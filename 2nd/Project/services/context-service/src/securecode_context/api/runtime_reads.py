"""내부 Runtime 계약형 읽기·검색·목록 경로(/internal/v1/runtime/read|search|list).

host는 인증한 workspace·session을 넣어 호출한다. 응답은 PointerReadResult·PointerSearchResult·
PointerListResult 형식이며 bytes/token 상한과 범위에 묶인 cursor를 쓴다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from securecode_context.api.runtime_errors import translate
from securecode_context.api.runtime_wire import list_result, read_result, search_result
from securecode_context.api.selector_body import SelectorBody, to_selector
from securecode_context.pointers.limits import MAX_READ_BYTES, MAX_READ_TOKENS
from securecode_context.pointers.models.runtime import RuntimeStoreError
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.text.models import ReadRequest, SearchRequest

router = APIRouter(prefix="/internal/v1/runtime", tags=["runtime-reads"])
ScopeField = Annotated[str, Field(min_length=1, max_length=128)]
CursorField = Annotated[str | None, Field(default=None, min_length=1, max_length=512)]


class _ScopedBody(BaseModel):
    """
    클래스 이름: _ScopedBody
    기능: 인증된 workspace·session 범위. 정의되지 않은 필드는 거절한다.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: ScopeField
    session_id: ScopeField


class ReadBody(_ScopedBody):
    """
    클래스 이름: ReadBody
    기능: PointerReadRequest와 범위.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    pointer: str = Field(min_length=1, max_length=512)
    selector: SelectorBody | None = None
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)
    max_tokens: int = Field(default=MAX_READ_TOKENS, ge=1, le=MAX_READ_TOKENS)
    cursor: CursorField


class SearchBody(_ScopedBody):
    """
    클래스 이름: SearchBody
    기능: PointerSearchRequest와 범위.
    작성 날짜: 2026/11/10
    """

    schema_version: Literal["1"]
    pointer: str = Field(min_length=1, max_length=512)
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)
    max_tokens: int = Field(default=MAX_READ_TOKENS, ge=1, le=MAX_READ_TOKENS)
    cursor: CursorField


class ListBody(_ScopedBody):
    """
    클래스 이름: ListBody
    기능: PointerListQuery(kind=runtime)와 범위.
    작성 날짜: 2026/11/10
    """

    kind: Literal["runtime"] = "runtime"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: CursorField


def _reader(request: Request) -> RuntimeReader:
    """
    함수 이름: _reader()
    기능: 앱이 구성한 RuntimeReader를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: RuntimeReader
    작성 날짜: 2026/11/10
    """
    reader: RuntimeReader = request.app.state.runtime_reader
    return reader


@router.post("/read")
async def read_runtime(request: Request, body: ReadBody) -> dict[str, object]:
    """
    함수 이름: read_runtime()
    기능: 저장된 출력의 selector 구간을 상한 안에서 읽는다.
    인자: request -> 인증된 요청, body -> 읽기 요청
    반환값: PointerReadResult
    작성 날짜: 2026/11/10
    """
    read = ReadRequest(
        body.pointer, to_selector(body.selector), body.max_bytes, body.max_tokens, body.cursor
    )
    try:
        outcome = await run_in_threadpool(
            _reader(request).read, body.workspace_id, body.session_id, read
        )
    except RuntimeStoreError as error:
        raise translate(error) from None
    return read_result(body.pointer, outcome)


@router.post("/search")
async def search_runtime(request: Request, body: SearchBody) -> dict[str, object]:
    """
    함수 이름: search_runtime()
    기능: 저장된 출력에서 리터럴을 찾아 줄 출처와 함께 돌려준다.
    인자: request -> 인증된 요청, body -> 검색 요청
    반환값: PointerSearchResult(일치 없음은 빈 matches)
    작성 날짜: 2026/11/10
    """
    search = SearchRequest(
        body.pointer, body.query, body.limit, body.max_bytes, body.max_tokens, body.cursor
    )
    try:
        outcome = await run_in_threadpool(
            _reader(request).search, body.workspace_id, body.session_id, search
        )
    except RuntimeStoreError as error:
        raise translate(error) from None
    return search_result(body.pointer, outcome)


@router.post("/list")
async def list_runtime(request: Request, body: ListBody) -> dict[str, object]:
    """
    함수 이름: list_runtime()
    기능: 세션의 저장 출력 목록을 최대 100개·64 KiB씩 돌려준다.
    인자: request -> 인증된 요청, body -> 목록 요청
    반환값: PointerListResult
    작성 날짜: 2026/11/10
    """
    store: RuntimeStore = request.app.state.pointer_store
    try:
        page = await run_in_threadpool(
            store.list_pointers, body.workspace_id, body.session_id, body.limit, body.cursor
        )
    except RuntimeStoreError as error:
        raise translate(error) from None
    return list_result(body.workspace_id, body.limit, page)
