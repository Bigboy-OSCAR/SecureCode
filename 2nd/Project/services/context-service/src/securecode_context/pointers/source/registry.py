"""Source Pointer 디스크 저장소 및 경로 검증 Registry.

작성일: 2026-11-07
"""

import hashlib
import os
import sqlite3
import time
from typing import Dict, List, Optional
from securecode_context.pointers.source.models import SourceDescriptor, SourceRegistrationRequest


class SourceRegistry:
    """Workspace 단위 Source Pointer 등록 및 스탯/버전 관리자."""

    def __init__(self, db_path: str = ":memory:", workspace_roots: Optional[Dict[str, str]] = None):
        self.db_path = db_path
        self.workspace_roots = workspace_roots or {}
        self.allowed_external_paths: List[str] = []
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
        else:
            self.conn = sqlite3.connect(":memory:")
        self._init_db()

    def _init_db(self) -> None:
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
        real_p = os.path.realpath(path)
        if real_p not in self.allowed_external_paths:
            self.allowed_external_paths.append(real_p)

    def validate_path(self, workspace_id: str, target_path: str, allow_external: bool = False) -> str:
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
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]

    def register(self, req: SourceRegistrationRequest) -> SourceDescriptor:
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
            with open(real_p, "r", encoding="utf-8", errors="replace") as f:
                preview = f.read(512)
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
            created_at=time.time()
        )

        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO source_pointers
                (pointer, workspace_id, real_path, revision, media_type, byte_size, preview, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (desc.pointer, desc.workspace_id, desc.real_path, desc.revision,
                  desc.media_type, desc.byte_size, desc.preview, desc.created_at))

        return desc

    def stat(self, pointer: str) -> SourceDescriptor:
        cur = self.conn.cursor()
        cur.execute("SELECT pointer, workspace_id, real_path, revision, media_type, byte_size, preview, created_at FROM source_pointers WHERE pointer = ?", (pointer,))
        row = cur.fetchone()
        if not row:
            raise KeyError(f"NOT_FOUND: Source pointer not found: {pointer}")

        p, ws_id, real_p, stored_rev, m_type, b_size, prev, c_at = row
        if not os.path.exists(real_p):
            raise FileNotFoundError(f"SOURCE_CHANGED: Original file deleted: {real_p}")

        curr_rev = self.compute_file_hash(real_p)
        if curr_rev != stored_rev:
            raise ValueError(f"SOURCE_CHANGED: File hash modified. Stored={stored_rev}, Current={curr_rev}")

        return SourceDescriptor(
            pointer=p, kind="source", workspace_id=ws_id, revision=stored_rev,
            media_type=m_type, byte_size=b_size, preview=prev,
            available_operations=["read", "search", "stat"], real_path=real_p, created_at=c_at
        )

    def list_sources(self, workspace_id: str) -> List[SourceDescriptor]:
        cur = self.conn.cursor()
        cur.execute("SELECT pointer, workspace_id, real_path, revision, media_type, byte_size, preview, created_at FROM source_pointers WHERE workspace_id = ?", (workspace_id,))
        rows = cur.fetchall()
        res = []
        for r in rows:
            res.append(SourceDescriptor(
                pointer=r[0], kind="source", workspace_id=r[1], revision=r[3],
                media_type=r[4], byte_size=r[5], preview=r[6],
                available_operations=["read", "search", "stat"], real_path=r[2], created_at=r[7]
            ))
        return res

    def unregister(self, pointer: str) -> bool:
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM source_pointers WHERE pointer = ?", (pointer,))
            return cur.rowcount > 0
