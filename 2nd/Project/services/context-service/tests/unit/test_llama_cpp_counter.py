"""로컬 llama.cpp server 계수기: 보내는 본문, framing 거절, 오류 변환, 설정 선택을 가짜 서버로 시험한다.

실제 서버와 같은 수인지(usage.prompt_tokens 대조)는 `npm run test:live`의 llama.cpp 단계가 확인한다.
"""

import json
from typing import Any

import httpx
import pytest

from securecode_context.app.factory import build_token_counter
from securecode_context.app.settings import load_settings
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import UnavailableTokenCounter
from securecode_context.common.tokens.llama_cpp_counter import LlamaCppTokenCounter, server_root
from securecode_context.common.tokens.request_framing import count_provider_request
from support.helpers import TEST_TOKEN

MODEL = "qwen2.5-7b-instruct"
REQUEST: dict[str, Any] = {
    "model": MODEL,
    "stream": True,
    "stream_options": {"include_usage": True},
    "max_tokens": 1024,
    "temperature": 0,
    "messages": [
        {"role": "system", "content": "시스템"},
        {"role": "user", "content": "안녕 🌏"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "결과"},
    ],
    "tools": [
        {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}
    ],
    "tool_choice": "auto",
}


class FakeServer:
    """
    클래스 이름: FakeServer
    기능: [fixture] llama.cpp /apply-template·/tokenize 흉내. 받은 요청을 기록하고 바이트 수를 토큰 수로 준다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, status: int = 200) -> None:
        """
        함수 이름: __init__()
        기능: 응답 상태와 기록을 준비한다.
        인자: status -> 돌려줄 HTTP 상태
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.status = status
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """
        함수 이름: __call__()
        기능: 경로별 가짜 응답을 만든다.
        인자: request -> 계수기가 보낸 요청
        반환값: 응답
        작성 날짜: 2026/11/10
        """
        body = json.loads(request.content)
        self.calls.append((request.url.path, body, request.headers.get("authorization")))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "x"})
        if request.url.path == "/apply-template":
            return httpx.Response(
                200, json={"prompt": "<|im_start|>" + json.dumps(body, ensure_ascii=False)}
            )
        return httpx.Response(
            200, json={"tokens": list(range(len(body["content"].encode("utf-8"))))}
        )


def counter(server: FakeServer) -> LlamaCppTokenCounter:
    """
    함수 이름: counter()
    기능: 가짜 서버에 연결한 계수기를 만든다.
    인자: server -> FakeServer
    반환값: LlamaCppTokenCounter
    작성 날짜: 2026/11/10
    """
    client = httpx.Client(transport=httpx.MockTransport(server))
    return LlamaCppTokenCounter("http://127.0.0.1:8080/v1", MODEL, "local-key", client=client)


def test_request_count_renders_with_the_server_template_then_tokenizes_specials() -> None:
    """
    함수 이름: test_request_count_renders_with_the_server_template_then_tokenizes_specials()
    기능: /apply-template에는 입력 필드(messages·tools·tool_choice)만, /tokenize에는 렌더링된 prompt를
        특수 토큰 해석과 함께 보내며 결과는 exact·provider_request다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    server = FakeServer()
    result = counter(server).count_request(REQUEST, MODEL)
    (path1, body1, auth), (path2, body2, _) = server.calls
    assert (path1, path2, auth) == ("/apply-template", "/tokenize", "Bearer local-key")
    assert body1 == {k: REQUEST[k] for k in ("messages", "tool_choice", "tools")}
    assert body2["content"].startswith("<|im_start|>")
    assert (body2["add_special"], body2["parse_special"]) == (True, True)
    assert result.token_count == len(body2["content"].encode("utf-8"))
    assert (result.count_mode.value, result.framing, result.method) == (
        "exact",
        "provider_request",
        "llama_cpp_tokenize",
    )


def test_text_count_is_plain_and_cached() -> None:
    """
    함수 이름: test_text_count_is_plain_and_cached()
    기능: 본문 계수는 특수 토큰을 해석하지 않고, 같은 본문은 캐시에서 돌려준다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    server = FakeServer()
    tokens = counter(server)
    first, second = tokens.count("한글 <|im_end|>"), tokens.count("한글 <|im_end|>")
    assert len(server.calls) == 1 and server.calls[0][1]["parse_special"] is False
    assert (first.framing, first.count_mode.value, second.cached) == ("plain_text", "exact", True)


@pytest.mark.parametrize(
    ("request_body", "reason"),
    [
        ({**REQUEST, "response_format": {"type": "json_object"}}, "framing_unverified"),
        ({**REQUEST, "model": "other"}, "model_not_configured"),
    ],
)
def test_unverified_requests_are_refused(request_body: dict[str, Any], reason: str) -> None:
    """
    함수 이름: test_unverified_requests_are_refused()
    기능: 모르는 입력 필드·다른 모델은 서버에 보내지 않고 TOKENIZER_UNAVAILABLE이다.
    인자: request_body -> 요청, reason -> 기대 이유
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    server = FakeServer()
    with pytest.raises(ServiceError) as caught:
        counter(server).count_request(request_body, MODEL)
    assert caught.value.code == ErrorCode.TOKENIZER_UNAVAILABLE
    assert caught.value.details["reason"] == reason
    assert server.calls == []


def test_server_errors_and_wrong_provider_fail_closed() -> None:
    """
    함수 이름: test_server_errors_and_wrong_provider_fail_closed()
    기능: 인증 실패·서버 오류는 TOKENIZER_UNAVAILABLE이고, Anthropic 요청은 이 계수기로 세지 않는다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    with pytest.raises(ServiceError) as caught:
        counter(FakeServer(401)).count_request(REQUEST, MODEL)
    assert caught.value.details["reason"] == "provider_auth_failed"
    with pytest.raises(ServiceError) as wrong:
        count_provider_request(counter(FakeServer()), "anthropic", MODEL, REQUEST)
    assert wrong.value.details["reason"] == "provider_framing_unsupported"
    assert (
        count_provider_request(
            counter(FakeServer()), "openai-compatible", MODEL, REQUEST
        ).token_count
        > 0
    )


def test_settings_pick_llama_cpp_only_when_asked(tmp_path: Any) -> None:
    """
    함수 이름: test_settings_pick_llama_cpp_only_when_asked()
    기능: SECURECODE_TOKEN_COUNTER=llama-cpp + openai-compatible + base URL일 때만 llama.cpp 계수기를 쓰고
        키는 SECURECODE_PROVIDER_API_KEY에서 읽는다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    base = {
        "SECURECODE_INTERNAL_TOKEN": TEST_TOKEN, "SECURECODE_DATA_DIR": str(tmp_path),
        "SECURECODE_PROVIDER_ID": "openai-compatible", "SECURECODE_MODEL_ID": MODEL,
        "SECURECODE_PROVIDER_BASE_URL": "http://127.0.0.1:8080/v1",
        "SECURECODE_PROVIDER_API_KEY": "local-key",
    }  # fmt: skip
    chosen = build_token_counter(load_settings({**base, "SECURECODE_TOKEN_COUNTER": "llama-cpp"}))
    assert isinstance(chosen, LlamaCppTokenCounter)
    chosen.close()
    assert isinstance(build_token_counter(load_settings(base)), UnavailableTokenCounter)
    assert server_root("http://127.0.0.1:8080/v1/") == "http://127.0.0.1:8080"
