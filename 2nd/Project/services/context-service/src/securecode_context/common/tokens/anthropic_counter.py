"""Anthropic count_tokens 기반 본문 계수기(3.1 결정: 공개 로컬 tokenizer 없음, 결과는 provider_estimate)."""

import hashlib
import json
import threading
from collections import OrderedDict

import httpx

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import CounterStatus, measure_countable_text
from securecode_context.common.tokens.models import CountMode, TokenCount

DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
COUNT_METHOD = "anthropic_count_tokens"
COUNT_FRAMING = "single_user_message"


class AnthropicTokenCounter:
    """
    클래스 이름: AnthropicTokenCounter
    기능: 설정 모델 하나에 대해 count_tokens API로 본문을 계수하고 결과를 메모리 LRU에 보관한다.
    작성 날짜: 2026/11/04
    """

    def __init__(
        self,
        api_key: str,
        model_id: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        cache_size: int = 1024,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 키·모델·endpoint·timeout과 HTTP client, 캐시 크기를 설정한다.
        인자: api_key -> provider 키(로그·응답에 남기지 않는다)
            model_id -> 계수할 모델(3.1 검증 모델)
            base_url -> provider base URL
            timeout_seconds -> 호출 하나의 제한 시간
            client -> 시험용 주입 client, None이면 새로 만든다
            cache_size -> sha256(model, text) 키 캐시 최대 개수
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        self.model_id = model_id
        if cache_size < 0:
            raise ValueError("cache_size must be nonnegative")
        self.cache_size = cache_size
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/v1/messages/count_tokens"
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._cache: OrderedDict[str, TokenCount] = OrderedDict()
        self._lock = threading.Lock()

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 서비스가 만든 계수기의 HTTP 연결을 정리한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self._client.close()

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 키가 설정된 상태임을 돌려준다(키 값은 포함하지 않는다).
        인자: 없음
        반환값: configured=True인 CounterStatus
        작성 날짜: 2026/11/04
        """
        return CounterStatus(configured=True)

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 입력을 검사하고 캐시를 확인한 뒤 count_tokens를 호출한다.
        인자: text -> 계수할 본문
            model_id -> 생략 또는 설정 모델만 허용
        반환값: count_mode=provider_estimate인 TokenCount
        작성 날짜: 2026/11/04
        """
        text_bytes = measure_countable_text(text)
        if model_id is not None and model_id != self.model_id:
            raise ServiceError(
                ErrorCode.TOKENIZER_UNAVAILABLE,
                "설정되지 않은 모델의 계수는 지원하지 않습니다.",
                {"reason": "model_not_configured"},
                retryable=False,
            )

        cache_key = hashlib.sha256(f"{self.model_id}\x00{text}".encode()).hexdigest()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached.as_cached()

        token_count = self._request_count(text)
        result = TokenCount(
            token_count=token_count,
            count_mode=CountMode.PROVIDER_ESTIMATE,
            provider_id="anthropic",
            model_id=self.model_id,
            method=COUNT_METHOD,
            framing=COUNT_FRAMING,
            text_bytes=text_bytes,
        )
        with self._lock:
            self._cache[cache_key] = result
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return result

    def _request_count(self, text: str) -> int:
        """
        함수 이름: _request_count()
        기능: count_tokens API를 한 번 호출하고 오류를 TOKENIZER_UNAVAILABLE 계열로 바꾼다.
        인자: text -> 이미 검사한 본문
        반환값: input_tokens 값
        작성 날짜: 2026/11/04
        """
        body = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            with self._client.stream(
                "POST", self._endpoint, json=body, headers=headers, follow_redirects=False
            ) as response:
                status = response.status_code
                if status in (401, 403):
                    raise _unavailable("provider_auth_failed", retryable=False)
                if status != 200:
                    raise _unavailable(
                        f"provider_http_{status}", retryable=status == 429 or status >= 500
                    )
                payload = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    if len(payload) + len(chunk) > 64 * 1024:
                        raise _unavailable("invalid_provider_response", retryable=False)
                    payload.extend(chunk)
        except httpx.TimeoutException as error:
            raise _unavailable("provider_timeout", retryable=True) from error
        except httpx.HTTPError as error:
            raise _unavailable("provider_unreachable", retryable=True) from error

        try:
            input_tokens = json.loads(payload)["input_tokens"]
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise _unavailable("invalid_provider_response", retryable=False) from error
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
            raise _unavailable("invalid_provider_response", retryable=False)
        return input_tokens


def _unavailable(reason: str, retryable: bool) -> ServiceError:
    """
    함수 이름: _unavailable()
    기능: provider 계수 실패를 원문·키 없이 TOKENIZER_UNAVAILABLE 오류로 만든다.
    인자: reason -> 기계가 읽는 실패 이유
        retryable -> 재시도 가능 여부
    반환값: ServiceError
    작성 날짜: 2026/11/04
    """
    return ServiceError(
        ErrorCode.TOKENIZER_UNAVAILABLE,
        "토큰 계수에 실패했습니다.",
        {"reason": reason},
        retryable=retryable,
    )
