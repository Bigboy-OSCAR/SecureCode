"""revision 기록과 빌드 상태를 IndexStatusResponse 계약 모양으로 바꾼다."""

from dataclasses import dataclass
from typing import Any

from .records import IndexCounts, IndexRevisionRecord

MAX_STATUS_DIAGNOSTICS = 50


@dataclass(frozen=True)
class BuildState:
    """
    클래스 이름: BuildState
    기능: 진행 중이거나 마지막으로 실패한 빌드의 revision·시각·오류 코드를 보관한다.
    작성 날짜: 2026/11/05
    """

    pending_revision: int | None
    started_at: str
    completed_at: str | None = None
    error_code: str | None = None


def _index_state(record: IndexRevisionRecord | None, build: BuildState | None, stale: bool) -> str:
    """
    함수 이름: _index_state()
    기능: 진행·실패·변경·검색 준비 여부로 IndexState 값을 고른다.
    인자: record -> 현재 revision, build -> 빌드 상태, stale -> 디스크 변경 여부
    반환값: 계약 IndexState 문자열
    작성 날짜: 2026/11/05
    """
    if build is not None and build.completed_at is None:
        return "indexing"
    if build is not None and build.error_code is not None:
        return "failed"
    if record is None:
        return "not_indexed"
    if stale:
        return "stale"
    if record["retrieval"]["state"] != "ready":
        return "parsed"
    return "partial" if record["diagnostics"] else "ready"


def status_payload(
    workspace_id: str,
    record: IndexRevisionRecord | None,
    build: BuildState | None,
    stale: bool,
) -> dict[str, Any]:
    """
    함수 이름: status_payload()
    기능: 집계와 앞쪽 진단 50개만 담는다. 원문·그래프·후보·절대 경로는 포함하지 않는다.
    인자: workspace_id -> 작업 공간, record -> 현재 revision, build -> 빌드 상태, stale -> 변경 여부
    반환값: IndexStatusResponse JSON 값
    작성 날짜: 2026/11/05
    """
    counts = (
        record["counts"]
        if record is not None
        else IndexCounts(discovered=0, indexed=0, skipped=0, failed=0)
    )
    diagnostics = record["diagnostics"] if record is not None else []
    payload: dict[str, Any] = {
        "schema_version": "1",
        "workspace_id": workspace_id,
        "index_status": _index_state(record, build, stale),
        "index_revision": record["index_revision"] if record is not None else None,
        "pending_revision": build.pending_revision if build is not None else None,
        "searchable": record is not None and record["retrieval"]["state"] == "ready",
        "counts": dict(counts),
        "diagnostics": [dict(item) for item in diagnostics[:MAX_STATUS_DIAGNOSTICS]],
        "diagnostics_truncated": len(diagnostics) > MAX_STATUS_DIAGNOSTICS,
    }
    if build is not None:
        payload["started_at"] = build.started_at
        if build.completed_at is not None:
            payload["completed_at"] = build.completed_at
    elif record is not None:
        payload["completed_at"] = record["created_at"]
    return payload
