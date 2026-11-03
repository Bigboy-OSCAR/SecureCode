import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ReadResult:
    content: str
    next_cursor: Optional[int]
    truncated: bool
    byte_size: int


class SQLiteRuntimeStore:
    def __init__(self, db_path: str = "runtime_pointers.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_pointers (
                    pointer_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    content BLOB NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_scope
                ON runtime_pointers (workspace_id, session_id)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def put(
        self,
        content: str,
        workspace_id: str,
        session_id: str,
        ttl_seconds: int = 60 * 60 * 24,
    ) -> str:
        pointer_id = str(uuid.uuid4())
        now = time.time()
        encoded = content.encode("utf-8")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_pointers (
                    pointer_id,
                    workspace_id,
                    session_id,
                    content,
                    byte_size,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
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
        max_bytes: int = 32 * 1024,
    ) -> ReadResult:
        item = self._get_valid_item(pointer_id, workspace_id, session_id)
        content: bytes = item["content"]
        byte_size: int = item["byte_size"]

        if cursor < 0 or cursor > byte_size:
            raise ValueError("invalid cursor")

        end = min(cursor + max_bytes, byte_size)
        chunk = content[cursor:end]
        next_cursor = end if end < byte_size else None

        return ReadResult(
            content=chunk.decode("utf-8", errors="ignore"),
            next_cursor=next_cursor,
            truncated=next_cursor is not None,
            byte_size=byte_size,
        )

    def list(self, workspace_id: str, session_id: str) -> list[str]:
        self._remove_expired()

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT pointer_id
                FROM runtime_pointers
                WHERE workspace_id = ? AND session_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id, session_id),
            ).fetchall()

        return [row["pointer_id"] for row in rows]

    def delete(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM runtime_pointers
                WHERE pointer_id = ?
                  AND workspace_id = ?
                  AND session_id = ?
                """,
                (pointer_id, workspace_id, session_id),
            )

        return cursor.rowcount > 0

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM runtime_pointers
                WHERE workspace_id = ? AND session_id = ?
                """,
                (workspace_id, session_id),
            )

        return cursor.rowcount

    def _get_valid_item(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
    ) -> sqlite3.Row:
        with self._connect() as connection:
            item = connection.execute(
                """
                SELECT *
                FROM runtime_pointers
                WHERE pointer_id = ?
                """,
                (pointer_id,),
            ).fetchone()

        if item is None:
            raise KeyError("runtime pointer not found")

        if item["workspace_id"] != workspace_id:
            raise PermissionError("workspace scope mismatch")

        if item["session_id"] != session_id:
            raise PermissionError("session scope mismatch")

        if time.time() > item["expires_at"]:
            self.delete(pointer_id, workspace_id, session_id)
            raise TimeoutError("runtime pointer expired")

        return item

    def _remove_expired(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM runtime_pointers
                WHERE expires_at < ?
                """,
                (time.time(),),
            )
