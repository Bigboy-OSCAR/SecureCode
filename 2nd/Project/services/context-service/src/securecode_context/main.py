"""Context Service Fast API Entry Point exposing REST Routes for D8 & Host SDK."""

from fastapi import FastAPI, HTTPException, Header
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from securecode_context.context.policy import ContextSelectorPolicy

app = FastAPI(title="SecureCode Context Service", version="1.0.0")

class ContextSelectRequest(BaseModel):
    candidates: List[Dict[str, Any]]
    max_tokens: Optional[int] = 4000

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "context-service"}

@app.post("/v1/context/select")
def select_context(req: ContextSelectRequest, authorization: Optional[str] = Header(None)):
    policy = ContextSelectorPolicy()
    plan = policy.select(req.candidates, max_tokens=req.max_tokens)
    return {
        "selected_uris": plan.selected_uris,
        "omitted": [{"uri": o.uri, "reason": o.reason, "reason_code": o.reason_code} for o in plan.omitted],
        "total_tokens": plan.total_tokens,
        "used_tokens": plan.used_tokens
    }
