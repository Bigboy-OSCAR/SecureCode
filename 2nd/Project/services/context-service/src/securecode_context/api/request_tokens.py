"""POST /internal/v1/tokens/request: 4.8 gate용 전체 provider 요청 계수.

host fetch gate가 SDK가 보내려던 직렬화 요청을 그대로 넘긴다. 서비스는 framing을 확인하고 세기만 하며
허용·차단(예산 산술, hard-cap 모드)은 host gate가 정한다.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from securecode_context.api.bounded_body import read_bounded_json
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.request_framing import (
    MAX_REQUEST_BYTES,
    count_provider_request,
)

# 요청 JSON이 문자열이 아닌 객체로 오므로 envelope 여유만 더한다.
MAX_ENVELOPE_BYTES = MAX_REQUEST_BYTES + 4096
router = APIRouter(prefix="/internal/v1/tokens", tags=["tokens"])


class RequestCountBody(BaseModel):
    """
    클래스 이름: RequestCountBody
    기능: 계약 RequestTokenCountRequest. request는 outbound 요청 JSON 객체 그대로다.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    request: dict[str, Any]


@router.post("/request")
async def count_request(request: Request) -> dict[str, object]:
    """
    함수 이름: count_request()
    기능: 본문을 상한 안에서 읽고 작업 스레드에서 요청 전체를 센다.
    인자: request -> 인증된 요청
    반환값: TokenCountResult 사전(framing=provider_request)
    작성 날짜: 2026/11/10
    """
    data = await read_bounded_json(request, MAX_ENVELOPE_BYTES)
    try:
        body = RequestCountBody.model_validate_json(data)
    except ValidationError:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "요청 형식이 올바르지 않습니다.") from None
    counter = request.app.state.token_counter
    result = await run_in_threadpool(
        count_provider_request, counter, body.provider_id, body.model_id, body.request
    )
    return result.to_wire()
