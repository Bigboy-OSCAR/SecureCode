"""PDF 페이지 읽기·검색(4.9). 캐시한 페이지 텍스트만 상한 안에서 돌려준다. 요청하지 않은 페이지는 읽지 않는다.

읽기는 계약 pdf_page selector(start~end 페이지)이고 한 번에 한 페이지 구간만 돌려준다. 남은 부분은
cursor로 잇는다. 모든 결과에는 페이지 번호·페이지 텍스트 안 바이트 구간·파서 버전 selection이 붙는다.
"""

from dataclasses import dataclass

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.pdf.cache import PdfManifest, PdfPageCache, cache_key
from securecode_context.pdf.limits import MAX_PAGE_TEXT_BYTES, PARSER_VERSION, PDF_MEDIA
from securecode_context.pointers.source.models import SourceRecord
from securecode_context.pointers.source.read_models import ByteSpan, ReadOutcome, ReadRequest
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.text.caps import check_caps, fit_text
from securecode_context.pointers.text.cursor import decode_state, encode_state, request_digest
from securecode_context.pointers.text.models import CursorState, SearchMatch
from securecode_context.pointers.text.searching import check_search, fit_matches, query_patterns

SNIPPET_BYTES = 240
_STATE_ERRORS = {
    "unsupported": (ErrorCode.UNSUPPORTED_FORMAT, "PDF에서 텍스트를 읽을 수 없습니다."),
    "failed": (ErrorCode.PARSE_FAILED, "PDF를 파싱하지 못했습니다."),
}


@dataclass(frozen=True)
class PdfMatch:
    """
    클래스 이름: PdfMatch
    기능: 검색 일치 하나와 그 페이지 번호.
    작성 날짜: 2026/11/10
    """

    page: int
    match: SearchMatch


