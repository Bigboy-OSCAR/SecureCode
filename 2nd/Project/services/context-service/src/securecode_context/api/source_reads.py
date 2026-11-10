"""내부 Source 부분 읽기·검색 경로(/internal/v1/source/read|search).

host 공개 route(3.6)가 인증된 workspace를 넣어 호출한다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from securecode_context.api.selector_body import SelectorBody, to_selector
from securecode_context.api.source_wire import read_result, search_result
from securecode_context.pdf.tools import PdfService
from securecode_context.pointers.limits import MAX_READ_BYTES, MAX_READ_TOKENS
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.media import PDF_MEDIA
from securecode_context.pointers.source.read_models import ReadRequest, SearchRequest

router = APIRouter(prefix="/internal/v1/source", tags=["source-reads"])
WorkspaceIdField = Annotated[str, Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")]
PointerField = Annotated[str, Field(min_length=1, max_length=512)]
CursorField = Annotated[str | None, Field(default=None, min_length=1, max_length=512)]


class ReadBody(BaseModel):
    """
    클래스 이름: ReadBody
    기능: PointerReadRequest와 인증된 workspace.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField
    pointer: PointerField
    selector: SelectorBody | None = None
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)
    max_tokens: int = Field(default=MAX_READ_TOKENS, ge=1, le=MAX_READ_TOKENS)
    cursor: CursorField


class SearchBody(BaseModel):
    """
    클래스 이름: SearchBody
    기능: PointerSearchRequest와 인증된 workspace.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField
    pointer: PointerField
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)
    max_tokens: int = Field(default=MAX_READ_TOKENS, ge=1, le=MAX_READ_TOKENS)
    cursor: CursorField


def _adapter(request: Request) -> SourceAdapter:
    """
    함수 이름: _adapter()
    기능: 앱 수명 동안 공유하는 Source adapter를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: SourceAdapter
    작성 날짜: 2026/11/10
    """
    adapter: SourceAdapter = request.app.state.source_adapter
    return adapter


@router.post("/read")
async def read_source(request: Request, body: ReadBody) -> dict[str, object]:
    """
    함수 이름: read_source()
    기능: 등록 원본의 요청 구간을 bytes/tokens 상한 안에서 읽는다.
    인자: request -> 인증된 요청, body -> 읽기 요청
    반환값: PointerReadResult
    작성 날짜: 2026/11/10
    """
    read = ReadRequest(
        body.pointer, to_selector(body.selector), body.max_bytes, body.max_tokens, body.cursor
    )
    if read.selector is not None and read.selector.kind == "pdf_page":
        pdf: PdfService = request.app.state.pdf
        outcome = await run_in_threadpool(pdf.read, body.workspace_id, read)
    else:
        outcome = await run_in_threadpool(_adapter(request).reader.read, body.workspace_id, read)
    return read_result(body.pointer, outcome)


@router.post("/search")
async def search_source(request: Request, body: SearchBody) -> dict[str, object]:
    """
    함수 이름: search_source()
    기능: 등록 원본에서 리터럴 검색어를 찾는다.
    인자: request -> 인증된 요청, body -> 검색 요청
    반환값: PointerSearchResult(일치 없음은 빈 matches)
    작성 날짜: 2026/11/10
    """
    adapter = _adapter(request)
    record = await run_in_threadpool(adapter.registry.stat, body.workspace_id, body.pointer)
    if record.media_type == PDF_MEDIA:
        pdf: PdfService = request.app.state.pdf
        caps = (body.max_bytes, body.max_tokens)
        args = (body.workspace_id, body.pointer, body.query, body.limit, caps)
        return await run_in_threadpool(pdf.search, *args)
    search = SearchRequest(
        body.pointer, body.query, body.limit, body.max_bytes, body.max_tokens, body.cursor
    )
    outcome = await run_in_threadpool(adapter.searcher.search, body.workspace_id, search)
    return search_result(body.pointer, outcome)
