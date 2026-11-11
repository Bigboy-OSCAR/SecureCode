"""Runtime 목록 조회와 행→descriptor 변환. 응답은 최대 100개·64 KiB다."""

import sqlite3
from datetime import datetime
from typing import Any

from securecode_context.pointers.models.runtime import InvalidSelector, RuntimeDescriptor
from securecode_context.pointers.runtime.db import utc_now

MAX_LIST_BODY_BYTES = 64 * 1024


def list_page(
    connection: sqlite3.Connection,
    scope: tuple[str, str],
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """
    함수 이름: list_page()
    기능: 만료 전 ready 포인터를 ID 순으로 최대 limit개, 응답 64 KiB 이하로 돌려준다.
    인자: connection -> SQLite 연결, scope -> (workspace, session), limit -> 1~100,
        cursor -> 직전 마지막 ID(호출자가 형식 검사)
    반환값: items·has_more·next_cursor·truncated_by_bytes
    작성 날짜: 2026/11/10
    """
    if not 1 <= limit <= 100:
        raise InvalidSelector("목록 limit이 올바르지 않습니다", "invalid_page")
    rows = connection.execute(
        "SELECT * FROM runtime_pointers WHERE workspace_id = ? AND session_id = ? "
        "AND state = 'ready' AND expires_at > ? AND pointer_id > ? ORDER BY pointer_id LIMIT ?",
        (scope[0], scope[1], utc_now().isoformat(), cursor or "", limit + 1),
    ).fetchall()
    items: list[dict[str, Any]] = []
    used = 0
    for row in rows[:limit]:
        item = descriptor_of(row).to_dict()
        used += len(item["preview"].encode()) + 512
        if used > MAX_LIST_BODY_BYTES:
            break
        items.append(item)
    by_bytes = len(items) < min(limit, len(rows))
    has_more = by_bytes or len(rows) > limit
    last = items[-1]["pointer"].rsplit("/", 1)[-1].split("?")[0] if items else cursor
    return {
        "items": items,
        "has_more": has_more,
        "next_cursor": last if has_more else None,
        "truncated_by_bytes": by_bytes,
    }


def descriptor_of(row: Any) -> RuntimeDescriptor:
    """
    함수 이름: descriptor_of()
    기능: ready 행을 descriptor로 바꾼다.
    인자: row -> sqlite3.Row
    반환값: RuntimeDescriptor
    작성 날짜: 2026/11/10
    """
    scope = f"{row['workspace_id']}/{row['session_id']}/{row['pointer_id']}"
    return RuntimeDescriptor(
        pointer=f"securecode://runtime/{scope}?v=1",
        workspace_id=row["workspace_id"],
        session_id=row["session_id"],
        media_type=row["media_type"],
        byte_size=row["byte_size"],
        checksum=row["checksum"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        preview=row["preview"],
        origin=row["origin"],
        truncated_before_storage=bool(row["truncated_before_storage"]),
        run_id=row["run_id"],
    )
