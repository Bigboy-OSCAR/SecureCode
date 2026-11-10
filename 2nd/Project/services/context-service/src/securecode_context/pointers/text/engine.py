"""Source·Runtime 공용 텍스트 읽기 엔진: selector를 원본 구간으로 바꾸고 bytes/token 상한 안에서 한 창을 읽는다.

byte/line/section은 원본의 정확한 구간을 seek로 읽는다. json_path는 8 MiB 이하 전체 파싱이다.
원본 확인(범위·revision·hash)과 cursor 묶기는 호출자(Source/Runtime) 몫이다.
"""

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.text.caps import fit_text
from securecode_context.pointers.text.io_meter import MeteredFile
from securecode_context.pointers.text.json_select import select_json
from securecode_context.pointers.text.line_index import LineIndex, build_line_index, line_span
from securecode_context.pointers.text.markdown import Heading, build_headings, section_span
from securecode_context.pointers.text.memo import BoundedMemo
from securecode_context.pointers.text.models import ByteSpan, CursorState, Selector, TextWindow


def invalid_selector(reason: str) -> ServiceError:
    """
    함수 이름: invalid_selector()
    기능: selector 오류를 만든다.
    인자: reason -> details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(ErrorCode.INVALID_SELECTOR, "범위가 올바르지 않습니다.", {"reason": reason})


def changed_error() -> ServiceError:
    """
    함수 이름: changed_error()
    기능: 읽는 도중 원본 변경 오류를 만든다.
    인자: 없음
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 읽기 도중 바뀌었습니다. 다시 읽으세요.")


def selector_shape(selector: Selector | None) -> object:
    """
    함수 이름: selector_shape()
    기능: cursor를 묶을 selector 표현을 만든다.
    인자: selector -> 요청 selector
    반환값: JSON 표현 가능한 값
    작성 날짜: 2026/11/10
    """
    if selector is None:
        return None
    return [selector.kind, selector.start, selector.end, selector.section, selector.path]


def _is_continuation(file: MeteredFile, offset: int) -> bool:
    """
    함수 이름: _is_continuation()
    기능: offset의 바이트가 UTF-8 연속 바이트인지 확인한다.
    인자: file -> 계측 핸들, offset -> 원본 위치
    반환값: 연속 바이트이면 True
    작성 날짜: 2026/11/10
    """
    return file.read_range(offset, offset + 1)[0] & 0xC0 == 0x80


def _byte_state(file: MeteredFile, byte_size: int, selector: Selector) -> CursorState:
    """
    함수 이름: _byte_state()
    기능: 0부터 시작하는 반열린 바이트 구간을 검사한다. 시작이 문자 중간이면 거부하고,
        끝이 문자 중간이면 가장 긴 유효 앞부분까지로 줄이고 clipped로 표시한다(POINTERS.md 3).
    인자: file -> 계측 핸들, byte_size -> 원본 크기, selector -> byte selector
    반환값: CursorState
    작성 날짜: 2026/11/10
    """
    start = selector.start or 0
    end = byte_size if selector.end is None else selector.end
    if end < start:
        raise invalid_selector("end_before_start")
    if end > byte_size:
        raise invalid_selector("byte_out_of_range")
    if start < end and _is_continuation(file, start):
        raise invalid_selector("utf8_boundary")
    clipped_end = end
    while start < clipped_end < byte_size and _is_continuation(file, clipped_end):
        clipped_end -= 1
    return CursorState(start, clipped_end, clipped=clipped_end != end)


class TextEngine:
    """
    클래스 이름: TextEngine
    기능: 줄/제목 색인 캐시를 가진 공용 읽기 엔진. 색인 키는 호출자가 내용에 묶어 준다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: TokenCounter와 색인 캐시를 준비한다.
        인자: counter -> 본문 TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.counter = counter
        self._lines: BoundedMemo[LineIndex] = BoundedMemo()
        self._headings: BoundedMemo[tuple[Heading, ...]] = BoundedMemo()

    def start(
        self,
        file: MeteredFile,
        version: tuple[object, ...],
        byte_size: int,
        selector: Selector | None,
    ) -> CursorState:
        """
        함수 이름: start()
        기능: selector를 원본 바이트 구간(또는 JSON 값 길이)으로 바꾼다. 없으면 처음부터다.
        인자: file -> 계측 핸들, version -> 내용에 묶인 색인 키, byte_size -> 원본 크기, selector -> 범위
        반환값: 처음 읽을 CursorState
        작성 날짜: 2026/11/10
        """
        if selector is None:
            return CursorState(0, byte_size)
        if selector.kind == "byte":
            return _byte_state(file, byte_size, selector)
        if selector.kind == "line":
            index = self._lines.get_or_build(
                ("lines", *version), lambda: build_line_index(file, byte_size)
            )
            first = selector.start or 1
            span = line_span(file, index, first, first if selector.end is None else selector.end)
            return CursorState(span.start, span.end)
        if selector.kind == "section":
            headings = self._headings.get_or_build(
                ("headings", *version), lambda: build_headings(file)
            )
            span = section_span(headings, selector.section or "", byte_size)
            return CursorState(span.start, span.end)
        if selector.kind == "json_path":
            value = select_json(file, byte_size, selector.path or "")
            return CursorState(0, len(value.encode("utf-8")), in_json=True)
        raise invalid_selector("selector_not_supported")

    def window(
        self,
        file: MeteredFile,
        byte_size: int,
        selector: Selector | None,
        state: CursorState,
        caps: tuple[int, int],
    ) -> TextWindow:
        """
        함수 이름: window()
        기능: 남은 구간에서 상한만큼만 읽어 맞추고 다음 위치를 정한다.
        인자: file -> 계측 핸들, byte_size -> 원본 크기, selector -> 요청 selector,
            state -> 읽을 위치, caps -> (max_bytes, max_tokens)
        반환값: TextWindow
        작성 날짜: 2026/11/10
        """
        max_bytes, max_tokens = caps
        window_end = min(state.end, state.offset + max_bytes)
        if state.in_json:
            path = selector.path if selector else None
            value = select_json(file, byte_size, path or "")
            data = value.encode("utf-8")[state.offset : window_end]
        else:
            data = file.read_range(state.offset, window_end)
        if len(data) != window_end - state.offset:
            raise changed_error()
        fitted = fit_text(
            data, window_end == state.end, state.offset, max_bytes, max_tokens, self.counter
        )
        next_offset = state.offset + fitted.used
        if fitted.used == 0 and next_offset < state.end:
            raise ServiceError(
                ErrorCode.BUDGET_EXCEEDED, "상한이 너무 작습니다.", {"reason": "cap_too_small"}
            )
        following = None
        if next_offset < state.end:
            following = CursorState(next_offset, state.end, 1, state.in_json, state.clipped)
        span = None if state.in_json or fitted.used == 0 else ByteSpan(state.offset, next_offset)
        truncated = next_offset < state.end or state.clipped
        return TextWindow(
            fitted.text, span, truncated, following, fitted.token_count, fitted.count_mode
        )
