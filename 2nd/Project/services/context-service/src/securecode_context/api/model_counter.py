"""인증된 host가 로컬 모델 교체 후 모든 서비스의 공용 계수기를 갱신한다."""

from typing import Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from securecode_context.api.bounded_body import read_bounded_json
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.common.tokens.llama_cpp_counter import LlamaCppTokenCounter
from securecode_context.common.tokens.lm_studio_counter import LmStudioTokenCounter
from securecode_context.common.tokens.switchable_counter import SwitchableTokenCounter

router = APIRouter(prefix="/internal/v1/models", tags=["models"])


class CounterConfiguration(BaseModel):
    """
    클래스 이름: CounterConfiguration
    기능: 내부 모델 교체 요청의 한정된 설정 필드만 허용한다.
    작성 날짜: 2026/11/11
    """

    model_config = ConfigDict(extra="forbid")
    runtime: Literal["llama-cpp", "lm-studio"]
    model_id: str = Field(min_length=1, max_length=128)
    base_url: str = Field(max_length=256)
    api_key: str | None = Field(default=None, max_length=512)


@router.post("/configure")
async def configure_counter(request: Request) -> dict[str, object]:
    """
    함수 이름: configure_counter()
    기능: 새 로컬 모델로 계수를 먼저 검증한 뒤 공용 계수기 참조를 교체한다.
    인자: request -> 내부 토큰으로 인증된 요청
    반환값: 비밀값 없는 활성 모델 정보
    작성 날짜: 2026/11/11
    """
    raw = await read_bounded_json(request, 4096)
    try:
        body = CounterConfiguration.model_validate_json(raw)
        url = httpx.URL(body.base_url)
        if (
            url.scheme != "http"
            or url.host not in ("127.0.0.1", "localhost", "::1")
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise ValueError("loopback required")
    except ValidationError, ValueError, httpx.InvalidURL:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED, "로컬 모델 설정이 올바르지 않습니다."
        ) from None
    shared = request.app.state.token_counter
    if not isinstance(shared, SwitchableTokenCounter):
        raise ServiceError(ErrorCode.SERVICE_UNAVAILABLE, "모델 교체가 활성화되지 않았습니다.")
    counter: TokenCounter
    if body.runtime == "llama-cpp":
        counter = LlamaCppTokenCounter(body.base_url, body.model_id, body.api_key)
    else:
        counter = LmStudioTokenCounter(body.base_url, body.model_id)
    try:
        await run_in_threadpool(counter.count, "LocalDesk 모델 준비 확인")
        await run_in_threadpool(shared.replace, counter)
    except Exception:
        close = getattr(counter, "close", None)
        if close:
            close()
        raise
    return {"schema_version": "1", "model_id": body.model_id, "ready": True}
