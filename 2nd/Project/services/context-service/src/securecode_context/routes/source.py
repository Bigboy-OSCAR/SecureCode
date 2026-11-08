from fastapi import APIRouter

router = APIRouter(prefix="/source", tags=["source"])

@router.get("/read")
def read_source(pointer: str, start_line: int = 1, end_line: int = 100):
    return {"pointer": pointer, "start_line": start_line, "end_line": end_line, "content": ""}
