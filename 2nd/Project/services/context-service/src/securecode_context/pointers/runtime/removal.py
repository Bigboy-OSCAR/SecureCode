"""Runtime 출력 삭제: tombstone을 남기고 blob을 지운다(삭제·세션 정리·TTL sweep 공용)."""

import sqlite3
from pathlib import Path
from threading import RLock

from securecode_context.pointers.runtime.blob import blob_path
from securecode_context.pointers.runtime.db import tombstone, transaction


def remove_where(
    connection: sqlite3.Connection,
    lock: RLock,
    blobs: Path,
    condition: tuple[str, tuple[str, ...]],
    reason: str,
) -> int:
    """
    함수 이름: remove_where()
    기능: 조건에 맞는 ready 행을 사유와 함께 tombstone으로 바꾸고 행·blob을 지운다.
        다시 불러도 이미 지운 행은 없으므로 같은 결과다(멱등).
    인자: connection -> SQLite 연결, lock -> 저장소 잠금, blobs -> blob root,
        condition -> (WHERE 절, 인자), reason -> deleted/session_cleared/expired
    반환값: 지운 개수
    작성 날짜: 2026/11/10
    """
    where, params = condition
    with lock, transaction(connection):
        rows = connection.execute(
            "SELECT pointer_id, workspace_id, session_id FROM runtime_pointers "
            f"WHERE {where} AND state = 'ready'",
            params,
        ).fetchall()
        for row in rows:
            tombstone(
                connection, row["pointer_id"], (row["workspace_id"], row["session_id"]), reason
            )
            connection.execute(
                "DELETE FROM runtime_pointers WHERE pointer_id = ?", (row["pointer_id"],)
            )
    for row in rows:
        path = blob_path(blobs, row["workspace_id"], row["session_id"], row["pointer_id"])
        path.unlink(missing_ok=True)
    return len(rows)
