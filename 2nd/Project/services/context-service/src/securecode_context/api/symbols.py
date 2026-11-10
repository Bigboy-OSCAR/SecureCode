"""내부 작업 공간·R0 경로(3.6): workspaces/register, symbols/{index,index/status,search,bundle}.

host가 작업 공간을 만들 때 root를 등록하고, 색인은 백그라운드 스레드에서 만든다(상태는 status로 확인).
검색 결과에는 원문이 없고 원문은 bundle(바이트·토큰 상한)로만 나간다.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from securecode_context.common.workspace_roots import WorkspaceRootRegistry
from securecode_context.symbols.index import SymbolIndexService
from securecode_context.symbols.symbol_service import R0SymbolService

router = APIRouter(prefix="/internal/v1", tags=["symbols"])
WorkspaceIdField = Annotated[str, Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")]
_BUILDS = ThreadPoolExecutor(1, thread_name_prefix="r0-index")


class _Strict(BaseModel):
    """
    클래스 이름: _Strict
    기능: 정의되지 않은 필드를 거절하는 기본 모델.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")


class RegisterBody(_Strict):
    """
    클래스 이름: RegisterBody
    기능: host가 검증한 작업 공간 root 등록 요청.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField
    root_path: str = Field(min_length=1, max_length=4096)


class WorkspaceBody(_Strict):
    """
    클래스 이름: WorkspaceBody
    기능: 작업 공간 하나를 가리키는 요청(색인 시작·상태).
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField


class PageBody(_Strict):
    """
    클래스 이름: PageBody
    기능: 계약 PageRequest.
    작성 날짜: 2026/11/10
    """

    limit: int | None = Field(default=None, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class SearchBody(_Strict):
    """
    클래스 이름: SearchBody
    기능: 계약 SymbolSearchRequest.
    작성 날짜: 2026/11/10
    """

    workspace_id: WorkspaceIdField
    query: str = Field(min_length=1, max_length=2000)
    index_revision: int | None = Field(default=None, ge=1)
    page: PageBody | None = None


class BundleBody(_Strict):
    """
    클래스 이름: BundleBody
    기능: 계약 SymbolBundleRequest.
    작성 날짜: 2026/11/10
    """

    workspace_id: WorkspaceIdField
    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9-]{8,64}$")
    index_revision: int = Field(ge=1)
    max_tokens: int = Field(ge=1, le=32768)
    max_bytes: int | None = Field(default=None, ge=1, le=32768)


def _roots(request: Request) -> WorkspaceRootRegistry:
    """
    함수 이름: _roots()
    기능: 앱의 작업 공간 root 등록부를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: WorkspaceRootRegistry
    작성 날짜: 2026/11/10
    """
    roots: WorkspaceRootRegistry = request.app.state.workspace_roots
    return roots


def _symbols(request: Request) -> R0SymbolService:
    """
    함수 이름: _symbols()
    기능: 앱의 R0 서비스를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: R0SymbolService
    작성 날짜: 2026/11/10
    """
    service: R0SymbolService = request.app.state.symbols
    return service


@router.post("/workspaces/register")
async def register_workspace(request: Request, body: RegisterBody) -> dict[str, Any]:
    """
    함수 이름: register_workspace()
    기능: 작업 공간 root를 검사·등록한다(같은 값이면 멱등). 응답에 경로를 넣지 않는다.
    인자: request -> 인증된 요청, body -> 등록 요청
    반환값: {"workspace_id", "registered": true}
    작성 날짜: 2026/11/10
    """
    await run_in_threadpool(_roots(request).register, body.workspace_id, body.root_path)
    return {"schema_version": "1", "workspace_id": body.workspace_id, "registered": True}


@router.post("/symbols/index")
async def start_index(request: Request, body: WorkspaceBody) -> dict[str, Any]:
    """
    함수 이름: start_index()
    기능: 색인을 백그라운드에서 시작하고 현재 상태(IndexStatusResponse)를 돌려준다.
        이미 진행 중이면 새로 시작하지 않는다.
    인자: request -> 인증된 요청, body -> 작업 공간
    반환값: IndexStatusResponse
    작성 날짜: 2026/11/10
    """
    root = _roots(request).root_for(body.workspace_id)
    index: SymbolIndexService = _symbols(request).index
    _BUILDS.submit(index.build, body.workspace_id, root)
    return await run_in_threadpool(index.status, body.workspace_id, root)


@router.post("/symbols/index/status")
async def index_status(request: Request, body: WorkspaceBody) -> dict[str, Any]:
    """
    함수 이름: index_status()
    기능: 색인 상태와 디스크 변경(stale) 여부를 돌려준다.
    인자: request -> 인증된 요청, body -> 작업 공간
    반환값: IndexStatusResponse
    작성 날짜: 2026/11/10
    """
    root = _roots(request).root_for(body.workspace_id)
    return await run_in_threadpool(_symbols(request).index.status, body.workspace_id, root)


@router.post("/symbols/search")
async def search_symbols(request: Request, body: SearchBody) -> dict[str, Any]:
    """
    함수 이름: search_symbols()
    기능: R0 TF-IDF 후보(원문 없음)를 찾는다.
    인자: request -> 인증된 요청, body -> SymbolSearchRequest
    반환값: SymbolSearchResponse
    작성 날짜: 2026/11/10
    """
    _roots(request).root_for(body.workspace_id)
    payload = body.model_dump(exclude_none=True)
    return await run_in_threadpool(_symbols(request).search, payload)


@router.post("/symbols/bundle")
async def read_bundle(request: Request, body: BundleBody) -> dict[str, Any]:
    """
    함수 이름: read_bundle()
    기능: 후보의 원문 묶음을 revision·디스크 해시를 다시 확인한 뒤 상한 안에서 돌려준다.
    인자: request -> 인증된 요청, body -> SymbolBundleRequest
    반환값: SymbolBundle
    작성 날짜: 2026/11/10
    """
    payload = body.model_dump(exclude_none=True)
    return await run_in_threadpool(_symbols(request).read_bundle, payload)
