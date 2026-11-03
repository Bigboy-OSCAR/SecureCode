from fastapi import APIRouter, HTTPException

from securecode_context.api.schemas import (
    RuntimePointerCreate,
    RuntimePointerCreated,
    RuntimePointerRead,
    RuntimePointerReadResult,
)
from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore

router = APIRouter(prefix="/api/v1/pointers", tags=["pointers"])

store = SQLiteRuntimeStore()


@router.post("/runtime", response_model=RuntimePointerCreated)
def create_runtime_pointer(request: RuntimePointerCreate):
    pointer_id = store.put(
        content=request.content,
        workspace_id=request.workspace_id,
        session_id=request.session_id,
        ttl_seconds=request.ttl_seconds or 60 * 60 * 24,
    )

    pointer_uri = (
        f"securecode://runtime/"
        f"{request.workspace_id}/{request.session_id}/{pointer_id}"
    )

    return RuntimePointerCreated(
        pointer_id=pointer_id,
        pointer_uri=pointer_uri,
        byte_size=len(request.content.encode("utf-8")),
    )


@router.post("/runtime/read", response_model=RuntimePointerReadResult)
def read_runtime_pointer(request: RuntimePointerRead):
    try:
        result = store.read(
            pointer_id=request.pointer_id,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            cursor=request.cursor,
            max_bytes=request.max_bytes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="pointer not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail="pointer expired") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RuntimePointerReadResult(
        content=result.content,
        next_cursor=result.next_cursor,
        truncated=result.truncated,
        byte_size=result.byte_size,
    )


@router.get("/runtime")
def list_runtime_pointers(workspace_id: str, session_id: str):
    return {
        "pointer_ids": store.list(
            workspace_id=workspace_id,
            session_id=session_id,
        )
    }


@router.delete("/runtime/{pointer_id}")
def delete_runtime_pointer(
    pointer_id: str,
    workspace_id: str,
    session_id: str,
):
    deleted = store.delete(
        pointer_id=pointer_id,
        workspace_id=workspace_id,
        session_id=session_id,
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="pointer not found")

    return {"deleted": True}
