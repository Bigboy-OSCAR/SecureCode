"""Source 부분 읽기(source.read). 공용 TextEngine 위에 등록부 확인과 cursor 묶기를 더한다.

순서: resolve(범위·revision·경로) → 같은 핸들의 identity 확인 → 구간 계산 → 상한 안 읽기 →
핸들 identity 재확인 → resolve 재확인. 어느 단계든 원본이 바뀌면 SOURCE_CHANGED다.
"""

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.source import media
from securecode_context.pointers.source.models import SourceRecord
from securecode_context.pointers.source.paths import identity_of, open_verified
from securecode_context.pointers.source.read_cursor import (
    decode_cursor,
    encode_cursor,
    request_digest,
)
from securecode_context.pointers.source.read_models import ReadOutcome, ReadRequest, Selector
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.text.caps import check_caps
from securecode_context.pointers.text.engine import (
    TextEngine,
    changed_error,
    invalid_selector,
    selector_shape,
)
from securecode_context.pointers.text.io_meter import IoStats, MeteredFile


def check_source_selector(record: SourceRecord, selector: Selector | None) -> None:
    """
    함수 이름: check_source_selector()
    기능: 형식이 광고한 selector만 허용한다. PDF 본문은 4.9 페이지 도구로만 읽는다.
    인자: record -> 등록 레코드, selector -> 요청 selector
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if record.media_type == media.PDF_MEDIA:
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FORMAT,
            "PDF는 페이지 추출 후 PDF 도구로 읽습니다.",
            {"reason": "pdf_requires_page_tool"},
        )
    supported = media.supported_selectors(record.media_type, record.byte_size)
    if selector is not None and selector.kind not in supported:
        if selector.kind == "json_path" and record.media_type == media.JSON_MEDIA:
            raise ServiceError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "JSON 구조 조회는 8 MiB 이하만 지원합니다. 줄·바이트 범위로 읽으세요.",
                {"reason": "json_structured_limit"},
            )
        raise invalid_selector("selector_not_supported")


class SourceReader:
    """
    클래스 이름: SourceReader
    기능: Source adapter의 읽기 연산. 3.6 route, 4.8 resolver가 사용한다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, registry: SourceRegistry, counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: 등록부와 공용 읽기 엔진을 준비한다.
        인자: registry -> 4.5 SourceRegistry, counter -> 본문 TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._registry = registry
        self._engine = TextEngine(counter)

    def read(self, workspace_id: str, request: ReadRequest) -> ReadOutcome:
        """
        함수 이름: read()
        기능: 요청 구간을 상한 안에서 읽고 원본 구간·revision·hash와 일치하는 결과를 돌려준다.
        인자: workspace_id -> 인증된 범위, request -> 읽기 요청
        반환값: ReadOutcome(io는 계측값)
        작성 날짜: 2026/11/10
        """
        check_caps(request.max_bytes, request.max_tokens)
        resolved = self._registry.resolve(workspace_id, request.pointer)
        record = resolved.record
        check_source_selector(record, request.selector)
        digest = request_digest("read", selector_shape(request.selector))
        version = (record.source_id, record.revision, record.fingerprint, record.identity)
        stats = IoStats()
        with open_verified(resolved.root, record.relative_path) as raw:
            if identity_of(raw) != record.identity:
                raise changed_error()
            file = MeteredFile(raw, stats)
            state = (
                decode_cursor(request.cursor, record, digest)
                if request.cursor
                else self._engine.start(file, version, record.byte_size, request.selector)
            )
            caps = (request.max_bytes, request.max_tokens)
            window = self._engine.window(file, record.byte_size, request.selector, state, caps)
            if identity_of(raw) != record.identity:
                raise changed_error()
        self._registry.resolve(workspace_id, request.pointer)
        cursor = None
        if window.following is not None:
            cursor = encode_cursor(record, digest, window.following)
        return ReadOutcome(
            record,
            window.content,
            window.span,
            window.truncated,
            cursor,
            window.token_count,
            window.count_mode,
            stats,
        )
