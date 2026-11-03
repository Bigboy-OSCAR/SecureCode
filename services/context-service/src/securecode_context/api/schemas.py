from pydantic import BaseModel


class RuntimePointerCreate(BaseModel):
    workspace_id: str
    session_id: str
    content: str
    ttl_seconds: int | None = None


class RuntimePointerCreated(BaseModel):
    pointer_id: str
    pointer_uri: str
    byte_size: int


class RuntimePointerRead(BaseModel):
    pointer_id: str
    workspace_id: str
    session_id: str
    cursor: int = 0
    max_bytes: int = 32 * 1024


class RuntimePointerReadResult(BaseModel):
    content: str
    next_cursor: int | None
    truncated: bool
    byte_size: int
