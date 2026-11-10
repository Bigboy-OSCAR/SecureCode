"""전체 provider 요청 계수(4.8 gate)의 framing 규칙과 포트.

framing은 Anthropic Messages 요청과 OpenAI 호환 chat 요청(로컬 llama.cpp server) 두 가지다.
입력 토큰에 영향을 주는 필드는 그대로 계수기로 보내고,
출력·전송 설정 필드만 뺀다. 모르는 필드가 있으면 계수가 맞는지 알 수 없으므로 fail-closed로 막는다.
"""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.models import TokenCount

MAX_REQUEST_BYTES = 16 * 1024 * 1024
ANTHROPIC_INPUT_KEYS = frozenset({"system", "messages", "tools", "tool_choice", "thinking"})
ANTHROPIC_SETTING_KEYS = frozenset(
    {
        "model", "max_tokens", "stream", "temperature", "top_p", "top_k",
        "stop_sequences", "metadata", "service_tier",
        # 3.1 S-05: Cline SDK가 붙이는 표준 외 필드. 입력 토큰에 들어가지 않는다.
        "fallbacks", "cache_control",
    }
)  # fmt: skip
VERIFIED_FALLBACKS = "default"


# OpenAI 호환 chat 요청: 입력 토큰은 chat template이 렌더링하는 필드에서만 나온다.
OPENAI_INPUT_KEYS = frozenset({"messages", "tools", "tool_choice", "parallel_tool_calls"})
OPENAI_SETTING_KEYS = frozenset(
    {
        "model", "stream", "stream_options", "max_tokens", "max_completion_tokens",
        "temperature", "top_p", "top_k", "stop", "seed", "frequency_penalty",
        "presence_penalty", "user", "n",
    }
)  # fmt: skip
# provider_id → 계수기가 내세워야 하는 framing 이름(counter.request_framing).
PROVIDER_FRAMINGS = {"anthropic": "anthropic_messages", "openai-compatible": "openai_chat"}


def _framing_error(reason: str, key: str | None = None) -> ServiceError:
    """
    함수 이름: _framing_error()
    기능: 검증하지 않은 요청 모양을 TOKENIZER_UNAVAILABLE로 거절한다.
    인자: reason -> 기계가 읽는 이유, key -> 문제 필드 이름(값은 넣지 않는다)
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    details: dict[str, str | int | float | bool | None] = {"reason": reason}
    if key is not None:
        details["field"] = key[:64]
    return ServiceError(
        ErrorCode.TOKENIZER_UNAVAILABLE,
        "이 모델 요청 형식은 정확히 계수할 수 없습니다.",
        details,
        retryable=False,
    )


def anthropic_input(request: Mapping[str, Any]) -> dict[str, Any]:
    """
    함수 이름: anthropic_input()
    기능: Anthropic Messages 요청에서 입력 토큰에 들어가는 필드만 꺼낸다.
    인자: request -> outbound 요청 JSON 객체
    반환값: count_tokens 본문(model 제외)
    작성 날짜: 2026/11/10
    """
    unknown = sorted(set(request) - ANTHROPIC_INPUT_KEYS - ANTHROPIC_SETTING_KEYS)
    if unknown:
        raise _framing_error("framing_unverified", unknown[0])
    if "fallbacks" in request and request["fallbacks"] != VERIFIED_FALLBACKS:
        raise _framing_error("framing_unverified", "fallbacks")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise _framing_error("messages_missing")
    return {key: request[key] for key in sorted(ANTHROPIC_INPUT_KEYS) if key in request}


def openai_input(request: Mapping[str, Any]) -> dict[str, Any]:
    """
    함수 이름: openai_input()
    기능: OpenAI 호환 chat 요청에서 chat template 입력 필드만 꺼낸다. 모르는 필드는 거절한다.
    인자: request -> outbound 요청 JSON 객체
    반환값: 입력 필드 사전
    작성 날짜: 2026/11/10
    """
    unknown = sorted(set(request) - OPENAI_INPUT_KEYS - OPENAI_SETTING_KEYS)
    if unknown:
        raise _framing_error("framing_unverified", unknown[0])
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise _framing_error("messages_missing")
    return {key: request[key] for key in sorted(OPENAI_INPUT_KEYS) if key in request}


@runtime_checkable
class RequestTokenCounter(Protocol):
    """
    클래스 이름: RequestTokenCounter
    기능: 직렬화된 provider 요청 전체를 세는 포트. 실패하면 TOKENIZER_UNAVAILABLE을 던진다.
    작성 날짜: 2026/11/10
    """

    def count_request(self, request: Mapping[str, Any], model_id: str) -> TokenCount:
        """
        함수 이름: count_request()
        기능: 요청 JSON의 입력 토큰을 센다.
        인자: request -> outbound 요청 JSON, model_id -> 요청 모델
        반환값: TokenCount
        작성 날짜: 2026/11/10
        """
        ...


def count_provider_request(
    counter: object, provider_id: str, model_id: str, request: Mapping[str, Any]
) -> TokenCount:
    """
    함수 이름: count_provider_request()
    기능: provider framing을 확인하고 요청 전체를 센다. 검증한 framing이 없으면 거절한다.
    인자: counter -> 앱 TokenCounter, provider_id/model_id -> 요청 대상, request -> 요청 JSON
    반환값: TokenCount
    작성 날짜: 2026/11/10
    """
    framing = PROVIDER_FRAMINGS.get(provider_id)
    if framing is None:
        raise _framing_error("provider_framing_unsupported")
    if not isinstance(counter, RequestTokenCounter):
        # 미설정 계수기는 그 이유(api_key_missing 등)를 그대로 알린다.
        raise _framing_error(str(getattr(counter, "reason", "request_counter_unavailable")))
    if getattr(counter, "request_framing", None) != framing:
        raise _framing_error("provider_framing_unsupported")
    return counter.count_request(request, model_id)
