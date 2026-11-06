"""Runtime Pointer 모델과 오류.

작성일: 2026-11-06
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class RuntimeStoreError(Exception):
    code = "RUNTIME_ERROR"


class PointerNotFound(RuntimeStoreError):  # noqa: N818
    code = "NOT_FOUND"


class PointerExpired(RuntimeStoreError):  # noqa: N818
    code = "EXPIRED"


class ScopeForbidden(RuntimeStoreError):  # noqa: N818
    code = "FORBIDDEN"


class QuotaExceeded(RuntimeStoreError):  # noqa: N818
    code = "BUDGET_EXCEEDED"


class InvalidSelector(RuntimeStoreError):  # noqa: N818
    code = "INVALID_SELECTOR"


@dataclass(frozen=True)
class RuntimePut:
    workspace_id: str
    session_id: str
    media_type: str
    content: bytes
    ttl_seconds: int = 86_400


@dataclass(frozen=True)
class RuntimeDescriptor:
    pointer: str
    workspace_id: str
    session_id: str
    media_type: str
    byte_size: int
    checksum: str
    created_at: datetime
    expires_at: datetime
    preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pointer": self.pointer,
            "kind": "runtime",
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "preview": self.preview,
            "expires_at": self.expires_at.isoformat(),
            "available_operations": ["read", "search", "delete"],
        }


@dataclass(frozen=True)
class ReadResult:
    content: str
    byte_size: int
    truncated: bool
    next_cursor: str | None
    revision: str = "1"
