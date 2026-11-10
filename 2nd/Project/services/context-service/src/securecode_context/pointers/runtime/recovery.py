"""재시작 정합성 복구: 오래된 저장 예약, blob이 없거나 크기가 다른 행, 행 없는 blob·임시 파일을 정리한다.

다른 저장소 인스턴스가 진행 중인 저장을 지우지 않도록 예약은 1시간, 고아 파일은 5분이 지난 것만 정리한다.
TTL 만료 정리(sweep)와 세션 종료 정리는 이 모듈이 아니라 저장소의 별도 연산이다.
"""

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from threading import RLock

from securecode_context.pointers.runtime.blob import TEMP_PREFIX, blob_path
from securecode_context.pointers.runtime.db import tombstone, transaction, utc_now

STALE_PENDING = timedelta(hours=1)
ORPHAN_GRACE_SECONDS = 300.0


@dataclass(frozen=True)
class RecoveryReport:
    """
    클래스 이름: RecoveryReport
    기능: 복구에서 지운 예약·잃은 행·고아 파일 수.
    작성 날짜: 2026/11/10
    """

    stale_pending: int
    lost_rows: int
    orphan_files: int


def recover(connection: sqlite3.Connection, lock: RLock, root: Path) -> RecoveryReport:
    """
    함수 이름: recover()
    기능: DB와 blob 폴더를 맞춘다. ready 행의 blob 크기가 다르면 잃은 것으로 보고 tombstone(lost)을 남긴다.
    인자: connection -> SQLite 연결, lock -> 저장소 잠금, root -> blob root
    반환값: RecoveryReport
    작성 날짜: 2026/11/10
    """
    cutoff = (utc_now() - STALE_PENDING).isoformat()
    removed: list[tuple[str, str, str]] = []
    lost = 0
    with lock, transaction(connection):
        rows = connection.execute(
            "SELECT pointer_id, workspace_id, session_id, state, byte_size, created_at "
            "FROM runtime_pointers"
        ).fetchall()
        for row in rows:
            scope = (row["workspace_id"], row["session_id"])
            path = blob_path(root, scope[0], scope[1], row["pointer_id"])
            if row["state"] == "pending":
                if row["created_at"] < cutoff:
                    removed.append((row["pointer_id"], *scope))
                continue
            if not path.is_file() or path.stat().st_size != row["byte_size"]:
                removed.append((row["pointer_id"], *scope))
                tombstone(connection, row["pointer_id"], scope, "lost")
                lost += 1
        for pointer_id, _, _ in removed:
            connection.execute("DELETE FROM runtime_pointers WHERE pointer_id = ?", (pointer_id,))
        known = {
            str(row[0]) for row in connection.execute("SELECT pointer_id FROM runtime_pointers")
        }
    for pointer_id, workspace_id, session_id in removed:
        path = blob_path(root, workspace_id, session_id, pointer_id)
        _unlink(path)
        _unlink(path.with_name(TEMP_PREFIX + path.name))
    orphans = _remove_orphans(root, known)
    return RecoveryReport(len(removed) - lost, lost, orphans)


def _remove_orphans(root: Path, known: set[str]) -> int:
    """
    함수 이름: _remove_orphans()
    기능: 행이 없고 유예 시간이 지난 blob·임시 파일을 지운다.
    인자: root -> blob root, known -> DB에 있는 포인터 ID
    반환값: 지운 파일 수
    작성 날짜: 2026/11/10
    """
    if not root.is_dir():
        return 0
    removed = 0
    deadline = time.time() - ORPHAN_GRACE_SECONDS
    for workspace in os.scandir(root):
        if not workspace.is_dir(follow_symlinks=False):
            continue
        for session in os.scandir(workspace.path):
            if not session.is_dir(follow_symlinks=False):
                continue
            for entry in os.scandir(session.path):
                name = entry.name.removeprefix(TEMP_PREFIX).removesuffix(".blob")
                stale = entry.stat(follow_symlinks=False).st_mtime < deadline
                if entry.is_file(follow_symlinks=False) and name not in known and stale:
                    removed += _unlink(Path(entry.path))
    return removed


def _unlink(path: Path) -> int:
    """
    함수 이름: _unlink()
    기능: 파일을 지운다. 다른 프로세스가 열고 있어 지우지 못하면 다음 복구로 미루고 시작은 막지 않는다.
    인자: path -> 지울 파일
    반환값: 지웠으면 1, 아니면 0
    작성 날짜: 2026/11/10
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return 0
    return 1
