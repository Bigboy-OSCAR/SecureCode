"""Runtime Pointer 저장소.

작성일: 2026-11-06
"""

import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..models.runtime import (
    InvalidSelector,
    PointerExpired,
    PointerNotFound,
    QuotaExceeded,
    ReadResult,
    RuntimeDescriptor,
    RuntimePut,
    ScopeForbidden,
)
from .blob import BlobStore
from .search import search_blob

MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_SESSION_BYTES = 128 * 1024 * 1024
MAX_PREVIEW_BYTES = 512


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RuntimeStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._db_path = root / "runtime.sqlite3"
        self._blobs = BlobStore(root / "blobs")
        self._lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS runtime_pointers (
                pointer_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                media_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                blob_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                preview TEXT NOT NULL
            )
        """)
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_scope ON runtime_pointers(workspace_id, session_id)"
        )
        self._connection.commit()

    @staticmethod
    def _validate_scope(workspace_id: str, session_id: str) -> None:
        if not workspace_id or not session_id:
            raise ScopeForbidden("workspace_id와 session_id는 필수입니다")

    def _preview(self, content: bytes) -> str:
        return content[:MAX_PREVIEW_BYTES].decode("utf-8", errors="replace")

    def put(self, request: RuntimePut) -> RuntimeDescriptor:
        self._validate_scope(request.workspace_id, request.session_id)
        if len(request.content) > MAX_OBJECT_BYTES:
            raise QuotaExceeded("객체 용량 한도를 초과했습니다")
        if request.ttl_seconds <= 0:
            raise InvalidSelector("TTL은 양수여야 합니다")
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(SUM(byte_size), 0) FROM runtime_pointers WHERE workspace_id = ? AND session_id = ?",
                (request.workspace_id, request.session_id),
            ).fetchone()
            if int(row[0]) + len(request.content) > MAX_SESSION_BYTES:
                raise QuotaExceeded("세션 용량 한도를 초과했습니다")
            pointer_id = str(uuid.uuid4())
            now = _utc_now()
            expires_at = now + timedelta(seconds=request.ttl_seconds)
            blob_path, checksum = self._blobs.write(
                request.workspace_id, request.session_id, pointer_id, request.content
            )
            self._connection.execute(
                """INSERT INTO runtime_pointers (
                    pointer_id, workspace_id, session_id, media_type, byte_size,
                    checksum, blob_path, created_at, expires_at, preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pointer_id,
                    request.workspace_id,
                    request.session_id,
                    request.media_type,
                    len(request.content),
                    checksum,
                    str(blob_path),
                    now.isoformat(),
                    expires_at.isoformat(),
                    self._preview(request.content),
                ),
            )
            self._connection.commit()
        return self.stat(request.workspace_id, request.session_id, pointer_id)

    def _load(self, workspace_id: str, session_id: str, pointer_id: str) -> Any:
        self._validate_scope(workspace_id, session_id)
        row = self._connection.execute(
            """SELECT * FROM runtime_pointers WHERE pointer_id = ? AND workspace_id = ? AND session_id = ?""",
            (pointer_id, workspace_id, session_id),
        ).fetchone()
        if row is None:
            raise PointerNotFound("포인터를 찾을 수 없습니다")
        if datetime.fromisoformat(row["expires_at"]) <= _utc_now():
            raise PointerExpired("포인터가 만료되었습니다")
        return row

    def stat(self, workspace_id: str, session_id: str, pointer_id: str) -> RuntimeDescriptor:
        row = self._load(workspace_id, session_id, pointer_id)
        return RuntimeDescriptor(
            pointer=f"securecode://runtime/{workspace_id}/{session_id}/{pointer_id}?v=1",
            workspace_id=row["workspace_id"],
            session_id=row["session_id"],
            media_type=row["media_type"],
            byte_size=row["byte_size"],
            checksum=row["checksum"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            preview=row["preview"],
        )

    def list(
        self, workspace_id: str, session_id: str, limit: int = 100, cursor: str | None = None
    ) -> dict[str, Any]:
        self._validate_scope(workspace_id, session_id)
        query = "SELECT pointer_id FROM runtime_pointers WHERE workspace_id = ? AND session_id = ? AND expires_at > ?"
        params: list[Any] = [workspace_id, session_id, _utc_now().isoformat()]
        if cursor:
            query += " AND pointer_id > ?"
            params.append(cursor)
        query += " ORDER BY pointer_id LIMIT ?"
        params.append(limit + 1)
        rows = self._connection.execute(query, params).fetchall()
        has_more = len(rows) > limit
        ids = [row["pointer_id"] for row in rows[:limit]]
        return {
            "pointers": [self.stat(workspace_id, session_id, pid).to_dict() for pid in ids],
            "has_more": has_more,
            "next_cursor": ids[-1] if has_more and ids else None,
        }

    def read(
        self,
        workspace_id: str,
        session_id: str,
        pointer_id: str,
        offset: int = 0,
        max_bytes: int = 16_384,
    ) -> ReadResult:
        if offset < 0 or max_bytes <= 0:
            raise InvalidSelector("offset과 max_bytes가 올바르지 않습니다")
        row = self._load(workspace_id, session_id, pointer_id)
        content = self._blobs.read(Path(row["blob_path"]))
        end = min(offset + max_bytes, len(content))
        chunk = content[offset:end]
        return ReadResult(
            content=chunk.decode("utf-8", errors="replace"),
            byte_size=len(chunk),
            truncated=end < len(content),
            next_cursor=str(end) if end < len(content) else None,
        )

    def search(
        self,
        workspace_id: str,
        session_id: str,
        pointer_id: str,
        pattern: str,
        max_matches: int = 100,
        max_scan_bytes: int = 1_048_576,
    ) -> dict[str, Any]:
        if not pattern:
            raise InvalidSelector("검색 패턴이 비어 있습니다")
        row = self._load(workspace_id, session_id, pointer_id)
        content = self._blobs.read(Path(row["blob_path"]))
        return search_blob(content, pattern, max_matches, max_scan_bytes)

    def delete(self, workspace_id: str, session_id: str, pointer_id: str) -> None:
        self._validate_scope(workspace_id, session_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT blob_path FROM runtime_pointers WHERE pointer_id = ? AND workspace_id = ? AND session_id = ?",
                (pointer_id, workspace_id, session_id),
            ).fetchone()
            if row is None:
                return
            self._blobs.delete(Path(row["blob_path"]))
            self._connection.execute(
                "DELETE FROM runtime_pointers WHERE pointer_id = ?", (pointer_id,)
            )
            self._connection.commit()

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        self._validate_scope(workspace_id, session_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT pointer_id, blob_path FROM runtime_pointers WHERE workspace_id = ? AND session_id = ?",
                (workspace_id, session_id),
            ).fetchall()
            for row in rows:
                self._blobs.delete(Path(row["blob_path"]))
            self._connection.execute(
                "DELETE FROM runtime_pointers WHERE workspace_id = ? AND session_id = ?",
                (workspace_id, session_id),
            )
            self._connection.commit()
            self._blobs.remove_session(workspace_id, session_id)
            return len(rows)

    def sweep_expired(self) -> int:
        now = _utc_now().isoformat()
        with self._lock:
            rows = self._connection.execute(
                "SELECT pointer_id, blob_path FROM runtime_pointers WHERE expires_at <= ?", (now,)
            ).fetchall()
            for row in rows:
                self._blobs.delete(Path(row["blob_path"]))
            self._connection.execute("DELETE FROM runtime_pointers WHERE expires_at <= ?", (now,))
            self._connection.commit()
            return len(rows)

    def close(self) -> None:
        self._connection.close()
