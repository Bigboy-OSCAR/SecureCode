"""4.8 전체 provider 요청 계수: framing 검사, Anthropic count_tokens 본문, 내부 경로 계약을 시험한다."""

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import AnthropicTokenCounter, UnavailableTokenCounter
from securecode_context.common.tokens.request_framing import anthropic_input
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
MODEL = "claude-sonnet-5-5"
RESULT_REF = "common/token-count.schema.json#/definitions/TokenCountResult"
REQUEST_REF = "common/token-count.schema.json#/definitions/RequestTokenCountRequest"
OUTBOUND: dict[str, Any] = {
    "model": MODEL,
    "max_tokens": 1024,
    "stream": True,
    "fallbacks": "default",
    "system": [{"type": "text", "text": "시스템", "cache_control": {"type": "ephemeral"}}],
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "안녕하세요 🌏"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "결과"}],
        },
    ],
    "tools": [{"name": "read_file", "description": "읽기", "input_schema": {"type": "object"}}],
}


def test_framing_keeps_input_fields_and_drops_output_settings() -> None:
    """
    함수 이름: test_framing_keeps_input_fields_and_drops_output_settings()
    기능: system·messages·tools는 그대로(tool_use/tool_result 쌍 포함), max_tokens·stream·model은 뺀다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    counted = anthropic_input(OUTBOUND)
    assert set(counted) == {"system", "messages", "tools"}
    assert counted["messages"] == OUTBOUND["messages"]


@pytest.mark.parametrize(
    ("request_body", "reason"),
    [
        ({**OUTBOUND, "mcp_servers": []}, "framing_unverified"),
        ({**OUTBOUND, "messages": []}, "messages_missing"),
        ({**OUTBOUND, "fallbacks": ["other-model"]}, "framing_unverified"),
    ],
)
def test_unverified_framing_is_refused(request_body: dict[str, Any], reason: str) -> None:
    """
    함수 이름: test_unverified_framing_is_refused()
    기능: 모르는 입력 필드나 메시지 없는 요청은 계수하지 않고 TOKENIZER_UNAVAILABLE이다.
    인자: request_body -> 요청, reason -> 기대 이유
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    with pytest.raises(ServiceError) as caught:
        anthropic_input(request_body)
    assert caught.value.code == ErrorCode.TOKENIZER_UNAVAILABLE
    assert caught.value.details["reason"] == reason


def test_anthropic_counter_sends_the_request_input_unchanged() -> None:
    """
    함수 이름: test_anthropic_counter_sends_the_request_input_unchanged()
    기능: count_tokens에 보낸 본문이 outbound 요청의 입력 부분과 같고 결과는 provider_estimate다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """
        함수 이름: handler()
        기능: [fixture] count_tokens 호출 본문을 기록하고 고정 결과를 돌려준다.
        인자: request -> provider로 가려던 요청
        반환값: input_tokens=321 응답
        작성 날짜: 2026/11/10
        """
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"input_tokens": 321})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    counter = AnthropicTokenCounter("key", MODEL, client=client)
    result = counter.count_request(OUTBOUND, MODEL)
    assert sent == [{"model": MODEL, **anthropic_input(OUTBOUND)}]
    assert (result.token_count, result.count_mode.value, result.framing) == (
        321,
        "provider_estimate",
        "provider_request",
    )
    with pytest.raises(ServiceError) as caught:
        counter.count_request({**OUTBOUND, "model": "other"}, MODEL)
    assert caught.value.code == ErrorCode.TOKENIZER_UNAVAILABLE


def test_request_route_counts_and_refuses_unsupported(
    service_settings: ServiceSettings, contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_request_route_counts_and_refuses_unsupported()
    기능: 내부 경로가 계약 결과를 돌려주고, 검증하지 않은 provider와 미설정 계수기는 거절한다.
    인자: service_settings -> 시험 설정, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    body = {
        "schema_version": "1",
        "provider_id": "anthropic",
        "model_id": MODEL,
        "request": OUTBOUND,
    }
    assert contract_check(REQUEST_REF, body) == []
    with TestClient(create_app(service_settings, token_counter=FixedTokenCounter())) as client:
        ok = client.post("/internal/v1/tokens/request", json=body, headers=AUTH)
        other = client.post(
            "/internal/v1/tokens/request", json={**body, "provider_id": "openai"}, headers=AUTH
        )
    assert ok.status_code == 200 and contract_check(RESULT_REF, ok.json()) == []
    expected = len(
        json.dumps(anthropic_input(OUTBOUND), ensure_ascii=False, sort_keys=True).encode()
    )
    assert ok.json()["token_count"] == expected
    assert other.json()["error"]["details"]["reason"] == "provider_framing_unsupported"
    unavailable = UnavailableTokenCounter("api_key_missing")
    with TestClient(create_app(service_settings, token_counter=unavailable)) as client:
        refused = client.post("/internal/v1/tokens/request", json=body, headers=AUTH)
    assert refused.json()["error"]["code"] == "TOKENIZER_UNAVAILABLE"
    assert refused.json()["error"]["details"]["reason"] == "api_key_missing"
