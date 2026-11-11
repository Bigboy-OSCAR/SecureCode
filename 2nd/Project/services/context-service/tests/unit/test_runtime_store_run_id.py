"""Runtime 출력의 run_id 출처(1.5 UI 표시용)와 v2→v3 스키마 업그레이드를 시험한다."""

import sqlite3
from pathlib import Path

from securecode_context.pointers.models.runtime import RuntimePut
from securecode_context.pointers.runtime.db import SCHEMA_VERSION
from securecode_context.pointers.runtime.store import RuntimeStore

WS, SES = "ws-1", "ses-1"
RUN = "run_0123456789abcdef"

_V2_SCHEMA = """
CREATE TABLE runtime_pointers (
    pointer_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, session_id TEXT NOT NULL,
    state TEXT NOT NULL, media_type TEXT NOT NULL, byte_size INTEGER NOT NULL,
    checksum TEXT NOT NULL, chunk_digests BLOB NOT NULL, origin TEXT NOT NULL,
    truncated_before_storage INTEGER NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, preview TEXT NOT NULL
);
CREATE TABLE runtime_tombstones (
    pointer_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, session_id TEXT NOT NULL,
    reason TEXT NOT NULL, removed_at TEXT NOT NULL
);
"""


def test_run_id_is_kept_in_descriptor_and_list(tmp_path: Path) -> None:
    """
    함수 이름: test_run_id_is_kept_in_descriptor_and_list()
    기능: 저장 때 받은 run_id가 descriptor와 목록 provenance에 남고, 없으면 필드도 없는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    store = RuntimeStore(tmp_path / "runtime")
    try:
        with_run = store.put(
            RuntimePut(WS, SES, "text/plain", b"out", origin="run_command", run_id=RUN)
        )
        without_run = store.put(RuntimePut(WS, SES, "text/plain", b"other"))
        assert with_run.to_dict()["provenance"]["run_id"] == RUN
        assert "run_id" not in without_run.to_dict()["provenance"]
        listed = {
            item["pointer"]: item["provenance"] for item in store.list_pointers(WS, SES)["items"]
        }
        assert listed[with_run.pointer].get("run_id") == RUN
        assert "run_id" not in listed[without_run.pointer]
    finally:
        store.close()


def test_v2_database_upgrades_without_losing_rows(tmp_path: Path) -> None:
    """
    함수 이름: test_v2_database_upgrades_without_losing_rows()
    기능: v2 DB를 열면 run_id 열만 더하고 기존 ready 행과 tombstone을 그대로 둔다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    root = tmp_path / "runtime"
    root.mkdir()
    legacy = sqlite3.connect(root / "runtime.sqlite3")
    legacy.executescript(_V2_SCHEMA)
    legacy.execute(
        "INSERT INTO runtime_tombstones VALUES ('00000000-0000-4000-8000-000000000000', ?, ?, "
        "'deleted', '2026-11-11T00:00:00+00:00')",
        (WS, SES),
    )
    legacy.execute("PRAGMA user_version=2")
    legacy.commit()
    legacy.close()

    store = RuntimeStore(root)
    try:
        connection = sqlite3.connect(root / "runtime.sqlite3")
        columns = [row[1] for row in connection.execute("PRAGMA table_info(runtime_pointers)")]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tombstones = connection.execute("SELECT COUNT(*) FROM runtime_tombstones").fetchone()[0]
        connection.close()
        assert "run_id" in columns and version == SCHEMA_VERSION == 3
        assert tombstones == 1
        stored = store.put(RuntimePut(WS, SES, "text/plain", b"after upgrade", run_id=RUN))
        assert stored.to_dict()["provenance"]["run_id"] == RUN
    finally:
        store.close()
