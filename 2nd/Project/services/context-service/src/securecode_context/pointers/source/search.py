"""Source 리터럴 검색(source.search). 결과 수·bytes·tokens 상한과 revision에 묶인 이어 읽기 cursor를 적용한다.

검색어는 대소문자를 구분하는 리터럴이며 실행하지 않는다. 한글은 지우지 않고 NFC·NFD 두 형태를 함께
찾는다. 최초 검색은 순차 scan이다(요청당 8 MiB·2초 상한, text/search_scan.py).
"""

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.source import media
from securecode_context.pointers.source.paths import identity_of, open_verified
from securecode_context.pointers.source.read_cursor import (
    decode_cursor,
    encode_cursor,
    request_digest,
)
from securecode_context.pointers.source.read_models import SearchOutcome, SearchRequest
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.text import search_scan
from securecode_context.pointers.text.engine import changed_error
from securecode_context.pointers.text.io_meter import IoStats, MeteredFile
from securecode_context.pointers.text.models import CursorState
from securecode_context.pointers.text.searching import check_search, fit_matches, query_patterns


class SourceSearcher:
    """
    클래스 이름: SourceSearcher
    기능: Source adapter의 검색 연산.
    작성 날짜: 2026/11/10
    """

    def __init__(self, registry: SourceRegistry, counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: 등록부와 TokenCounter를 보관한다.
        인자: registry -> 4.5 SourceRegistry, counter -> 본문 TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._registry = registry
        self._counter = counter

    def search(self, workspace_id: str, request: SearchRequest) -> SearchOutcome:
        """
        함수 이름: search()
        기능: 원본에서 검색어를 찾아 줄·바이트 위치와 짧은 원본 구간을 돌려준다.
        인자: workspace_id -> 인증된 범위, request -> 검색 요청
        반환값: SearchOutcome(io는 계측값)
        작성 날짜: 2026/11/10
        """
        check_search(request.query, request.limit, request.max_bytes, request.max_tokens)
        resolved = self._registry.resolve(workspace_id, request.pointer)
        record = resolved.record
        if "search" not in media.available_operations(record.media_type):
            raise ServiceError(
                ErrorCode.UNSUPPORTED_FORMAT,
                "이 형식은 검색할 수 없습니다.",
                {"reason": "no_search"},
            )
        digest = request_digest("search", request.query)
        stats = IoStats()
        with open_verified(resolved.root, record.relative_path) as raw:
            if identity_of(raw) != record.identity:
                raise changed_error()
            state = (
                decode_cursor(request.cursor, record, digest)
                if request.cursor
                else CursorState(0, record.byte_size)
            )
            patterns = query_patterns(request.query)
            file = MeteredFile(raw, stats)
            result = search_scan.scan(file, state.offset, state.line, patterns, request.limit)
            if identity_of(raw) != record.identity:
                raise changed_error()
        self._registry.resolve(workspace_id, request.pointer)
        caps = (request.max_bytes, request.max_tokens)
        kept, resume, tokens, mode = fit_matches(result.matches, result.resume, caps, self._counter)
        cursor = None
        if resume is not None:
            following = CursorState(resume[0], record.byte_size, resume[1])
            cursor = encode_cursor(record, digest, following)
        return SearchOutcome(record, kept, cursor is not None, cursor, tokens, mode, stats)
