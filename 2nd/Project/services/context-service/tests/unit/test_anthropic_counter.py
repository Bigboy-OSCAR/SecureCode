"""AnthropicTokenCounter를 httpx.MockTransport(scripted provider)로 검사한다. live 호출은 npm run test:live 범위다."""

import json
from collections.abc import Callable

import httpx
import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import (
    AnthropicTokenCounter,
    CountMode,
    UnavailableTokenCounter,
)
from support.helpers import load_shared_vectors

UNICODE_CASES = load_shared_vectors("token-unicode-cases.json")["cases"]
VALID_CASES = [case for case in UNICODE_CASES if case["expect"] == "valid"]
INVALID_CASES = [case for case in UNICODE_CASES if case["expect"] == "invalid_unicode"]


def make_counter(
    handler: Callable[[httpx.Request], httpx.Response], captured: list[httpx.Request]
) -> AnthropicTokenCounter:
    """
    함수 이름: make_counter()
    기능: 요청을 기록하고 handler 응답을 돌려주는 scripted transport로 계수기를 만든다.
    인자: handler -> 요청별 응답 함수
        captured -> 보낸 요청을 담을 목록
    반환값: AnthropicTokenCounter
    작성 날짜: 2026/11/04
    """

    def record(request: httpx.Request) -> httpx.Response:
        """
        함수 이름: record()
        기능: 요청을 기록한 뒤 handler에 넘긴다.
        인자: request -> 보낸 요청
        반환값: handler 응답
        작성 날짜: 2026/11/04
        """
        captured.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return AnthropicTokenCounter("sk-ant-test-key-000000", "claude-sonnet-5-5", client=client)


def ok_response(request: httpx.Request) -> httpx.Response:
    """
    함수 이름: ok_response()
    기능: 받은 text의 code point 수를 input_tokens로 돌려주는 scripted 응답.
    인자: request -> 보낸 요청
    반환값: 200 응답
    작성 날짜: 2026/11/04
    """
    text = json.loads(request.content)["messages"][0]["content"][0]["text"]
    return httpx.Response(200, json={"input_tokens": len(text)})


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda case: case["name"])
def test_unicode_text_is_sent_unchanged(case: dict[str, object]) -> None:
    """
    함수 이름: test_unicode_text_is_sent_unchanged()
    기능: 한글·이모지·결합 문자·NUL·BOM이 손실 없이 전송되고 text_bytes가 공용 벡터와 같은지 확인한다.
    인자: case -> 공용 Unicode 벡터
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    captured: list[httpx.Request] = []
    result = make_counter(ok_response, captured).count(str(case["text"]))
    sent = json.loads(captured[0].content)

    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["messages"][0]["content"][0]["text"] == case["text"]
    assert result.text_bytes == case["utf8_bytes"]
    assert result.token_count == case["code_points"]
    assert result.count_mode is CountMode.PROVIDER_ESTIMATE
    assert result.to_wire()["framing"] == "single_user_message"


def test_request_headers_and_endpoint() -> None:
    """
    함수 이름: test_request_headers_and_endpoint()
    기능: count_tokens endpoint와 x-api-key·anthropic-version 헤더를 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    captured: list[httpx.Request] = []
    make_counter(ok_response, captured).count("hello")
    request = captured[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages/count_tokens"
    assert request.headers["x-api-key"] == "sk-ant-test-key-000000"
    assert request.headers["anthropic-version"] == "2023-06-01"


@pytest.mark.parametrize("case", INVALID_CASES, ids=lambda case: case["name"])
def test_invalid_unicode_is_rejected_before_any_call(case: dict[str, object]) -> None:
    """
    함수 이름: test_invalid_unicode_is_rejected_before_any_call()
    기능: 외톨이 surrogate는 provider 호출 없이 VALIDATION_FAILED(invalid_unicode)인지 확인한다.
    인자: case -> 잘못된 Unicode 벡터
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    captured: list[httpx.Request] = []
    with pytest.raises(ServiceError) as error_info:
        make_counter(ok_response, captured).count(str(case["text"]))
    assert error_info.value.code is ErrorCode.VALIDATION_FAILED
    assert error_info.value.details["reason"] == "invalid_unicode"
    assert captured == []


@pytest.mark.parametrize(
    ("status", "reason", "retryable"),
    [
        (401, "provider_auth_failed", False),
        (429, "provider_http_429", True),
        (500, "provider_http_500", True),
        (400, "provider_http_400", False),
    ],
)
def test_provider_errors_map_to_tokenizer_unavailable(
    status: int, reason: str, retryable: bool
) -> None:
    """
    함수 이름: test_provider_errors_map_to_tokenizer_unavailable()
    기능: provider HTTP 오류가 원문·키 없이 TOKENIZER_UNAVAILABLE로 바뀌는지 확인한다.
    인자: status -> provider 응답 상태
        reason -> 기대 details.reason
        retryable -> 기대 재시도 여부
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    counter = make_counter(lambda _request: httpx.Response(status, json={"error": "x"}), [])
    with pytest.raises(ServiceError) as error_info:
        counter.count("secret source text")
    error = error_info.value
    assert (error.code, error.details["reason"], error.retryable) == (
        ErrorCode.TOKENIZER_UNAVAILABLE,
        reason,
        retryable,
    )
    assert "secret source text" not in error.message


def test_timeout_and_bad_payload() -> None:
    """
    함수 이름: test_timeout_and_bad_payload()
    기능: timeout과 input_tokens 누락 응답을 각각 retryable/비retryable 오류로 처리하는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        """
        함수 이름: raise_timeout()
        기능: timeout을 흉내 낸다.
        인자: request -> 보낸 요청
        반환값: 반환하지 않는다
        작성 날짜: 2026/11/04
        """
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ServiceError) as timeout_info:
        make_counter(raise_timeout, []).count("x")
    assert timeout_info.value.retryable is True

    bad_counter = make_counter(lambda _request: httpx.Response(200, json={"tokens": 3}), [])
    with pytest.raises(ServiceError) as payload_info:
        bad_counter.count("x")
    assert payload_info.value.details["reason"] == "invalid_provider_response"


def test_cache_and_model_guard() -> None:
    """
    함수 이름: test_cache_and_model_guard()
    기능: 같은 본문은 캐시(cached=True)로 1회만 호출하고 다른 모델은 거절하는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    captured: list[httpx.Request] = []
    counter = make_counter(ok_response, captured)
    first = counter.count("같은 본문")
    second = counter.count("같은 본문")
    assert (first.cached, second.cached, len(captured)) == (False, True, 1)

    with pytest.raises(ServiceError) as error_info:
        counter.count("x", model_id="other-model")
    assert error_info.value.details["reason"] == "model_not_configured"


def test_unavailable_counter_never_estimates() -> None:
    """
    함수 이름: test_unavailable_counter_never_estimates()
    기능: 키가 없을 때 추정값 대신 TOKENIZER_UNAVAILABLE을 던지는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    with pytest.raises(ServiceError) as error_info:
        UnavailableTokenCounter("api_key_missing").count("hello")
    assert error_info.value.code is ErrorCode.TOKENIZER_UNAVAILABLE
    assert error_info.value.details == {"reason": "api_key_missing"}
