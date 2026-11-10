"""Source 등록부 SQLite 저장: 등록 행, 외부 허용 항목, 파생 캐시 참조."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from securecode_context.pointers.source.models import (
    SourceLocation,
    SourceRecord,
    SourceStatus,
)
from securecode_context.pointers.source.registry_links import SourceLinksDb

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    location TEXT NOT NULL,
    grant_id TEXT,
    relative_path TEXT NOT NULL,
    path_key TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    identity TEXT NOT NULL,
    revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    preview TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, path_key)
);
CREATE TABLE IF NOT EXISTS external_grants (
    grant_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    real_root TEXT NOT NULL,
    file_name TEXT,
    UNIQUE (workspace_id, real_root, file_name)
);
CREATE TABLE IF NOT EXISTS derived_refs (
    source_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    PRIMARY KEY (source_id, cache_key)
);
"""
_COLUMNS = (
    "source_id, workspace_id, location, grant_id, relative_path, media_type, byte_size, "
    "fingerprint, identity, revision, status, preview, created_at, updated_at"
)
type Row = tuple[str, str, str, str | None, str, str, int, str, str, int, str, str, str, str]


def path_key(location: SourceLocation, grant_id: str | None, relative: PurePosixPath) -> str:
    """
    함수 이름: path_key()
    기능: 같은 원본의 중복 등록을 찾는 workspace 내부 고유 키를 만든다.
    인자: location -> 위치, grant_id -> 외부 허용 ID, relative -> 상대 경로
    반환값: 고유 키 문자열
    작성 날짜: 2026/11/10
    """
    return f"{location.value}:{grant_id or ''}:{relative.as_posix()}"


def _record(row: Row) -> SourceRecord:
    """
    함수 이름: _record()
    기능: SQLite 행을 SourceRecord로 바꾼다.
    인자: row -> _COLUMNS 순서의 행
    반환값: SourceRecord
    작성 날짜: 2026/11/10
    """
    identity = tuple(json.loads(row[8]))
    return SourceRecord(
        source_id=row[0],
        workspace_id=row[1],
        location=SourceLocation(row[2]),
        grant_id=row[3],
        relative_path=PurePosixPath(row[4]),
        media_type=row[5],
        byte_size=row[6],
        fingerprint=row[7],
        identity=(identity[0], identity[1], identity[2], identity[3], identity[4]),
        revision=row[9],
        status=SourceStatus(row[10]),
        preview=row[11],
        created_at=row[12],
        updated_at=row[13],
    )


class SourceDb:
    """
    클래스 이름: SourceDb
    기능: 등록부 테이블 읽기·쓰기. 잠금과 정책 판단은 SourceRegistry가 한다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, db_path: Path) -> None:
        """
        함수 이름: __init__()
        기능: 데이터 폴더에 SQLite 파일을 열고 스키마를 준비한다.
        인자: db_path -> registry.sqlite 경로
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.links = SourceLinksDb(self.conn)

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 연결을 닫아 Windows에서도 파일을 지울 수 있게 한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """
        함수 이름: transaction()
        기능: 여러 테이블 변경을 하나의 쓰기 트랜잭션으로 묶고 실패하면 되돌린다.
        인자: 없음
        반환값: 트랜잭션 컨텍스트
        작성 날짜: 2026/11/10
        """
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def get(self, workspace_id: str, source_id: str) -> SourceRecord | None:
        """
        함수 이름: get()
        기능: 같은 workspace의 등록 행을 찾는다. 다른 workspace 행은 보이지 않는다.
        인자: workspace_id -> 호출 범위, source_id -> 등록 ID
        반환값: SourceRecord 또는 None
        작성 날짜: 2026/11/10
        """
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM sources WHERE workspace_id = ? AND source_id = ?",
            (workspace_id, source_id),
        ).fetchone()
        return _record(row) if row else None

    def find_path(self, workspace_id: str, key: str) -> SourceRecord | None:
        """
        함수 이름: find_path()
        기능: 같은 원본 경로의 기존 등록을 찾는다.
        인자: workspace_id -> 범위, key -> path_key 값
        반환값: SourceRecord 또는 None
        작성 날짜: 2026/11/10
        """
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM sources WHERE workspace_id = ? AND path_key = ?",
            (workspace_id, key),
        ).fetchone()
        return _record(row) if row else None

    def find_fingerprint(
        self, workspace_id: str, relative: str, sha256: str
    ) -> SourceRecord | None:
        """
        함수 이름: find_fingerprint()
        기능: 심볼 provenance용으로 작업 공간 내부 경로·내용 해시가 같은 ready 등록을 찾는다.
        인자: workspace_id -> 범위, relative -> 상대 경로, sha256 -> 내용 해시
        반환값: SourceRecord 또는 None
        작성 날짜: 2026/11/10
        """
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM sources WHERE workspace_id = ? AND location = ? "
            "AND relative_path = ? AND fingerprint = ? AND status = ?",
            (workspace_id, SourceLocation.WORKSPACE.value, relative, sha256, SourceStatus.READY),
        ).fetchone()
        return _record(row) if row else None

    def save(self, record: SourceRecord) -> None:
        """
        함수 이름: save()
        기능: 등록 행을 넣거나 같은 source_id 행을 교체한다.
        인자: record -> 저장할 레코드
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        key = path_key(record.location, record.grant_id, record.relative_path)
        self.conn.execute(
            f"INSERT OR REPLACE INTO sources ({_COLUMNS}, path_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.source_id,
                record.workspace_id,
                record.location.value,
                record.grant_id,
                record.relative_path.as_posix(),
                record.media_type,
                record.byte_size,
                record.fingerprint,
                json.dumps(list(record.identity)),
                record.revision,
                record.status.value,
                record.preview,
                record.created_at,
                record.updated_at,
                key,
            ),
        )

    def delete(self, workspace_id: str, source_id: str) -> None:
        """
        함수 이름: delete()
        기능: 등록 행만 지운다. 사용자 원본은 건드리지 않는다.
        인자: workspace_id -> 범위, source_id -> 등록 ID
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn.execute(
            "DELETE FROM sources WHERE workspace_id = ? AND source_id = ?",
            (workspace_id, source_id),
        )

    def page(self, workspace_id: str, after: str, limit: int) -> list[SourceRecord]:
        """
        함수 이름: page()
        기능: source_id 순서로 다음 limit개를 읽는다.
        인자: workspace_id -> 범위, after -> 직전 마지막 ID, limit -> 최대 개수
        반환값: 레코드 목록
        작성 날짜: 2026/11/10
        """
        rows = self.conn.execute(
            f"SELECT {_COLUMNS} FROM sources WHERE workspace_id = ? AND source_id > ? "
            "ORDER BY source_id LIMIT ?",
            (workspace_id, after, limit),
        ).fetchall()
        return [_record(row) for row in rows]
