"""내부 Source Pointer 경로(/internal/v1/source/*). host 공개 route(3.6)가 인증된 workspace로 호출한다."""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from securecode_context.api.source_wire import (
    delete_result,
    list_result,
    mutation_result,
    source_item,
)
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.models import (
    SourceLocation,
    SourceMutation,
    SourceTarget,
)
from securecode_context.pointers.source.registry import SourceRegistry

router = APIRouter(prefix="/internal/v1/source", tags=["source-pointers"])
WorkspaceIdField = Annotated[str, Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")]
PointerField = Annotated[str, Field(min_length=1, max_length=512)]
KeyField = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]


class _Body(BaseModel):
    """
    클래스 이름: _Body
    기능: 정의되지 않은 필드를 거절하는 요청 기반 모델.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")


class TargetBody(_Body):
    """
    클래스 이름: TargetBody
    기능: SourceMutationRequest.target. 경로 형식과 권한은 등록부가 다시 검사한다.
    작성 날짜: 2026/11/10
    """

    location: Literal["workspace", "external"]
    kind: Literal["file", "directory"]
    path: str = Field(min_length=1, max_length=4096)


class RegisterBody(_Body):
    """
    클래스 이름: RegisterBody
    기능: operation=register 요청과 인증된 workspace.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    idempotency_key: KeyField
    operation: Literal["register"]
    workspace_id: WorkspaceIdField
    target: TargetBody


class RefreshBody(_Body):
    """
    클래스 이름: RefreshBody
    기능: operation=refresh 요청과 인증된 workspace.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    idempotency_key: KeyField
    operation: Literal["refresh"]
    workspace_id: WorkspaceIdField
    pointer: PointerField


class StatBody(_Body):
    """
    클래스 이름: StatBody
    기능: 등록 하나의 현재 상태 조회 요청.
    작성 날짜: 2026/11/10
    """

    workspace_id: WorkspaceIdField
    pointer: PointerField


class ListBody(_Body):
    """
    클래스 이름: ListBody
    기능: PointerListQuery(kind=source)와 workspace.
    작성 날짜: 2026/11/10
    """

    workspace_id: WorkspaceIdField
    kind: Literal["source"] = "source"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class UnregisterBody(_Body):
    """
    클래스 이름: UnregisterBody
    기능: PointerDeleteRequest(kind=source). session_id는 계약상 허용하지 않는다.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    idempotency_key: KeyField
    kind: Literal["source"]
    workspace_id: WorkspaceIdField
    pointer: PointerField


def _registry(request: Request) -> SourceRegistry:
    """
    함수 이름: _registry()
    기능: 앱 수명 동안 공유하는 Source 등록부를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: SourceRegistry
    작성 날짜: 2026/11/10
    """
    adapter: SourceAdapter = request.app.state.source_adapter
    return adapter.registry


@router.post("/register")
async def register_source(request: Request, body: RegisterBody) -> dict[str, object]:
    """
    함수 이름: register_source()
    기능: 작업 공간 또는 사용자가 명시한 외부 파일·디렉터리를 등록한다.
    인자: request -> 인증된 요청, body -> 등록 요청
    반환값: SourceMutationResult
    작성 날짜: 2026/11/10
    """
    target = SourceTarget(SourceLocation(body.target.location), body.target.kind, body.target.path)
    mutation = await run_in_threadpool(_registry(request).register, body.workspace_id, target)
    return mutation_result(mutation)


@router.post("/refresh")
async def refresh_source(request: Request, body: RefreshBody) -> dict[str, object]:
    """
    함수 이름: refresh_source()
    기능: 권한을 다시 확인하고 바뀐 원본에 새 revision을 준다.
    인자: request -> 인증된 요청, body -> 갱신 요청
    반환값: SourceMutationResult(항목 1개)
    작성 날짜: 2026/11/10
    """
    record = await run_in_threadpool(_registry(request).refresh, body.workspace_id, body.pointer)
    return mutation_result(SourceMutation(body.workspace_id, items=[record]))


@router.post("/stat")
async def stat_source(request: Request, body: StatBody) -> dict[str, object]:
    """
    함수 이름: stat_source()
    기능: 범위·revision·원본 변경을 확인한 현재 descriptor를 돌려준다.
    인자: request -> 인증된 요청, body -> 조회 요청
    반환값: PointerListItem
    작성 날짜: 2026/11/10
    """
    record = await run_in_threadpool(_registry(request).stat, body.workspace_id, body.pointer)
    return source_item(record)


@router.post("/list")
async def list_sources(request: Request, body: ListBody) -> dict[str, object]:
    """
    함수 이름: list_sources()
    기능: workspace의 등록 목록을 최대 100개씩 돌려준다.
    인자: request -> 인증된 요청, body -> 목록 요청
    반환값: PointerListResult
    작성 날짜: 2026/11/10
    """
    registry = _registry(request)
    page = await run_in_threadpool(
        registry.list_sources, body.workspace_id, body.limit, body.cursor
    )
    return list_result(page)


@router.post("/unregister")
async def unregister_source(request: Request, body: UnregisterBody) -> dict[str, object]:
    """
    함수 이름: unregister_source()
    기능: 등록과 파생 캐시만 지운다. 사용자 원본 파일은 보존한다.
    인자: request -> 인증된 요청, body -> 해제 요청
    반환값: PointerDeleteResult
    작성 날짜: 2026/11/10
    """
    await run_in_threadpool(_registry(request).unregister, body.workspace_id, body.pointer)
    return delete_result(body.workspace_id, body.pointer)
