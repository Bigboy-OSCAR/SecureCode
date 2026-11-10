"""Source 읽기·검색 cursor. workspace·source를 범위로, revision·fingerprint를 내용 버전으로 묶는다."""

from securecode_context.pointers.source.models import SourceRecord
from securecode_context.pointers.text.cursor import decode_state, encode_state, request_digest
from securecode_context.pointers.text.models import CursorState

__all__ = ["decode_cursor", "encode_cursor", "request_digest"]


def _binding(record: SourceRecord) -> tuple[list[str], list[object]]:
    """
    함수 이름: _binding()
    기능: 등록 레코드의 범위와 내용 버전을 만든다.
    인자: record -> 등록 레코드
    반환값: (범위, 버전)
    작성 날짜: 2026/11/10
    """
    return [record.workspace_id, record.source_id], [record.revision, record.fingerprint[:16]]


def encode_cursor(record: SourceRecord, digest: str, state: CursorState) -> str:
    """
    함수 이름: encode_cursor()
    기능: 다음 위치를 Source 범위·버전에 묶은 cursor로 만든다.
    인자: record -> 확인한 등록, digest -> 요청 해시, state -> 다음 위치
    반환값: cursor
    작성 날짜: 2026/11/10
    """
    scope, version = _binding(record)
    return encode_state(scope, version, digest, state)


def decode_cursor(cursor: str, record: SourceRecord, digest: str) -> CursorState:
    """
    함수 이름: decode_cursor()
    기능: 다른 원본·요청은 INVALID_POINTER, 바뀐 revision·내용은 SOURCE_CHANGED로 거부한다.
    인자: cursor -> 요청 cursor, record -> 현재 등록, digest -> 현재 요청 해시
    반환값: CursorState
    작성 날짜: 2026/11/10
    """
    scope, version = _binding(record)
    return decode_state(cursor, scope, version, digest, record.byte_size)
