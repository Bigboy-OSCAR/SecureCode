"""Source Pointer 디스크 저장소 및 경로 검증 Registry.

작성일: 2026-11-07
"""

import hashlib
import os
import sqlite3
import time

from securecode_context.pointers.source.models import SourceDescriptor, SourceRegistrationRequest


class SourceRegistry:
    """클래스 이름: SourceRegistry
    기능: workspace의 등록 원본 경로와 revision을 SQLite로 관리한다.
    작성 날짜: 2026/11/09
    """

    def __init__(
        self, db_path: str = ":memory:", workspace_roots: dict[str, str] | None = None
    ) -> None:
        """함수 이름: __init__()
        기능: 저장소 경로와 workspace 허용 root를 설정한다.
        인자: db_path, workspace_roots
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.db_path = db_path
        self.workspace_roots = workspace_roots or {}
        self.allowed_external_paths: list[str] = []
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
        else:
            self.conn = sqlite3.connect(":memory:")
        self._init_db()

    def _init_db(self) -> None:
        """함수 이름: _init_db()
        기능: 등록 메타데이터 테이블을 준비한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS source_pointers (
                    pointer TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    real_path TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    preview TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

    def add_allowed_external_path(self, path: str) -> None:
        """함수 이름: add_allowed_external_path()
        기능: 사용자가 명시한 외부 파일의 실경로를 허용 목록에 추가한다.
        인자: path
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        real_p = os.path.realpath(path)
        if real_p not in self.allowed_external_paths:
            self.allowed_external_paths.append(real_p)

    def validate_path(
        self, workspace_id: str, target_path: str, allow_external: bool = False
    ) -> str:
        """함수 이름: validate_path()
        기능: 실경로가 workspace 또는 외부 허용 범위 안인지 확인한다.
        인자: workspace_id, target_path, allow_external
        반환값: 허용된 실경로
        작성 날짜: 2026/11/09
        """
        real_target = os.path.realpath(target_path)
        ws_root = self.workspace_roots.get(workspace_id)

        if ws_root:
            real_ws_root = os.path.realpath(ws_root)
            if os.path.commonpath([real_target, real_ws_root]) == real_ws_root:
                return real_target

        if allow_external:
            for ext_p in self.allowed_external_paths:
                if os.path.commonpath([real_target, ext_p]) == ext_p:
                    return real_target

        raise ValueError(f"FORBIDDEN: Path outside allowed root: {target_path}")

    def compute_file_hash(self, file_path: str) -> str:
        """함수 이름: compute_file_hash()
        기능: 고정 크기 청크로 파일의 내용 revision을 계산한다.
        인자: file_path
        반환값: 내용 hash 접두어
        작성 날짜: 2026/11/09
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]

    def register(self, req: SourceRegistrationRequest) -> SourceDescriptor:
        """함수 이름: register()
        기능: 크기와 경로를 검증한 원본을 등록하고 제한된 미리보기를 저장한다.
        인자: req
        반환값: Source descriptor
        작성 날짜: 2026/11/09
        """
        real_p = self.validate_path(req.workspace_id, req.target_path, req.allow_external)
        if not os.path.isfile(real_p):
            raise FileNotFoundError(f"NOT_FOUND: Source file does not exist: {real_p}")

        stat = os.stat(real_p)
        limit_bytes = 256 * 1024 * 1024
        if stat.st_size > limit_bytes:
            raise ValueError("EXCEEDED: Source file size exceeds 256 MiB limit")

        rev = self.compute_file_hash(real_p)
        source_id = hashlib.md5(f"{req.workspace_id}:{real_p}".encode()).hexdigest()[:12]
        pointer = f"securecode://source/{req.workspace_id}/{source_id}?v={rev}"

        preview = ""
        try:
            with open(real_p, "rb") as f:
                preview = f.read(512).decode("utf-8", errors="ignore")
        except Exception:
            preview = "<binary content>"

        media_type = req.media_type or "text/plain"
        desc = SourceDescriptor(
            pointer=pointer,
            kind="source",
            workspace_id=req.workspace_id,
            revision=rev,
            media_type=media_type,
            byte_size=stat.st_size,
            preview=preview,
            available_operations=["read", "search", "stat"],
            real_path=real_p,
            created_at=time.time(),
        )

        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO source_pointers
                (pointer, workspace_id, real_path, revision, media_type, byte_size, preview, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    desc.pointer,
                    desc.workspace_id,
                    desc.real_path,
                    desc.revision,
                    desc.media_type,
                    desc.byte_size,
                    desc.preview,
                    desc.created_at,
                ),
            )

        return desc

    def stat(self, pointer: str) -> SourceDescriptor:
        """함수 이름: stat()
        기능: 등록 메타데이터와 현재 경로·내용 revision을 검증한다.
        인자: pointer
        반환값: 변경되지 않은 Source descriptor
        작성 날짜: 2026/11/09
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT pointer, workspace_id, real_path, revision, media_type, byte_size, preview, "
            "created_at FROM source_pointers WHERE pointer = ?",
            (pointer,),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError(f"NOT_FOUND: Source pointer not found: {pointer}")

        p, ws_id, real_p, stored_rev, m_type, b_size, prev, c_at = row
        if not os.path.exists(real_p):
            raise FileNotFoundError(f"SOURCE_CHANGED: Original file deleted: {real_p}")

        self.validate_path(ws_id, real_p, allow_external=True)
        curr_rev = self.compute_file_hash(real_p)
        if curr_rev != stored_rev:
            raise ValueError(
                f"SOURCE_CHANGED: File hash modified. Stored={stored_rev}, Current={curr_rev}"
            )

        return SourceDescriptor(
            pointer=p,
            kind="source",
            workspace_id=ws_id,
            revision=stored_rev,
            media_type=m_type,
            byte_size=b_size,
            preview=prev,
            available_operations=["read", "search", "stat"],
            real_path=real_p,
            created_at=c_at,
        )

    def list_sources(self, workspace_id: str) -> list[SourceDescriptor]:
        """함수 이름: list_sources()
        기능: workspace에 등록된 Source 메타데이터를 조회한다.
        인자: workspace_id
        반환값: Source descriptor 목록
        작성 날짜: 2026/11/09
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT pointer, workspace_id, real_path, revision, media_type, byte_size, preview, "
            "created_at FROM source_pointers WHERE workspace_id = ?",
            (workspace_id,),
        )
        rows = cur.fetchall()
        res = []
        for r in rows:
            res.append(
                SourceDescriptor(
                    pointer=r[0],
                    kind="source",
                    workspace_id=r[1],
                    revision=r[3],
                    media_type=r[4],
                    byte_size=r[5],
                    preview=r[6],
                    available_operations=["read", "search", "stat"],
                    real_path=r[2],
                    created_at=r[7],
                )
            )
        return res

    def unregister(self, pointer: str) -> bool:
        """함수 이름: unregister()
        기능: 등록 정보만 지우고 사용자 원본 파일은 보존한다.
        인자: pointer
        반환값: 등록이 삭제됐으면 True
        작성 날짜: 2026/11/09
        """
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM source_pointers WHERE pointer = ?", (pointer,))
            return cur.rowcount > 0
