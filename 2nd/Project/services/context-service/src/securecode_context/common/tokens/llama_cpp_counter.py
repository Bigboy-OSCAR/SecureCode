"""로컬 llama.cpp server 계수기(qwen-2.5 등). 모델을 실제로 돌리는 그 서버의 tokenizer와 chat template을 쓴다.

- 본문 계수: `POST /tokenize` (특수 토큰 해석 없이 본문만, framing=plain_text).
- 요청 계수: `POST /apply-template`으로 OpenAI 호환 요청(messages·tools)을 서버가 실제로 쓰는 prompt로
  렌더링한 뒤 `POST /tokenize`(특수 토큰 해석, completion과 같은 add_special)로 센다.
같은 서버의 같은 경로로 세므로 count_mode는 exact다. 단, 서버의 usage.prompt_tokens와 대조하는 live
검증(tests/live/test_llama_cpp_count.py)을 실제 서버로 통과해야 그 표시를 믿을 수 있다.
"""

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

import httpx

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import CounterStatus, measure_countable_text
from securecode_context.common.tokens.models import CountMode, TokenCount
from securecode_context.common.tokens.request_framing import openai_input

COUNT_METHOD = "llama_cpp_tokenize"
TEXT_FRAMING = "plain_text"
REQUEST_FRAMING = "provider_request"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def server_root(base_url: str) -> str:
    """
    함수 이름: server_root()
    기능: OpenAI 호환 base URL(…/v1)에서 llama.cpp 서버 root를 얻는다.
    인자: base_url -> SECURECODE_PROVIDER_BASE_URL
    반환값: 끝 /v1을 뺀 URL
    작성 날짜: 2026/11/10
    """
    root = base_url.rstrip("/")
    return root[: -len("/v1")] if root.endswith("/v1") else root


def _unavailable(reason: str, retryable: bool) -> ServiceError:
    """
    함수 이름: _unavailable()
    기능: 서버 계수 실패를 원문·키 없이 TOKENIZER_UNAVAILABLE로 만든다.
    인자: reason -> 기계가 읽는 이유, retryable -> 재시도 가능 여부
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(
        ErrorCode.TOKENIZER_UNAVAILABLE, "로컬 모델 서버로 토큰을 세지 못했습니다.",
        {"reason": reason}, retryable=retryable,
    )  # fmt: skip


class LlamaCppTokenCounter:
    """
    클래스 이름: LlamaCppTokenCounter
    기능: 설정 모델 하나를 서비스하는 llama.cpp server의 /tokenize·/apply-template으로 센다(exact).
    작성 날짜: 2026/11/10
    """

    request_framing = "openai_chat"

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str | None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        cache_size: int = 1024,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 서버 주소·모델·키와 HTTP client, 본문 계수 캐시를 준비한다.
        인자: base_url -> OpenAI 호환 base URL(loopback), model_id -> 설정 모델,
            api_key -> llama-server --api-key 값(없으면 헤더 없음), timeout_seconds -> 호출 제한 시간,
            client -> 시험용 주입 client, cache_size -> 본문 계수 LRU 크기
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.model_id = model_id
        self._root = server_root(base_url)
        self._headers = {"content-type": "application/json"}
        if api_key:
            self._headers["authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._cache: OrderedDict[str, int] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def close(self) -> None:
        """
        함수 이름: close()
        기능: HTTP 연결을 정리한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._client.close()

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 설정된 상태를 돌려준다(서버 도달 여부는 계수 때 확인한다).
        인자: 없음
        반환값: configured=True인 CounterStatus
        작성 날짜: 2026/11/10
        """
        return CounterStatus(configured=True)

    def _post(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """
        함수 이름: _post()
        기능: 서버에 JSON을 보내고 응답을 상한 안에서 읽는다. 실패는 TOKENIZER_UNAVAILABLE이다.
        인자: path -> 서버 경로, body -> 요청 본문
        반환값: 응답 JSON 사전
        작성 날짜: 2026/11/10
        """
        try:
            response = self._client.post(
                self._root + path, json=body, headers=self._headers, follow_redirects=False
            )
        except httpx.TimeoutException as error:
            raise _unavailable("provider_timeout", True) from error
        except httpx.HTTPError as error:
            raise _unavailable("provider_unreachable", True) from error
        if response.status_code in (401, 403):
            raise _unavailable("provider_auth_failed", False)
        if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
            raise _unavailable(f"provider_http_{response.status_code}", response.status_code >= 500)
        try:
            data = response.json()
        except ValueError as error:
            raise _unavailable("invalid_provider_response", False) from error
        if not isinstance(data, dict):
            raise _unavailable("invalid_provider_response", False)
        return data

    def _tokens(self, content: str, special: bool) -> int:
        """
        함수 이름: _tokens()
        기능: /tokenize로 토큰 수를 센다.
        인자: content -> 문자열, special -> 특수 토큰 해석·add_special 여부(요청 prompt면 True)
        반환값: 토큰 수
        작성 날짜: 2026/11/10
        """
        body = {"content": content, "add_special": special, "parse_special": special}
        tokens = self._post("/tokenize", body).get("tokens")
        if not isinstance(tokens, list):
            raise _unavailable("invalid_provider_response", False)
        return len(tokens)

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 본문 하나를 서버 tokenizer로 센다(특수 토큰 문자열도 일반 텍스트로 센다).
        인자: text -> 본문, model_id -> 생략 또는 설정 모델만 허용
        반환값: count_mode=exact, framing=plain_text인 TokenCount
        작성 날짜: 2026/11/10
        """
        text_bytes = measure_countable_text(text)
        if model_id is not None and model_id != self.model_id:
            raise _unavailable("model_not_configured", False)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
        tokens = cached if cached is not None else self._tokens(text, special=False)
        with self._lock:
            self._cache[key] = tokens
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return TokenCount(
            tokens, CountMode.EXACT, "openai-compatible", self.model_id, COUNT_METHOD,
            TEXT_FRAMING, text_bytes, cached=cached is not None,
        )  # fmt: skip

    def count_request(self, request: Mapping[str, Any], model_id: str) -> TokenCount:
        """
        함수 이름: count_request()
        기능: OpenAI 호환 요청을 서버 chat template으로 렌더링하고 그 prompt를 센다.
        인자: request -> outbound 요청 JSON, model_id -> 요청 모델(설정 모델만 허용)
        반환값: count_mode=exact, framing=provider_request인 TokenCount
        작성 날짜: 2026/11/10
        """
        if model_id != self.model_id or request.get("model") != self.model_id:
            raise _unavailable("model_not_configured", False)
        rendered = self._post("/apply-template", openai_input(request)).get("prompt")
        if not isinstance(rendered, str) or not rendered:
            raise _unavailable("invalid_provider_response", False)
        size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        return TokenCount(
            self._tokens(rendered, special=True), CountMode.EXACT, "openai-compatible",
            self.model_id, COUNT_METHOD, REQUEST_FRAMING, size,
        )  # fmt: skip
