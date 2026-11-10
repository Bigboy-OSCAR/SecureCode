"""Source 부분 읽기·검색의 요청과 결과(계약 PointerRead/SearchRequest·Result의 내부 형태)."""

from dataclasses import dataclass, field

from securecode_context.pointers.source.models import SourceRecord
from securecode_context.pointers.text.io_meter import IoStats
from securecode_context.pointers.text.models import (
    ByteSpan,
    ReadRequest,
    SearchMatch,
    SearchRequest,
    Selector,
)

__all__ = [
    "ByteSpan",
    "ReadOutcome",
    "ReadRequest",
    "SearchMatch",
    "SearchOutcome",
    "SearchRequest",
    "Selector",
]


@dataclass(frozen=True)
class ReadOutcome:
    """
    클래스 이름: ReadOutcome
    기능: 읽기 결과. span이 있으면 content는 원본의 정확한 그 구간이다. io는 계측용이며 응답에 넣지 않는다.
    작성 날짜: 2026/11/10
    """

    record: SourceRecord
    content: str
    span: ByteSpan | None
    truncated: bool
    next_cursor: str | None
    token_count: int
    count_mode: str
    io: IoStats = field(default_factory=IoStats)
    # 4.9: PDF 페이지 읽기면 페이지 번호. span은 그 페이지 추출 텍스트 안 구간이다.
    pdf_page: int | None = None


@dataclass(frozen=True)
class SearchOutcome:
    """
    클래스 이름: SearchOutcome
    기능: 검색 결과와 이어 읽기 cursor.
    작성 날짜: 2026/11/10
    """

    record: SourceRecord
    matches: list[SearchMatch]
    truncated: bool
    next_cursor: str | None
    token_count: int
    count_mode: str
    io: IoStats = field(default_factory=IoStats)
