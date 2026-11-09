"""Runtime Pointer 모델과 오류.

작성일: 2026-11-06
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class RuntimeStoreError(Exception):
    """클래스 이름: RuntimeStoreError
    기능: RuntimeStoreError 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "RUNTIME_ERROR"


class PointerNotFound(RuntimeStoreError):  # noqa: N818
    """클래스 이름: PointerNotFound
    기능: PointerNotFound 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "NOT_FOUND"


class PointerExpired(RuntimeStoreError):  # noqa: N818
    """클래스 이름: PointerExpired
    기능: PointerExpired 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "EXPIRED"


class ScopeForbidden(RuntimeStoreError):  # noqa: N818
    """클래스 이름: ScopeForbidden
    기능: ScopeForbidden 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "FORBIDDEN"


class QuotaExceeded(RuntimeStoreError):  # noqa: N818
    """클래스 이름: QuotaExceeded
    기능: QuotaExceeded 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "QUOTA_EXCEEDED"


class InvalidSelector(RuntimeStoreError):  # noqa: N818
    """클래스 이름: InvalidSelector
    기능: InvalidSelector 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    code = "INVALID_SELECTOR"


@dataclass(frozen=True)
class RuntimePut:
    """클래스 이름: RuntimePut
    기능: RuntimePut 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    workspace_id: str
    session_id: str
    media_type: str
    content: bytes
    ttl_seconds: int = 86_400


@dataclass(frozen=True)
class RuntimeDescriptor:
    """클래스 이름: RuntimeDescriptor
    기능: RuntimeDescriptor 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

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
        """함수 이름: to_dict()
        기능: to_dict 기능을 수행한다.
        인자: 없음
        반환값: dict[str, Any]
        작성 날짜: 2026/11/06
        """
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
    """클래스 이름: ReadResult
    기능: ReadResult 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    content: str
    byte_size: int
    truncated: bool
    next_cursor: str | None
    revision: str = "1"
