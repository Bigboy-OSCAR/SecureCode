"""Runtime Pointer 저장소.

작성일: 2026-11-06
"""

import threading
import uuid
from datetime import datetime, timedelta
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
from .db import MAX_OBJECT_BYTES, MAX_PREVIEW_BYTES, MAX_SESSION_BYTES, open_connection
from .db import utc_now as _utc_now
from .search import search_blob


class RuntimeStore:
    """클래스 이름: RuntimeStore
    기능: RuntimeStore 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    def __init__(self, root: Path | None = None) -> None:
        """함수 이름: __init__()
        기능: __init__ 기능을 수행한다.
        인자: root
        반환값: None
        작성 날짜: 2026/11/06
        """
        if root is None:
            root = Path(".securecode/runtime")
        self._root = root
        self._db_path = root / "runtime.sqlite3"
        self._blobs = BlobStore(root / "blobs")
        self._lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = open_connection(self._db_path)

    @staticmethod
    def _validate_scope(workspace_id: str, session_id: str) -> None:
        """함수 이름: _validate_scope()
        기능: _validate_scope 기능을 수행한다.
        인자: workspace_id, session_id
        반환값: None
        작성 날짜: 2026/11/06
        """
        if not workspace_id or not session_id:
            raise ScopeForbidden("workspace_id와 session_id는 필수입니다")

    def _preview(self, content: bytes) -> str:
        """함수 이름: _preview()
        기능: _preview 기능을 수행한다.
        인자: content
        반환값: str
        작성 날짜: 2026/11/06
        """
        return content[:MAX_PREVIEW_BYTES].decode("utf-8", errors="replace")

    def put(self, request: RuntimePut) -> RuntimeDescriptor:
        """함수 이름: put()
        기능: put 기능을 수행한다.
        인자: request
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: _load()
        기능: _load 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id
        반환값: Any
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: stat()
        기능: stat 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: list()
        기능: list 기능을 수행한다.
        인자: workspace_id, session_id, limit, cursor
        반환값: dict[str, Any]
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: read()
        기능: read 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id, offset, max_bytes
        반환값: ReadResult
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: search()
        기능: search 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id, pattern, max_matches, max_scan_bytes
        반환값: dict[str, Any]
        작성 날짜: 2026/11/06
        """
        if not pattern:
            raise InvalidSelector("검색 패턴이 비어 있습니다")
        row = self._load(workspace_id, session_id, pointer_id)
        content = self._blobs.read(Path(row["blob_path"]))
        return search_blob(content, pattern, max_matches, max_scan_bytes)

    def delete(self, workspace_id: str, session_id: str, pointer_id: str) -> None:
        """함수 이름: delete()
        기능: delete 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id
        반환값: None
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: clear_session()
        기능: clear_session 기능을 수행한다.
        인자: workspace_id, session_id
        반환값: int
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: sweep_expired()
        기능: sweep_expired 기능을 수행한다.
        인자: 없음
        반환값: int
        작성 날짜: 2026/11/06
        """
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
        """함수 이름: close()
        기능: close 기능을 수행한다.
        인자: 없음
        반환값: None
        작성 날짜: 2026/11/06
        """
        self._connection.close()
