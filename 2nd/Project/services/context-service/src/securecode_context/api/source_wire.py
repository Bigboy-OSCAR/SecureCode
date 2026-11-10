"""Source 등록부 레코드를 계약 JSON(PointerListItem·SourceMutationResult 등)으로 바꾼다."""

from securecode_context.pdf.wire import page_selection
from securecode_context.pointers.source import media
from securecode_context.pointers.source.models import (
    SourceLocation,
    SourceMutation,
    SourcePage,
    SourceRecord,
)
from securecode_context.pointers.source.read_models import ByteSpan, ReadOutcome, SearchOutcome

SCHEMA_VERSION = "1"
_DISPLAY_LIMIT = 160


def _display_name(record: SourceRecord) -> str:
    """
    함수 이름: _display_name()
    기능: 계약 PointerDisplayName(콜론·구분자·제어 문자 없음, 160자 이하)을 만든다.
    인자: record -> 등록 레코드
    반환값: 화면 표시 이름
    작성 날짜: 2026/11/10
    """
    name = "".join(
        "_" if char == ":" or ord(char) < 32 else char for char in record.relative_path.name
    )
    return name[:_DISPLAY_LIMIT] or "source"


def source_item(record: SourceRecord) -> dict[str, object]:
    """
    함수 이름: source_item()
    기능: 등록 레코드를 PointerListItem으로 바꾼다. 서버 절대 경로는 넣지 않는다.
    인자: record -> 등록 레코드
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    item: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pointer": record.pointer,
        "kind": "source",
        "workspace_id": record.workspace_id,
        "revision": record.revision,
        "media_type": record.media_type,
        "byte_size": record.byte_size,
        "preview": record.preview,
        "available_operations": media.available_operations(record.media_type),
        "provenance": {"created_at": record.created_at, "origin": "register"},
        "display_name": _display_name(record),
        "supported_selectors": media.supported_selectors(record.media_type, record.byte_size),
    }
    if record.location is SourceLocation.WORKSPACE:
        item["relative_path"] = record.relative_path.as_posix()
    return item


def mutation_result(mutation: SourceMutation) -> dict[str, object]:
    """
    함수 이름: mutation_result()
    기능: 등록·갱신 결과를 SourceMutationResult로 바꾼다.
    인자: mutation -> 등록 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": mutation.workspace_id,
        "status": mutation.status,
        "items": [source_item(record) for record in mutation.items],
        "issues": [
            {"relative_path": issue.relative_path, "code": issue.code} for issue in mutation.issues
        ],
    }


def list_result(page: SourcePage) -> dict[str, object]:
    """
    함수 이름: list_result()
    기능: 목록 한 페이지를 PointerListResult로 바꾼다.
    인자: page -> 목록 페이지
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": page.workspace_id,
        "items": [source_item(record) for record in page.items],
        "page": {
            "limit": page.limit,
            "next_cursor": page.next_cursor,
            "has_more": page.next_cursor is not None,
        },
    }


def delete_result(workspace_id: str, pointer: str) -> dict[str, object]:
    """
    함수 이름: delete_result()
    기능: 등록 해제 결과를 PointerDeleteResult(effect=unregistered)로 만든다.
    인자: workspace_id -> 범위, pointer -> 요청 URI
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "effect": "unregistered",
        "kind": "source",
        "pointer": pointer,
        "workspace_id": workspace_id,
    }


def _selection(record: SourceRecord, span: ByteSpan) -> dict[str, object]:
    """
    함수 이름: _selection()
    기능: 반환 본문이 원본의 어느 구간인지 revision·원본 SHA-256과 함께 표시한다.
    인자: record -> 등록 레코드, span -> 원본 바이트 구간
    반환값: 계약 PointerSelection
    작성 날짜: 2026/11/10
    """
    return {
        "revision": record.revision,
        "content_sha256": record.fingerprint,
        "range": {"type": "byte", "start": span.start, "end": span.end},
    }


def read_result(pointer: str, outcome: ReadOutcome) -> dict[str, object]:
    """
    함수 이름: read_result()
    기능: 읽기 결과를 PointerReadResult로 바꾼다. 비어 있거나 JSON 값이면 selection을 넣지 않는다.
    인자: pointer -> 요청 URI, outcome -> 읽기 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    record = outcome.record
    provenance: dict[str, object] = {
        "media_type": record.media_type,
        "byte_size": record.byte_size,
        "revision": record.revision,
        "display_name": _display_name(record),
    }
    if record.location is SourceLocation.WORKSPACE:
        provenance["relative_path"] = record.relative_path.as_posix()
    if outcome.span is not None and outcome.pdf_page is not None:
        provenance["selection"] = page_selection(
            record.revision,
            record.fingerprint,
            outcome.pdf_page,
            outcome.span.start,
            outcome.span.end,
        )
    elif outcome.span is not None:
        provenance["selection"] = _selection(record, outcome.span)
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


def search_result(pointer: str, outcome: SearchOutcome) -> dict[str, object]:
    """
    함수 이름: search_result()
    기능: 검색 결과를 PointerSearchResult로 바꾼다. 일치마다 원본 구간 selection을 붙인다.
    인자: pointer -> 요청 URI, outcome -> 검색 결과
    반환값: 계약 JSON 사전
    작성 날짜: 2026/11/10
    """
    record = outcome.record
    matches = [
        {
            "line": match.line,
            "content": match.content,
            "byte_offset": match.byte_offset,
            **(
                {"selection": _selection(record, match.span)}
                if match.span.end > match.span.start
                else {}
            ),
        }
        for match in outcome.matches
    ]
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
