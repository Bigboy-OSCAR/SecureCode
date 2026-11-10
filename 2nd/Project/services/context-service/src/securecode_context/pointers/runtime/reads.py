"""Runtime 부분 읽기·검색. 공용 TextEngine·search_scan 위에 세션 범위 확인과 청크 checksum 검증을 더한다.

모든 원문 바이트는 VerifiedBlob을 거치므로 저장 뒤 손상된 청크는 원문 대신 오류가 된다.
cursor는 workspace·session·pointer와 저장 checksum에 묶는다.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.runtime.blob import VerifiedBlob, blob_path
from securecode_context.pointers.runtime.media import supported_selectors
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.text import search_scan
from securecode_context.pointers.text.caps import check_caps
from securecode_context.pointers.text.cursor import decode_state, encode_state, request_digest
from securecode_context.pointers.text.engine import TextEngine, invalid_selector, selector_shape
from securecode_context.pointers.text.io_meter import IoStats, MeteredFile
from securecode_context.pointers.text.models import (
    ByteSpan,
    CursorState,
    ReadRequest,
    SearchMatch,
    SearchRequest,
)
from securecode_context.pointers.text.searching import check_search, fit_matches, query_patterns

_URI = re.compile(
    r"securecode://runtime/(?P<w>[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127})/"
    r"(?P<s>[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127})/"
    r"(?P<p>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\?v=1"
)


@dataclass(frozen=True)
class RuntimeReadOutcome:
    """
    클래스 이름: RuntimeReadOutcome
    기능: Runtime 읽기 결과. span이 있으면 content는 저장된 출력의 정확한 그 구간이다.
    작성 날짜: 2026/11/10
    """

    row: Any
    content: str
    span: ByteSpan | None
    truncated: bool
    next_cursor: str | None
    token_count: int
    count_mode: str
    io: IoStats = field(default_factory=IoStats)


@dataclass(frozen=True)
class RuntimeSearchOutcome:
    """
    클래스 이름: RuntimeSearchOutcome
    기능: Runtime 검색 결과와 이어 읽기 cursor.
    작성 날짜: 2026/11/10
    """

    row: Any
    matches: list[SearchMatch]
    truncated: bool
    next_cursor: str | None
    token_count: int
    count_mode: str
    io: IoStats = field(default_factory=IoStats)


def pointer_id_of(pointer: str, workspace_id: str, session_id: str) -> str:
    """
    함수 이름: pointer_id_of()
    기능: URI 형식 → 범위 순서로 확인하고 포인터 ID를 돌려준다.
    인자: pointer -> Runtime URI, workspace_id/session_id -> 호출 범위
    반환값: UUID 문자열
    작성 날짜: 2026/11/10
    """
    match = _URI.fullmatch(pointer)
    if match is None:
        raise ServiceError(ErrorCode.INVALID_POINTER, "Runtime Pointer 형식이 올바르지 않습니다.")
    if (match["w"], match["s"]) != (workspace_id, session_id):
        raise ServiceError(ErrorCode.FORBIDDEN, "다른 세션의 포인터입니다.")
    return match["p"]


class RuntimeReader:
    """
    클래스 이름: RuntimeReader
    기능: Runtime adapter의 읽기·검색 연산(4.4 runtime_read/runtime_search 도구가 사용).
    작성 날짜: 2026/11/10
    """

    def __init__(self, store: RuntimeStore, counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: 저장소와 공용 읽기 엔진을 준비한다.
        인자: store -> RuntimeStore, counter -> 본문 TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._store = store
        self._engine = TextEngine(counter)

    def _open(self, scope: tuple[str, str], pointer_id: str) -> tuple[Any, VerifiedBlob]:
        """
        함수 이름: _open()
        기능: 범위·만료를 확인한 행과 checksum 검증 blob을 연다.
        인자: scope -> (workspace, session), pointer_id -> UUID
        반환값: (행, VerifiedBlob)
        작성 날짜: 2026/11/10
        """
        row = self._store.load(scope[0], scope[1], pointer_id)
        path = blob_path(self._store.blobs, scope[0], scope[1], pointer_id)
        return row, VerifiedBlob(path, row["byte_size"], row["chunk_digests"])

    def read(self, workspace_id: str, session_id: str, request: ReadRequest) -> RuntimeReadOutcome:
        """
        함수 이름: read()
        기능: selector 구간을 bytes/tokens 상한 안에서 읽는다.
        인자: workspace_id/session_id -> 인증된 범위, request -> 읽기 요청
        반환값: RuntimeReadOutcome
        작성 날짜: 2026/11/10
        """
        check_caps(request.max_bytes, request.max_tokens)
        pointer_id = pointer_id_of(request.pointer, workspace_id, session_id)
        row, blob = self._open((workspace_id, session_id), pointer_id)
        selector = request.selector
        if selector is not None and selector.kind not in supported_selectors(
            row["media_type"], row["byte_size"]
        ):
            blob.close()
            raise invalid_selector("selector_not_supported")
        scope, version = [workspace_id, session_id, pointer_id], [row["checksum"][:16]]
        digest = request_digest("read", selector_shape(selector))
        stats = IoStats()
        try:
            file = MeteredFile(blob, stats)
            state = (
                decode_state(request.cursor, scope, version, digest, row["byte_size"])
                if request.cursor
                else self._engine.start(file, (pointer_id, *version), row["byte_size"], selector)
            )
            caps = (request.max_bytes, request.max_tokens)
            window = self._engine.window(file, row["byte_size"], selector, state, caps)
        finally:
            blob.close()
        cursor = None
        if window.following is not None:
            cursor = encode_state(scope, version, digest, window.following)
        return RuntimeReadOutcome(
            row, window.content, window.span, window.truncated, cursor,
            window.token_count, window.count_mode, stats,
        )  # fmt: skip

    def search(
        self, workspace_id: str, session_id: str, request: SearchRequest
    ) -> RuntimeSearchOutcome:
        """
        함수 이름: search()
        기능: 저장된 출력에서 리터럴을 찾는다. 요청당 scan 8 MiB·2초 상한과 cursor를 쓴다.
        인자: workspace_id/session_id -> 인증된 범위, request -> 검색 요청
        반환값: RuntimeSearchOutcome
        작성 날짜: 2026/11/10
        """
        check_search(request.query, request.limit, request.max_bytes, request.max_tokens)
        pointer_id = pointer_id_of(request.pointer, workspace_id, session_id)
        row, blob = self._open((workspace_id, session_id), pointer_id)
        scope, version = [workspace_id, session_id, pointer_id], [row["checksum"][:16]]
        digest = request_digest("search", request.query)
        stats = IoStats()
        try:
            state = (
                decode_state(request.cursor, scope, version, digest, row["byte_size"])
                if request.cursor
                else CursorState(0, row["byte_size"])
            )
            file = MeteredFile(blob, stats)
            patterns = query_patterns(request.query)
            result = search_scan.scan(file, state.offset, state.line, patterns, request.limit)
        finally:
            blob.close()
        caps = (request.max_bytes, request.max_tokens)
        kept, resume, tokens, mode = fit_matches(
            result.matches, result.resume, caps, self._engine.counter
        )
        cursor = None
        if resume is not None:
            following = CursorState(resume[0], row["byte_size"], resume[1])
            cursor = encode_state(scope, version, digest, following)
        return RuntimeSearchOutcome(row, kept, cursor is not None, cursor, tokens, mode, stats)
