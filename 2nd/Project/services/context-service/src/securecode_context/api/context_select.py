"""POST /internal/v1/context/select: 4.8 Context Selector(정책 CONTEXT_SELECTOR.md 2.0).

host가 인증된 workspace·session과 비용 텍스트, current_task·이력 ref를 넘긴다. 응답은 계약
ContextSelectResponse(ContextPreviewPlan + run 생성 오류)다.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from securecode_context.api.bounded_body import read_bounded_json
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.context.budget import CostInput
from securecode_context.context.service import ContextSelectService, SelectRequest

MAX_SELECT_BODY_BYTES = 24 * 1024 * 1024
router = APIRouter(prefix="/internal/v1/context", tags=["context"])
_SHA = r"^[0-9a-f]{64}$"


class _Strict(BaseModel):
    """
    클래스 이름: _Strict
    기능: 정의되지 않은 필드를 거절하는 기본 모델.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")


class SelectionBody(_Strict):
    """
    클래스 이름: SelectionBody
    기능: 계약 PointerSelection. range 모양은 resolver가 종류별로 확인한다.
    작성 날짜: 2026/11/10
    """

    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=_SHA)
    range: dict[str, Any]


class SymbolRefBody(_Strict):
    """
    클래스 이름: SymbolRefBody
    기능: 계약 SymbolContextRef.
    작성 날짜: 2026/11/10
    """

    kind: Literal["symbol"]
    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9-]{8,64}$")
    index_revision: int = Field(ge=1)


class PointerRefBody(_Strict):
    """
    클래스 이름: PointerRefBody
    기능: 계약 PointerContextRef(selection 선택).
    작성 날짜: 2026/11/10
    """

    kind: Literal["source", "runtime"]
    pointer: str = Field(min_length=1, max_length=512)
    selection: SelectionBody | None = None


RefBody = Annotated[SymbolRefBody | PointerRefBody, Field(discriminator="kind")]


class CostsBody(_Strict):
    """
    클래스 이름: CostsBody
    기능: host 고정 비용 재료(계약 ContextSelectCosts).
    작성 날짜: 2026/11/10
    """

    model_context_limit: int = Field(ge=1, le=10_000_000)
    reserved_output_tokens: int = Field(ge=0)
    safety_margin_tokens: int = Field(ge=0)
    message_overhead_tokens: int = Field(ge=0)
    system: str = Field(max_length=1024 * 1024)
    tool_schema: str = Field(max_length=1024 * 1024)
    history: list[str] = Field(max_length=1024)


class InputBody(_Strict):
    """
    클래스 이름: InputBody
    기능: 계약 ContextPlanInput. 명시 포인터는 확인한 selection이 있어야 한다.
    작성 날짜: 2026/11/10
    """

    workspace_id: str = Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")
    session_id: str = Field(pattern=r"^ses_[A-Za-z0-9-]{8,64}$")
    index_revision: int = Field(ge=1)
    prompt: str = Field(min_length=1, max_length=32000, pattern=r"\S")
    context_refs: list[RefBody] = Field(max_length=32)

    @model_validator(mode="after")
    def _explicit_selection(self) -> InputBody:
        """
        함수 이름: _explicit_selection()
        기능: 명시 포인터 ref에 selection이 없으면 거절한다.
        인자: 없음
        반환값: 검증한 모델
        작성 날짜: 2026/11/10
        """
        for ref in self.context_refs:
            if isinstance(ref, PointerRefBody) and ref.selection is None:
                raise ValueError("explicit pointer needs a selection")
        return self


class SelectBody(_Strict):
    """
    클래스 이름: SelectBody
    기능: 계약 ContextSelectRequest.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    input: InputBody
    current_task_refs: list[PointerRefBody] = Field(default_factory=list, max_length=64)
    history_refs: list[RefBody] = Field(default_factory=list, max_length=256)
    costs: CostsBody


def _wire(ref: BaseModel) -> dict[str, Any]:
    """
    함수 이름: _wire()
    기능: ref 모델을 None 필드 없는 사전으로 바꾼다.
    인자: ref -> ref 모델
    반환값: 사전
    작성 날짜: 2026/11/10
    """
    return ref.model_dump(exclude_none=True)


def to_request(body: SelectBody) -> SelectRequest:
    """
    함수 이름: to_request()
    기능: 검증한 본문을 SelectRequest로 바꾼다.
    인자: body -> SelectBody
    반환값: SelectRequest
    작성 날짜: 2026/11/10
    """
    plan_input, costs = body.input, body.costs
    return SelectRequest(
        workspace_id=plan_input.workspace_id,
        session_id=plan_input.session_id,
        index_revision=plan_input.index_revision,
        prompt=plan_input.prompt,
        context_refs=[_wire(ref) for ref in plan_input.context_refs],
        costs=CostInput(
            costs.model_context_limit,
            costs.reserved_output_tokens,
            costs.safety_margin_tokens,
            costs.message_overhead_tokens,
            costs.system,
            costs.tool_schema,
            plan_input.prompt,
            list(costs.history),
        ),
        current_task_refs=[_wire(ref) for ref in body.current_task_refs],
        history_refs=[_wire(ref) for ref in body.history_refs],
    )


@router.post("/select")
async def select_context(request: Request) -> dict[str, Any]:
    """
    함수 이름: select_context()
    기능: 본문을 상한 안에서 읽어 검증하고 작업 스레드에서 계획을 만든다.
    인자: request -> 인증된 요청
    반환값: ContextSelectResponse 사전
    작성 날짜: 2026/11/10
    """
    data = await read_bounded_json(request, MAX_SELECT_BODY_BYTES)
    try:
        body = SelectBody.model_validate_json(data)
    except ValidationError:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "요청 형식이 올바르지 않습니다.") from None
    service: ContextSelectService = request.app.state.context_select
    return await run_in_threadpool(service.plan, to_request(body))
