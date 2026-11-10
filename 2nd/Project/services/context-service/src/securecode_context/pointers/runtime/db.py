"""Runtime Pointer 저장소의 SQLite 연결·스키마(v2)·공통 한도.

v2는 저장 예약(pending)→완료(ready) 상태, 64 KiB 청크 digest, origin, tombstone을 가진다.
v1(2026-11-06) 스키마의 자료는 24시간 TTL의 임시 출력이므로 업그레이드 때 비우고 다시 만든다.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_SESSION_BYTES = 128 * 1024 * 1024
MAX_PREVIEW_BYTES = 512
SCHEMA_VERSION = 2
TOMBSTONE_DAYS = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_pointers (
    pointer_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    state TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    chunk_digests BLOB NOT NULL,
    origin TEXT NOT NULL,
    truncated_before_storage INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    preview TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_scope ON runtime_pointers(workspace_id, session_id, state);
CREATE INDEX IF NOT EXISTS idx_runtime_expiry ON runtime_pointers(expires_at);
CREATE TABLE IF NOT EXISTS runtime_tombstones (
    pointer_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    removed_at TEXT NOT NULL
);
"""


def utc_now() -> datetime:
    """
    함수 이름: utc_now()
    기능: 현재 시각을 UTC로 반환한다.
    인자: 없음
    반환값: datetime
    작성 날짜: 2026/11/06
    """
    return datetime.now(UTC)


def open_connection(db_path: Path) -> sqlite3.Connection:
    """
    함수 이름: open_connection()
    기능: SQLite 연결을 열고 WAL·busy timeout을 설정한 뒤 v2 스키마를 준비한다.
        autocommit 모드라 쓰기 묶음은 transaction()으로 명시한다.
    인자: db_path -> SQLite 파일 경로
    반환값: sqlite3.Connection
    작성 날짜: 2026/11/10
    """
    connection = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    # WAL+NORMAL keeps the DB consistent; a power loss can drop the newest rows. Blobs are fsynced
    # before their row commits, and restart recovery removes blobs whose row was lost.
    connection.execute("PRAGMA synchronous=NORMAL")
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version < SCHEMA_VERSION:
        # v1 rows have no chunk digests or state; they are short-lived outputs, so start clean.
        connection.execute("DROP TABLE IF EXISTS runtime_pointers")
        connection.execute("DROP TABLE IF EXISTS runtime_tombstones")
    connection.executescript(_SCHEMA)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """
    함수 이름: transaction()
    기능: BEGIN IMMEDIATE로 쓰기 잠금을 먼저 잡는다. 같은 DB를 쓰는 다른 저장소 인스턴스와도
        용량 검사·저장이 직렬화된다. 실패하면 되돌린다.
    인자: connection -> SQLite 연결
    반환값: 트랜잭션 컨텍스트
    작성 날짜: 2026/11/10
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def tombstone(
    connection: sqlite3.Connection,
    pointer_id: str,
    scope: tuple[str, str],
    reason: str,
) -> None:
    """
    함수 이름: tombstone()
    기능: 지운 포인터의 사유(deleted/expired/session_cleared/lost)를 남겨 이후 조회에 명확한 상태를 준다.
    인자: connection -> 연결(트랜잭션 안), pointer_id -> ID, scope -> (workspace, session), reason -> 사유
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    connection.execute(
        "INSERT OR REPLACE INTO runtime_tombstones VALUES (?, ?, ?, ?, ?)",
        (pointer_id, scope[0], scope[1], reason, utc_now().isoformat()),
    )
