from fastapi import APIRouter

router = APIRouter(prefix="/context", tags=["context"])

@router.post("/select")
def select_context(payload: dict):
    return {"selected": [], "used_tokens": 0, "omitted": []}
