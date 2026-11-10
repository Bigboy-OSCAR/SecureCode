"""Source 등록부의 외부 허용 항목과 파생 캐시 참조 테이블."""

import sqlite3
from pathlib import Path

from securecode_context.pointers.source.models import ExternalGrant


class SourceLinksDb:
    """
    클래스 이름: SourceLinksDb
    기능: 등록 행과 연결된 외부 허용 항목·파생 캐시 참조를 읽고 쓴다. 같은 SQLite 연결을 쓴다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        함수 이름: __init__()
        기능: SourceDb가 연 연결을 보관한다.
        인자: conn -> SQLite 연결
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn = conn

    def grant(self, workspace_id: str, grant_id: str) -> ExternalGrant | None:
        """
        함수 이름: grant()
        기능: workspace 범위의 외부 허용 항목을 찾는다.
        인자: workspace_id -> 범위, grant_id -> 허용 ID
        반환값: ExternalGrant 또는 None
        작성 날짜: 2026/11/10
        """
        row = self.conn.execute(
            "SELECT grant_id, workspace_id, real_root, file_name FROM external_grants "
            "WHERE workspace_id = ? AND grant_id = ?",
            (workspace_id, grant_id),
        ).fetchone()
        return ExternalGrant(row[0], row[1], Path(row[2]), row[3]) if row else None

    def find_grant(self, workspace_id: str, real_root: Path, file_name: str | None) -> str | None:
        """
        함수 이름: find_grant()
        기능: 같은 외부 root·파일 허용 항목을 재사용하기 위해 찾는다.
        인자: workspace_id -> 범위, real_root -> 실제 root, file_name -> 단일 파일 허용 이름
        반환값: grant_id 또는 None
        작성 날짜: 2026/11/10
        """
        row = self.conn.execute(
            "SELECT grant_id FROM external_grants WHERE workspace_id = ? AND real_root = ? "
            "AND file_name IS ?",
            (workspace_id, str(real_root), file_name),
        ).fetchone()
        return str(row[0]) if row else None

    def add_grant(self, grant: ExternalGrant) -> None:
        """
        함수 이름: add_grant()
        기능: 외부 허용 항목을 저장한다.
        인자: grant -> 저장할 항목
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn.execute(
            "INSERT INTO external_grants (grant_id, workspace_id, real_root, file_name) "
            "VALUES (?, ?, ?, ?)",
            (grant.grant_id, grant.workspace_id, str(grant.real_root), grant.file_name),
        )

    def drop_unused_grant(self, grant_id: str) -> None:
        """
        함수 이름: drop_unused_grant()
        기능: 더 이상 참조하는 등록이 없는 외부 허용 항목을 지워 접근 권한을 회수한다.
        인자: grant_id -> 허용 ID
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn.execute(
            "DELETE FROM external_grants WHERE grant_id = ? AND NOT EXISTS "
            "(SELECT 1 FROM sources WHERE grant_id = ?)",
            (grant_id, grant_id),
        )

    def add_ref(self, source_id: str, cache_key: str) -> None:
        """
        함수 이름: add_ref()
        기능: 등록이 파생 캐시를 참조한다고 기록한다.
        인자: source_id -> 등록 ID, cache_key -> 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO derived_refs (source_id, cache_key) VALUES (?, ?)",
            (source_id, cache_key),
        )

    def release_refs(self, source_id: str) -> list[str]:
        """
        함수 이름: release_refs()
        기능: 등록의 캐시 참조를 지우고, 다른 등록이 더 참조하지 않는 캐시 키를 돌려준다.
        인자: source_id -> 등록 ID
        반환값: 삭제해도 되는 캐시 키 목록
        작성 날짜: 2026/11/10
        """
        keys = [
            str(row[0])
            for row in self.conn.execute(
                "SELECT cache_key FROM derived_refs WHERE source_id = ?", (source_id,)
            ).fetchall()
        ]
        self.conn.execute("DELETE FROM derived_refs WHERE source_id = ?", (source_id,))
        return [
            key
            for key in keys
            if self.conn.execute(
                "SELECT 1 FROM derived_refs WHERE cache_key = ?", (key,)
            ).fetchone()
            is None
        ]
