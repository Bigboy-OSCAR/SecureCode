"""POST /internal/v1/tokens/count: 내부 공용 tokens.count. host의 TokenCounter 포트가 이 경로를 쓴다."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.common.tokens.models import MAX_COUNT_TEXT_BYTES

# One input byte can occupy six JSON bytes (e.g. an escaped control character).
MAX_ENVELOPE_BYTES = 6 * MAX_COUNT_TEXT_BYTES + 4096

router = APIRouter(prefix="/internal/v1/tokens", tags=["tokens"])


class TokenCountBody(BaseModel):
    """
    클래스 이름: TokenCountBody
    기능: 계약 TokenCountRequest 본문. 정의되지 않은 필드는 거절한다.
    작성 날짜: 2026/11/04
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] | None = None
    text: str = Field(min_length=1)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/count")
async def count_tokens(request: Request) -> dict[str, object]:
    """
    함수 이름: count_tokens()
    기능: HTTP 본문을 상한 내에서 읽고 검증한 뒤 작업 스레드에서 계수한다.
    인자: request -> 인증된 요청
    반환값: TokenCountResult 사전
    작성 날짜: 2026/11/04
    """
    media_type = (
        request.headers.get("content-type", "application/json").split(";", 1)[0].strip().lower()
    )
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "JSON 본문이 필요합니다.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_ENVELOPE_BYTES:
            raise ServiceError(ErrorCode.PAYLOAD_TOO_LARGE, "계수할 요청 본문이 너무 큽니다.")
        data.extend(chunk)
    try:
        body = TokenCountBody.model_validate_json(data)
    except ValidationError:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "요청 형식이 올바르지 않습니다.") from None
    if any(getattr(body, field) is None for field in body.model_fields_set):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "요청 필드에 null을 사용할 수 없습니다.")
    token_counter: TokenCounter = request.app.state.token_counter
    result = await run_in_threadpool(token_counter.count, body.text, body.model_id)
    return result.to_wire()
