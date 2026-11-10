"""Secure Context Service FastAPI Application with mandatory Auth Header verification."""

from fastapi import FastAPI, HTTPException, Header, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from securecode_context.context.policy import ContextSelectorPolicy

app = FastAPI(title="SecureCode Context Service", version="1.0.0")

class ContextSelectRequest(BaseModel):
    candidates: List[Dict[str, Any]]
    max_tokens: Optional[int] = 4000

def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED_MISSING_OR_INVALID_TOKEN")
    return authorization

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "context-service"}

@app.post("/v1/context/select")
def select_context(req: ContextSelectRequest, token: str = Depends(verify_token)):
    policy = ContextSelectorPolicy()
    plan = policy.select(req.candidates, max_tokens=req.max_tokens)
    return {
        "selected_uris": plan.selected_uris,
        "omitted": [{"uri": o.uri, "reason": o.reason, "reason_code": o.reason_code} for o in plan.omitted],
        "total_tokens": plan.total_tokens,
        "used_tokens": plan.used_tokens
    }
