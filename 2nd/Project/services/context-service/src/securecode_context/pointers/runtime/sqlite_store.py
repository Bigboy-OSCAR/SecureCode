"""SQLite 기반 세션별 Runtime Pointer 저장소."""

import os
import sqlite3
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from securecode_context.pointers.limits import (
    DEFAULT_TTL_SECONDS,
    MAX_READ_BYTES,
    check_read_limit,
    check_ttl,
    utf8_prefix,
)


@dataclass(frozen=True)
class ReadResult:
    """클래스 이름: ReadResult
    기능: UTF-8 원문 조각과 다음 바이트 위치를 담는다.
    작성 날짜: 2026/11/05
    """

    content: str
    next_cursor: int | None
    truncated: bool
    byte_size: int


class SQLiteRuntimeStore:
    """클래스 이름: SQLiteRuntimeStore
    기능: 세션 원문을 트랜잭션으로 저장하고 인가된 요청에 제한된 범위만 반환한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, db_path: str | Path = "runtime_pointers.db") -> None:
        """함수 이름: __init__()
        기능: 기존 데이터베이스를 열거나 필요한 테이블을 생성한다.
        인자: db_path -> SQLite 파일 위치
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.db_path = Path(db_path).absolute()
        if self.db_path.is_symlink() or self.db_path.is_junction():
            raise PermissionError("runtime database must be a regular file")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(self.db_path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PermissionError("runtime database must be a regular file")
        finally:
            os.close(fd)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runtime_pointers (
                    pointer_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    content BLOB NOT NULL, byte_size INTEGER NOT NULL,
                    created_at REAL NOT NULL, expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_scope
                    ON runtime_pointers (workspace_id, session_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_expiry ON runtime_pointers (expires_at);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """함수 이름: _connect()
        기능: 요청 단위로 트랜잭션을 마치고 연결도 닫는다.
        인자: 없음
        반환값: 현재 작업의 SQLite 연결
        작성 날짜: 2026/11/05
        """
        if not stat.S_ISREG(self.db_path.lstat().st_mode):
            raise PermissionError("runtime database must be a regular file")
        uri = self.db_path.as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def put(
        self,
        content: str,
        workspace_id: str,
        session_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> str:
        """함수 이름: put()
        기능: 세션 원문과 수명을 함께 저장하고 만료 원문을 정리한다.
        인자: content -> 원문, workspace_id/session_id -> 범위, ttl_seconds -> 수명
        반환값: 새 런타임 ID
        작성 날짜: 2026/11/05
        """
        check_ttl(ttl_seconds)
        pointer_id = str(uuid.uuid4())
        now = time.time()
        encoded = content.encode()
        with self._connect() as connection:
            connection.execute("DELETE FROM runtime_pointers WHERE expires_at <= ?", (now,))
            connection.execute(
                """INSERT INTO runtime_pointers
                (pointer_id, workspace_id, session_id, content, byte_size, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    pointer_id,
                    workspace_id,
                    session_id,
                    encoded,
                    len(encoded),
                    now,
                    now + ttl_seconds,
                ),
            )
        return pointer_id

    def read(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
        cursor: int = 0,
        max_bytes: int = MAX_READ_BYTES,
    ) -> ReadResult:
        """함수 이름: read()
        기능: 인가·만료 판정과 같은 시점의 BLOB 조각을 조회하고 다음 문자 경계로 이동한다.
        인자: pointer_id -> ID, workspace_id/session_id -> 범위, cursor/max_bytes -> 바이트 위치·상한
        반환값: 원문 조각과 다음 위치
        작성 날짜: 2026/11/05
        """
        check_read_limit(max_bytes)
        if not 0 <= cursor < 2**63 - 1:
            raise ValueError("invalid cursor")
        now = time.time()
        with self._connect() as connection:
            item = connection.execute(
                """SELECT workspace_id, session_id, expires_at, byte_size,
                   CASE WHEN workspace_id = ? AND session_id = ? AND expires_at > ?
                        THEN substr(content, ?, ?) END AS chunk
                   FROM runtime_pointers WHERE pointer_id = ?""",
                (workspace_id, session_id, now, cursor + 1, max_bytes, pointer_id),
            ).fetchone()
        if item is None:
            raise KeyError("runtime pointer not found")
        if item["workspace_id"] != workspace_id or item["session_id"] != session_id:
            raise PermissionError("pointer scope mismatch")
        if item["expires_at"] <= now:
            raise TimeoutError("runtime pointer expired")
        byte_size = int(item["byte_size"])
        if cursor > byte_size:
            raise ValueError("invalid cursor")
        chunk = bytes(item["chunk"] or b"")
        if chunk and chunk[0] & 0xC0 == 0x80:
            raise ValueError("cursor splits a UTF-8 character")
        text, consumed = utf8_prefix(chunk)
        if chunk and not consumed:
            raise ValueError("max_bytes cannot fit the next character")
        end = cursor + consumed
        next_cursor = end if end < byte_size else None
        return ReadResult(text, next_cursor, next_cursor is not None, byte_size)

    def list(self, workspace_id: str, session_id: str) -> list[str]:
        """함수 이름: list()
        기능: 만료 원문을 정리하고 세션에 남은 ID를 정렬한다.
        인자: workspace_id/session_id -> 범위
        반환값: ID 목록
        작성 날짜: 2026/11/05
        """
        with self._connect() as connection:
            connection.execute("DELETE FROM runtime_pointers WHERE expires_at <= ?", (time.time(),))
            rows = connection.execute(
                """SELECT pointer_id FROM runtime_pointers WHERE workspace_id = ? AND session_id = ?
                   ORDER BY created_at DESC, pointer_id""",
                (workspace_id, session_id),
            )
            return [str(row["pointer_id"]) for row in rows]

    def delete(self, pointer_id: str, workspace_id: str, session_id: str) -> bool:
        """함수 이름: delete()
        기능: 작업 공간·세션·ID가 모두 일치하는 항목을 삭제한다.
        인자: pointer_id -> ID, workspace_id/session_id -> 범위
        반환값: 삭제 성공 여부
        작성 날짜: 2026/11/05
        """
        with self._connect() as connection:
            result = connection.execute(
                """DELETE FROM runtime_pointers WHERE pointer_id = ? AND workspace_id = ? AND session_id = ?""",
                (pointer_id, workspace_id, session_id),
            )
            return result.rowcount > 0

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        """함수 이름: clear_session()
        기능: 지정한 세션의 원문만 정리한다.
        인자: workspace_id/session_id -> 범위
        반환값: 삭제한 항목 수
        작성 날짜: 2026/11/05
        """
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM runtime_pointers WHERE workspace_id = ? AND session_id = ?",
                (workspace_id, session_id),
            )
            return result.rowcount
