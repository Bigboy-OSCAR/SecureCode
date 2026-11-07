"""내부 Runtime Pointer 경로. host의 afterTool hook이 큰 도구 출력을 저장·조회한다(4.3 RuntimeStore 연결)."""

import re

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.models.runtime import RuntimePut, RuntimeStoreError
from securecode_context.pointers.runtime.db import MAX_OBJECT_BYTES
from securecode_context.pointers.runtime.store import RuntimeStore

# One input byte can occupy six JSON bytes (e.g. an escaped control character).
MAX_ENVELOPE_BYTES = 6 * MAX_OBJECT_BYTES + 4096
MAX_READ_BYTES = 16 * 1024
_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}"
_URI = re.compile(
    rf"securecode://runtime/(?P<workspace>{_SEGMENT})/(?P<session>{_SEGMENT})/"
    r"(?P<pointer>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\?v=1"
)

router = APIRouter(prefix="/internal/v1/runtime", tags=["runtime-pointers"])


class ScopeBody(BaseModel):
    """
    클래스 이름: ScopeBody
    기능: 작업 공간과 세션 범위를 담는 요청 본문 기반 모델. 정의되지 않은 필드는 거절한다.
    작성 날짜: 2026/11/07
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)


class PutBody(ScopeBody):
    """
    클래스 이름: PutBody
    기능: 도구 출력 원문 저장 요청.
    작성 날짜: 2026/11/07
    """

    content: str
    media_type: str = Field(default="text/plain", min_length=1, max_length=128)


class PointerBody(ScopeBody):
    """
    클래스 이름: PointerBody
    기능: 포인터 URI를 가리키는 요청 기반 모델.
    작성 날짜: 2026/11/07
    """

    pointer: str = Field(min_length=1, max_length=512)


class ReadBody(PointerBody):
    """
    클래스 이름: ReadBody
    기능: 바이트 오프셋 기반 부분 조회 요청.
    작성 날짜: 2026/11/07
    """

    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)


class SearchBody(PointerBody):
    """
    클래스 이름: SearchBody
    기능: 포인터 원문 안의 문자열 검색 요청.
    작성 날짜: 2026/11/07
    """

    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=100, ge=1, le=100)


def _store(request: Request) -> RuntimeStore:
    """
    함수 이름: _store()
    기능: 앱이 구성한 4.3 RuntimeStore를 꺼낸다.
    인자: request -> 현재 요청
    반환값: RuntimeStore
    작성 날짜: 2026/11/07
    """
    store: RuntimeStore = request.app.state.pointer_store
    return store


def _translate(error: RuntimeStoreError) -> ServiceError:
    """
    함수 이름: _translate()
    기능: 저장소 오류 코드를 공용 ErrorCode로 옮긴다. 알 수 없는 코드는 내부 오류로 처리한다.
    인자: error -> 4.3 저장소 오류
    반환값: ServiceError
    작성 날짜: 2026/11/07
    """
    try:
        code = ErrorCode(error.code)
    except ValueError:
        code = ErrorCode.INTERNAL_ERROR
    return ServiceError(code, str(error))


async def _read_body[Body: BaseModel](request: Request, model: type[Body], limit: int) -> Body:
    """
    함수 이름: _read_body()
    기능: JSON 본문을 상한 안에서 읽고 모델로 검증한다.
    인자: request -> 인증된 요청, model -> 검증 모델, limit -> 본문 바이트 상한
    반환값: 검증된 모델
    작성 날짜: 2026/11/07
    """
    media_type = (
        request.headers.get("content-type", "application/json").split(";", 1)[0].strip().lower()
    )
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "JSON 본문이 필요합니다.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise ServiceError(ErrorCode.PAYLOAD_TOO_LARGE, "요청 본문이 너무 큽니다.")
        data.extend(chunk)
    try:
        return model.model_validate_json(data)
    except ValidationError:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "요청 형식이 올바르지 않습니다.") from None


def _pointer_id(body: PointerBody) -> str:
    """
    함수 이름: _pointer_id()
    기능: 포인터 URI를 파싱해 요청 범위와 일치하는 ID만 돌려준다.
    인자: body -> 범위와 포인터를 담은 요청
    반환값: 포인터 ID
    작성 날짜: 2026/11/07
    """
    match = _URI.fullmatch(body.pointer)
    if match is None:
        raise ServiceError(ErrorCode.INVALID_POINTER, "포인터 형식이 올바르지 않습니다.")
    if match["workspace"] != body.workspace_id or match["session"] != body.session_id:
        raise ServiceError(ErrorCode.FORBIDDEN, "포인터가 이 범위에 속하지 않습니다.")
    return match["pointer"]


@router.post("/pointers")
async def put_pointer(request: Request) -> dict[str, object]:
    """
    함수 이름: put_pointer()
    기능: 도구 출력 원문을 세션 범위에 저장하고 ID와 크기를 돌려준다.
    인자: request -> 인증된 요청
    반환값: pointer_id, pointer_uri, byte_size
    작성 날짜: 2026/11/07
    """
    body = await _read_body(request, PutBody, MAX_ENVELOPE_BYTES)
    try:
        content = body.content.encode("utf-8")
    except UnicodeEncodeError:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "올바른 UTF-8 텍스트가 아닙니다.") from None
    put = RuntimePut(body.workspace_id, body.session_id, body.media_type, content)
    try:
        descriptor = await run_in_threadpool(_store(request).put, put)
    except RuntimeStoreError as error:
        raise _translate(error) from None
    pointer_id = descriptor.pointer.split("/")[-1].split("?", 1)[0]
    return {"pointer_id": pointer_id, "pointer_uri": descriptor.pointer, "byte_size": len(content)}


@router.post("/pointers/read")
async def read_pointer(request: Request) -> dict[str, object]:
    """
    함수 이름: read_pointer()
    기능: 포인터 원문의 일부를 바이트 오프셋 기준으로 조회한다.
    인자: request -> 인증된 요청
    반환값: 원문 조각과 다음 커서
    작성 날짜: 2026/11/07
    """
    body = await _read_body(request, ReadBody, 64 * 1024)
    pointer_id = _pointer_id(body)
    try:
        result = await run_in_threadpool(
            _store(request).read,
            body.workspace_id,
            body.session_id,
            pointer_id,
            body.offset,
            body.max_bytes,
        )
    except RuntimeStoreError as error:
        raise _translate(error) from None
    return {
        "pointer": body.pointer,
        "content": result.content,
        "byte_size": result.byte_size,
        "truncated": result.truncated,
        "next_cursor": result.next_cursor,
        "revision": result.revision,
    }


@router.post("/pointers/search")
async def search_pointer(request: Request) -> dict[str, object]:
    """
    함수 이름: search_pointer()
    기능: 포인터 원문에서 문자열을 찾아 줄 번호와 함께 돌려준다.
    인자: request -> 인증된 요청
    반환값: 포인터와 검색 결과
    작성 날짜: 2026/11/07
    """
    body = await _read_body(request, SearchBody, 64 * 1024)
    pointer_id = _pointer_id(body)
    try:
        result = await run_in_threadpool(
            _store(request).search,
            body.workspace_id,
            body.session_id,
            pointer_id,
            body.query,
            body.limit,
        )
    except RuntimeStoreError as error:
        raise _translate(error) from None
    return {"pointer": body.pointer, **result}


@router.post("/pointers/delete")
async def delete_pointer(request: Request) -> dict[str, bool]:
    """
    함수 이름: delete_pointer()
    기능: 범위가 일치하는 포인터 하나를 지운다. 이미 없어도 성공으로 본다.
    인자: request -> 인증된 요청
    반환값: 삭제 완료 여부
    작성 날짜: 2026/11/07
    """
    body = await _read_body(request, PointerBody, 64 * 1024)
    pointer_id = _pointer_id(body)
    try:
        await run_in_threadpool(
            _store(request).delete, body.workspace_id, body.session_id, pointer_id
        )
    except RuntimeStoreError as error:
        raise _translate(error) from None
    return {"deleted": True}


@router.post("/sessions/clear")
async def clear_session(request: Request) -> dict[str, int]:
    """
    함수 이름: clear_session()
    기능: 세션 종료 시 해당 세션의 포인터를 모두 지운다.
    인자: request -> 인증된 요청
    반환값: 지운 개수
    작성 날짜: 2026/11/07
    """
    body = await _read_body(request, ScopeBody, 64 * 1024)
    try:
        count = await run_in_threadpool(
            _store(request).clear_session, body.workspace_id, body.session_id
        )
    except RuntimeStoreError as error:
        raise _translate(error) from None
    return {"deleted": count}