class PdfPages:
    """
    클래스 이름: PdfPages
    기능: 등록·파싱된 PDF Source의 페이지 구간 읽기와 리터럴 검색.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self, registry: SourceRegistry, cache: PdfPageCache, counter: TokenCounter
    ) -> None:
        """
        함수 이름: __init__()
        기능: 등록부·페이지 캐시·계수기를 저장한다.
        인자: registry -> Source 등록부, cache -> 페이지 캐시, counter -> TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._registry = registry
        self._cache = cache
        self._counter = counter

    def open(self, workspace_id: str, pointer: str) -> tuple[SourceRecord, str, PdfManifest]:
        """
        함수 이름: open()
        기능: 원본·revision을 다시 확인하고 현재 해시·파서 버전의 완료된 캐시를 연다.
        인자: workspace_id -> 인증된 범위, pointer -> 현재 revision URI
        반환값: (레코드, 캐시 키, manifest)
        작성 날짜: 2026/11/10
        """
        record = self._registry.resolve(workspace_id, pointer).record
        if record.media_type != PDF_MEDIA:
            raise ServiceError(ErrorCode.INVALID_SELECTOR, "PDF가 아닙니다.", {"reason": "not_pdf"})
        key = cache_key(record.fingerprint, PARSER_VERSION)
        manifest = self._cache.load(key)
        if manifest is None:
            raise ServiceError(
                ErrorCode.INDEX_NOT_READY,
                "PDF 파싱이 끝나지 않았습니다. pdf_parse 상태를 확인하세요.",
                {"reason": "pdf_not_parsed"},
            )
        if manifest.state in _STATE_ERRORS:
            code, message = _STATE_ERRORS[manifest.state]
            raise ServiceError(code, message, {"reason": manifest.reason})
        return record, key, manifest

    def page_bytes(self, key: str, manifest: PdfManifest, page: int) -> bytes:
        """
        함수 이름: page_bytes()
        기능: 범위 안의 읽을 수 있는 페이지 텍스트를 읽는다. 범위 밖·제외 페이지는 INVALID_SELECTOR다.
        인자: key -> 캐시 키, manifest -> manifest, page -> 페이지 번호
        반환값: UTF-8 바이트
        작성 날짜: 2026/11/10
        """
        if not 1 <= page <= manifest.page_count:
            raise ServiceError(
                ErrorCode.INVALID_SELECTOR,
                f"페이지는 1~{manifest.page_count}입니다.",
                {"reason": "page_out_of_range", "page_count": manifest.page_count},
            )
        meta = manifest.pages[page]
        if "excluded" in meta:
            raise ServiceError(
                ErrorCode.INVALID_SELECTOR,
                "이 페이지에는 읽을 텍스트가 없습니다.",
                {"reason": "page_excluded", "page_reason": meta["excluded"]},
            )
        return self._cache.page_bytes(key, manifest, page)

    def read_span(
        self, workspace_id: str, pointer: str, page: int, span: tuple[int, int | None],
        caps: tuple[int, int],
    ) -> ReadOutcome:  # fmt: skip
        """
        함수 이름: read_span()
        기능: 한 페이지 텍스트의 [start, end) 구간을 바이트·토큰 상한 안에서 앞부터 읽는다(Selector용).
        인자: workspace_id/pointer -> 대상, page -> 페이지, span -> (start, end 또는 None=끝),
            caps -> (max_bytes, max_tokens)
        반환값: ReadOutcome(pdf_page 설정)
        작성 날짜: 2026/11/10
        """
        check_caps(*caps)
        record, key, manifest = self.open(workspace_id, pointer)
        data = self.page_bytes(key, manifest, page)
        start, end = span[0], len(data) if span[1] is None else span[1]
        if not 0 <= start < end <= len(data):
            raise ServiceError(ErrorCode.INVALID_SELECTOR, "페이지 구간이 올바르지 않습니다.")
        fitted = fit_text(data[start:end], True, start, caps[0], caps[1], self._counter)
        stop = start + fitted.used
        return ReadOutcome(
            record, fitted.text, ByteSpan(start, stop), stop < end, None,
            fitted.token_count, fitted.count_mode, pdf_page=page,
        )  # fmt: skip

    def read(self, workspace_id: str, request: ReadRequest) -> ReadOutcome:
        """
        함수 이름: read()
        기능: pdf_page selector의 첫 페이지(또는 cursor 위치)부터 한 페이지 구간만 읽는다.
            페이지가 남으면 다음 읽을 수 있는 페이지로, 페이지가 잘리면 같은 페이지 다음 위치로 cursor를 준다.
        인자: workspace_id -> 인증된 범위, request -> 읽기 요청
        반환값: ReadOutcome(pdf_page 설정)
        작성 날짜: 2026/11/10
        """
        check_caps(request.max_bytes, request.max_tokens)
        selector = request.selector
        if selector is None or selector.kind != "pdf_page" or selector.start is None:
            raise ServiceError(
                ErrorCode.INVALID_SELECTOR, "PDF는 pdf_page selector로 읽습니다.",
                {"reason": "pdf_page_required"},
            )  # fmt: skip
        record, _key, manifest = self.open(workspace_id, request.pointer)
        last = selector.end or selector.start
        if last < selector.start:
            raise ServiceError(ErrorCode.INVALID_SELECTOR, "끝 페이지가 시작보다 앞입니다.")
        scope = [workspace_id, record.source_id]
        version: list[object] = [record.revision, record.fingerprint, PARSER_VERSION]
        digest = request_digest("pdf_read", [selector.start, last])
        page, offset = selector.start, 0
        if request.cursor:
            state = decode_state(request.cursor, scope, version, digest, MAX_PAGE_TEXT_BYTES)
            page, offset = state.offset, state.line - 1
        if last > manifest.page_count:
            raise ServiceError(
                ErrorCode.INVALID_SELECTOR,
                f"페이지는 1~{manifest.page_count}입니다.",
                {"reason": "page_out_of_range", "page_count": manifest.page_count},
            )
        outcome = self.read_span(
            workspace_id,
            request.pointer,
            page,
            (offset, None),
            (request.max_bytes, request.max_tokens),
        )
        following = None
        assert outcome.span is not None
        if outcome.truncated:
            following = CursorState(page, last, outcome.span.end + 1)
        else:
            nxt = next(
                (p for p in range(page + 1, last + 1) if "excluded" not in manifest.pages[p]), None
            )
            if nxt is not None:
                following = CursorState(nxt, last, 1)
        cursor = encode_state(scope, version, digest, following) if following else None
        return ReadOutcome(
            record, outcome.content, outcome.span, following is not None, cursor,
            outcome.token_count, outcome.count_mode, pdf_page=page,
        )  # fmt: skip

    def search(
        self, workspace_id: str, pointer: str, query: str, limit: int, caps: tuple[int, int]
    ) -> tuple[SourceRecord, list[PdfMatch], bool, int, str]:
        """
        함수 이름: search()
        기능: 읽을 수 있는 페이지에서 리터럴 검색어(NFC·NFD)를 찾고 그 줄의 짧은 미리보기를 돌려준다.
        인자: workspace_id/pointer -> 대상, query -> 검색어, limit -> 최대 일치 수, caps -> 상한
        반환값: (레코드, 일치, 잘림 여부, 토큰 수, count_mode)
        작성 날짜: 2026/11/10
        """
        check_search(query, limit, *caps)
        record, key, manifest = self.open(workspace_id, pointer)
        patterns = query_patterns(query)
        found: list[PdfMatch] = []
        for page, meta in sorted(manifest.pages.items()):
            if "excluded" in meta or len(found) > limit:
                continue
            data = self._cache.page_bytes(key, manifest, page)
            found += [PdfMatch(page, match) for match in _page_matches(data, patterns)]
        kept, _resume, tokens, mode = fit_matches(
            [item.match for item in found[:limit]], None, caps, self._counter
        )
        return record, found[: len(kept)], len(found) > len(kept), tokens, mode


def _page_matches(data: bytes, patterns: list[bytes]) -> list[SearchMatch]:
    """
    함수 이름: _page_matches()
    기능: 페이지 텍스트에서 일치를 찾고 일치를 포함한 줄 미리보기(최대 240바이트, UTF-8 경계)를 만든다.
    인자: data -> 페이지 UTF-8 텍스트, patterns -> 검색 패턴
    반환값: 일치 목록(줄 번호는 페이지 안 1부터)
    작성 날짜: 2026/11/10
    """
    hits = sorted({at for pattern in patterns for at in _find_all(data, pattern)})
    matches = []
    for at in hits:
        start = data.rfind(b"\n", 0, at) + 1
        end = data.find(b"\n", at)
        end = len(data) if end < 0 else end
        start = max(start, at - SNIPPET_BYTES // 2)
        end = min(end, start + SNIPPET_BYTES)
        text = data[start:end].decode("utf-8", errors="ignore")
        start = data.find(text.encode("utf-8"), start)
        span = ByteSpan(start, start + len(text.encode("utf-8")))
        matches.append(SearchMatch(data.count(b"\n", 0, at) + 1, at, text, span))
    return matches


def _find_all(data: bytes, pattern: bytes) -> list[int]:
    """
    함수 이름: _find_all()
    기능: 겹치지 않는 모든 시작 위치를 찾는다.
    인자: data -> 텍스트, pattern -> 패턴
    반환값: 위치 목록
    작성 날짜: 2026/11/10
    """
    found, at = [], data.find(pattern)
    while at >= 0:
        found.append(at)
        at = data.find(pattern, at + len(pattern))
    return found
