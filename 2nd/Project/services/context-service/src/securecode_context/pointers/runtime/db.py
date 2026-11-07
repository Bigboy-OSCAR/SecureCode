"""Runtime Pointer 저장소의 DB 연결·스키마·공통 한도.

작성일: 2026-11-06
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_SESSION_BYTES = 128 * 1024 * 1024
MAX_PREVIEW_BYTES = 512

_SCHEMA = """
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
"""

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_runtime_scope ON runtime_pointers(workspace_id, session_id)"
)


def utc_now() -> datetime:
    """함수 이름: utc_now()
    기능: 현재 시각을 UTC 기준으로 반환한다.
    인자: 없음
    반환값: datetime
    작성 날짜: 2026/11/06
    """
    return datetime.now(UTC)


def open_connection(db_path: Path) -> sqlite3.Connection:
    """함수 이름: open_connection()
    기능: SQLite 연결을 열고 WAL 설정과 테이블·인덱스를 준비한다.
    인자: db_path -> SQLite 파일 경로
    반환값: sqlite3.Connection
    작성 날짜: 2026/11/06
    """
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute(_SCHEMA)
    connection.execute(_INDEX)
    connection.commit()
    return connection
