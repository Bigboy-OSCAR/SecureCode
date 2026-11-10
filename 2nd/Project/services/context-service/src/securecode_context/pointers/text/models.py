"""Source·Runtime 포인터가 함께 쓰는 텍스트 읽기 값 객체(selector, 구간, 일치, 이어 읽기 위치)."""

from dataclasses import dataclass
from typing import Literal

from securecode_context.pointers.limits import MAX_READ_BYTES, MAX_READ_TOKENS

type SelectorKind = Literal["line", "byte", "section", "json_path", "pdf_page"]


@dataclass(frozen=True)
class Selector:
    """
    클래스 이름: Selector
    기능: 계약 PointerSelector 하나. 종류별로 쓰는 필드만 채운다.
    작성 날짜: 2026/11/10
    """

    kind: SelectorKind
    start: int | None = None
    end: int | None = None
    section: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class ByteSpan:
    """
    클래스 이름: ByteSpan
    기능: 원본의 반열린 UTF-8 바이트 구간 [start, end).
    작성 날짜: 2026/11/10
    """

    start: int
    end: int


@dataclass(frozen=True)
class SearchMatch:
    """
    클래스 이름: SearchMatch
    기능: 일치 하나. byte_offset은 일치 시작, span은 반환한 미리보기 구간이다.
    작성 날짜: 2026/11/10
    """

    line: int
    byte_offset: int
    content: str
    span: ByteSpan


@dataclass(frozen=True)
class CursorState:
    """
    클래스 이름: CursorState
    기능: 다음 요청이 이어갈 위치. read는 [offset, end) 남은 구간, search는 scan 위치와 그 줄 번호다.
        json은 원본이 아닌 재직렬화 값 안의 위치라 원본 크기와 비교하지 않는다.
        clipped는 요청 끝이 UTF-8 문자 중간이라 그 앞에서 끝냈다는 표시다.
    작성 날짜: 2026/11/10
    """

    offset: int
    end: int
    line: int = 1
    in_json: bool = False
    clipped: bool = False


@dataclass(frozen=True)
class TextWindow:
    """
    클래스 이름: TextWindow
    기능: 상한 안에 맞춘 한 번의 읽기 결과. span이 있으면 content는 원본의 정확한 그 구간이다.
    작성 날짜: 2026/11/10
    """

    content: str
    span: ByteSpan | None
    truncated: bool
    following: CursorState | None
    token_count: int
    count_mode: str


@dataclass(frozen=True)
class ReadRequest:
    """
    클래스 이름: ReadRequest
    기능: 검증 전 PointerReadRequest.
    작성 날짜: 2026/11/10
    """

    pointer: str
    selector: Selector | None = None
    max_bytes: int = MAX_READ_BYTES
    max_tokens: int = MAX_READ_TOKENS
    cursor: str | None = None


@dataclass(frozen=True)
class SearchRequest:
    """
    클래스 이름: SearchRequest
    기능: 검증 전 PointerSearchRequest.
    작성 날짜: 2026/11/10
    """

    pointer: str
    query: str
    limit: int = 20
    max_bytes: int = MAX_READ_BYTES
    max_tokens: int = MAX_READ_TOKENS
    cursor: str | None = None
