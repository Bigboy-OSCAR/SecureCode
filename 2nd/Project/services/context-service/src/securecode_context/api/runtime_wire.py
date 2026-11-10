"""Runtime 읽기·검색·목록 결과를 계약 JSON(PointerReadResult·PointerSearchResult·PointerListResult)으로 바꾼다."""

from typing import Any

from securecode_context.pointers.runtime.reads import RuntimeReadOutcome, RuntimeSearchOutcome
from securecode_context.pointers.text.models import ByteSpan

SCHEMA_VERSION = "1"


def _selection(checksum: str, span: ByteSpan) -> dict[str, object]:
    """
    함수 이름: _selection()
    기능: 반환 본문이 저장 출력의 어느 구간인지 checksum과 함께 표시한다(Runtime revision은 1).
    인자: checksum -> 저장 출력 SHA-256, span -> 바이트 구간
    반환값: 계약 PointerSelection
    작성 날짜: 2026/11/10
    """
    return {
        "revision": 1,
        "content_sha256": checksum,
        "range": {"type": "byte", "start": span.start, "end": span.end},
    }


def read_result(pointer: str, outcome: RuntimeReadOutcome) -> dict[str, object]:
    """
    함수 이름: read_result()
    기능: Runtime 읽기 결과를 PointerReadResult로 바꾼다.
    인자: pointer -> 요청 URI, outcome -> 읽기 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    row = outcome.row
    provenance: dict[str, object] = {
        "media_type": row["media_type"],
        "byte_size": row["byte_size"],
        "revision": 1,
        "display_name": "output-" + row["pointer_id"][:8],
    }
    if outcome.span is not None:
        provenance["selection"] = _selection(row["checksum"], outcome.span)
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pointer": pointer,
        "content": outcome.content,
        "provenance": provenance,
        "truncated": outcome.truncated,
        "token_count": outcome.token_count,
        "count_mode": outcome.count_mode,
    }
    if outcome.next_cursor is not None:
        result["next_cursor"] = outcome.next_cursor
    return result


def search_result(pointer: str, outcome: RuntimeSearchOutcome) -> dict[str, object]:
    """
    함수 이름: search_result()
    기능: Runtime 검색 결과를 PointerSearchResult로 바꾼다. 일치마다 줄·바이트 출처를 붙인다.
    인자: pointer -> 요청 URI, outcome -> 검색 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    checksum = outcome.row["checksum"]
    matches: list[dict[str, object]] = []
    for match in outcome.matches:
        item: dict[str, object] = {
            "line": match.line,
            "content": match.content,
            "byte_offset": match.byte_offset,
        }
        if match.span.end > match.span.start:
            item["selection"] = _selection(checksum, match.span)
        matches.append(item)
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pointer": pointer,
        "matches": matches,
        "truncated": outcome.truncated,
        "token_count": outcome.token_count,
        "count_mode": outcome.count_mode,
    }
    if outcome.next_cursor is not None:
        result["next_cursor"] = outcome.next_cursor
    return result


def list_result(workspace_id: str, limit: int, page: dict[str, Any]) -> dict[str, object]:
    """
    함수 이름: list_result()
    기능: 목록 페이지를 PointerListResult로 바꾼다.
    인자: workspace_id -> 범위, limit -> 요청 limit, page -> 저장소 목록 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "items": page["items"],
        "page": {
            "limit": limit,
            "next_cursor": page["next_cursor"],
            "has_more": page["has_more"],
            "truncated_by_bytes": page["truncated_by_bytes"],
        },
    }
