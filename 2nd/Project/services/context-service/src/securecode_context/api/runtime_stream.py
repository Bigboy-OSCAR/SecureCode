"""내부 Runtime 스트리밍 저장 경로(/internal/v1/runtime/stream). host 명령 executor가 출력을 받는 대로 보낸다.

본문은 application/octet-stream이며 범위·origin은 헤더로 받는다. 받은 청크를 RuntimeWriter에 바로 쓰므로
전체 출력을 메모리에 모으지 않는다. 연결이 끊기거나 저장이 실패하면 임시 파일·예약을 지운다.
"""

import re

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from securecode_context.api.runtime_errors import translate
from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.models.runtime import RuntimePut, RuntimeStoreError
from securecode_context.pointers.runtime.store import RuntimeStore

router = APIRouter(prefix="/internal/v1/runtime", tags=["runtime-stream"])
_HEADER_VALUE = re.compile(r"[A-Za-z0-9_./+-]{1,128}")


def _header(request: Request, name: str, default: str | None = None) -> str:
    """
    함수 이름: _header()
    기능: 범위·형식 헤더 값을 안전한 문자만으로 제한해 읽는다.
    인자: request -> 인증된 요청, name -> 헤더 이름, default -> 없을 때 값
    반환값: 헤더 값
    작성 날짜: 2026/11/10
    """
    value = request.headers.get(name, default)
    if value is None or not _HEADER_VALUE.fullmatch(value):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, f"{name} 헤더가 올바르지 않습니다.")
    return value


@router.post("/stream")
async def stream_runtime(request: Request) -> dict[str, object]:
    """
    함수 이름: stream_runtime()
    기능: 청크 단위 본문을 객체 상한 안에서 저장하고 descriptor를 돌려준다.
    인자: request -> 인증된 요청(헤더: workspace·session·origin·media type·truncated)
    반환값: pointer_id, pointer_uri, byte_size, descriptor
    작성 날짜: 2026/11/10
    """
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/octet-stream":
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED, "application/octet-stream 본문이 필요합니다."
        )
    put = RuntimePut(
        _header(request, "x-securecode-workspace-id"),
        _header(request, "x-securecode-session-id"),
        _header(request, "x-securecode-media-type", "text/plain"),
        b"",
        origin=_header(request, "x-securecode-origin"),
        truncated_before_storage=_header(request, "x-securecode-truncated", "false") == "true",
    )
    store: RuntimeStore = request.app.state.pointer_store
    try:
        writer = await run_in_threadpool(store.open_writer, put)
    except RuntimeStoreError as error:
        raise translate(error) from None
    try:
        async for chunk in request.stream():
            if chunk:
                await run_in_threadpool(writer.write, chunk)
        descriptor = await run_in_threadpool(writer.commit)
    except RuntimeStoreError as error:
        await run_in_threadpool(writer.abort)
        raise translate(error) from None
    except BaseException:
        # Client disconnect or cancellation: nothing partial stays visible.
        await run_in_threadpool(writer.abort)
        raise
    return {
        "pointer_id": descriptor.pointer.rsplit("/", 1)[-1].split("?", 1)[0],
        "pointer_uri": descriptor.pointer,
        "byte_size": descriptor.byte_size,
        "descriptor": descriptor.to_dict(),
    }
