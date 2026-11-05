"""인증된 레거시 포인터 앱에서만 사용하는 런타임 경로."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from securecode_context.api.schemas import (
    RuntimePointerCreate,
    RuntimePointerCreated,
    RuntimePointerRead,
    RuntimePointerReadResult,
)
from securecode_context.pointers.limits import DEFAULT_TTL_SECONDS
from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore

router = APIRouter(prefix="/api/v1/pointers", tags=["pointers"])


def runtime_store(request: Request) -> SQLiteRuntimeStore:
    """함수 이름: runtime_store()
    기능: 현재 앱이 기동 시 구성한 저장소를 주입한다.
    인자: request -> 현재 HTTP 요청
    반환값: 레거시 앱의 SQLite 저장소
    작성 날짜: 2026/11/05
    """
    store: SQLiteRuntimeStore = request.app.state.runtime_store
    return store


Store = Annotated[SQLiteRuntimeStore, Depends(runtime_store)]


@router.post("/runtime", response_model=RuntimePointerCreated)
def create_runtime_pointer(request: RuntimePointerCreate, store: Store) -> RuntimePointerCreated:
    """함수 이름: create_runtime_pointer()
    기능: 요청한 범위에 원문을 저장하고 ID와 크기를 반환한다.
    인자: request -> 생성 요청, store -> 저장소
    반환값: 생성한 포인터 정보
    작성 날짜: 2026/11/05
    """
    pointer_id = store.put(
        content=request.content,
        workspace_id=request.workspace_id,
        session_id=request.session_id,
        ttl_seconds=DEFAULT_TTL_SECONDS if request.ttl_seconds is None else request.ttl_seconds,
    )
    return RuntimePointerCreated(
        pointer_id=pointer_id,
        pointer_uri=f"securecode://runtime/{request.workspace_id}/{request.session_id}/{pointer_id}?v=1",
        byte_size=len(request.content.encode()),
    )


@router.post("/runtime/read", response_model=RuntimePointerReadResult)
def read_runtime_pointer(request: RuntimePointerRead, store: Store) -> RuntimePointerReadResult:
    """함수 이름: read_runtime_pointer()
    기능: 원문을 부분 조회하고 권한·만료·잘못된 커서를 적절한 상태 코드로 알린다.
    인자: request -> 조회 요청, store -> 저장소
    반환값: 원문 조각과 다음 커서
    작성 날짜: 2026/11/05
    """
    try:
        result = store.read(
            request.pointer_id,
            request.workspace_id,
            request.session_id,
            cursor=request.cursor,
            max_bytes=request.max_bytes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="pointer not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="pointer scope mismatch") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail="pointer expired") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid read range") from exc
    return RuntimePointerReadResult(
        content=result.content,
        next_cursor=result.next_cursor,
        truncated=result.truncated,
        byte_size=result.byte_size,
    )


@router.get("/runtime")
def list_runtime_pointers(workspace_id: str, session_id: str, store: Store) -> dict[str, list[str]]:
    """함수 이름: list_runtime_pointers()
    기능: 작업 공간과 세션에서 유효한 ID를 조회한다.
    인자: workspace_id/session_id -> 범위, store -> 저장소
    반환값: 포인터 ID 목록
    작성 날짜: 2026/11/05
    """
    return {"pointer_ids": store.list(workspace_id, session_id)}


@router.delete("/runtime/{pointer_id}")
def delete_runtime_pointer(
    pointer_id: str, workspace_id: str, session_id: str, store: Store
) -> dict[str, bool]:
    """함수 이름: delete_runtime_pointer()
    기능: 범위가 일치하는 런타임 원문을 정리한다.
    인자: pointer_id -> ID, workspace_id/session_id -> 범위, store -> 저장소
    반환값: 삭제 완료 여부
    작성 날짜: 2026/11/05
    """
    if not store.delete(pointer_id, workspace_id, session_id):
        raise HTTPException(status_code=404, detail="pointer not found")
    return {"deleted": True}
