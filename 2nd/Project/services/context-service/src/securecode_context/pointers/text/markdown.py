"""Markdown ATX 제목 색인과 section 범위. 최초 생성은 순차 scan이며 줄마다 앞 512바이트만 본다."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.text.io_meter import CHUNK_BYTES, MeteredFile
from securecode_context.pointers.text.models import ByteSpan

HEAD_BYTES = 512
MAX_HEADINGS = 10_000
_ATX = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class Heading:
    """
    클래스 이름: Heading
    기능: 제목 수준, 표시 텍스트, 제목 줄 시작 바이트.
    작성 날짜: 2026/11/10
    """

    level: int
    text: str
    offset: int


def _line_heads(file: MeteredFile) -> Iterator[tuple[int, bytes]]:
    """
    함수 이름: _line_heads()
    기능: 줄마다 (시작 위치, 앞 512바이트)를 만든다. 긴 줄 전체를 메모리에 두지 않는다.
    인자: file -> 계측 핸들
    반환값: (줄 시작, 줄 앞부분) 반복자
    작성 날짜: 2026/11/10
    """
    file.seek(0)
    position = 0
    start = 0
    head = b""
    while chunk := file.read(CHUNK_BYTES):
        cursor = 0
        while True:
            newline = chunk.find(b"\n", cursor)
            stop = len(chunk) if newline == -1 else newline
            if len(head) < HEAD_BYTES:
                head += chunk[cursor:stop][: HEAD_BYTES - len(head)]
            if newline == -1:
                break
            yield start, head
            head, start, cursor = b"", position + newline + 1, newline + 1
        position += len(chunk)
    if start < position:
        yield start, head


def build_headings(file: MeteredFile) -> tuple[Heading, ...]:
    """
    함수 이름: build_headings()
    기능: 코드 펜스 밖 ATX 제목(#~######)을 모은다. Setext 제목은 지원하지 않는다.
    인자: file -> 계측 핸들
    반환값: 제목 목록
    작성 날짜: 2026/11/10
    """
    headings: list[Heading] = []
    fence: str | None = None
    for offset, raw in _line_heads(file):
        text = raw.rstrip(b"\r").decode("utf-8", errors="replace")
        fence_match = _FENCE.match(text)
        if fence_match:
            marker = fence_match.group(1)[0]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is not None:
            continue
        match = _ATX.fullmatch(text)
        if match:
            headings.append(Heading(len(match.group(1)), (match.group(2) or "").strip(), offset))
            if len(headings) > MAX_HEADINGS:
                raise ServiceError(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    "제목이 너무 많아 section 조회를 할 수 없습니다. 줄 범위를 사용하세요.",
                    {"reason": "too_many_headings"},
                )
    return tuple(headings)


def section_span(headings: tuple[Heading, ...], name: str, byte_size: int) -> ByteSpan:
    """
    함수 이름: section_span()
    기능: 정확히 같은 제목 하나를 찾아 다음 같은/상위 수준 제목 직전까지를 범위로 정한다.
    인자: headings -> 제목 색인, name -> 대소문자 구분 제목, byte_size -> 원본 크기
    반환값: ByteSpan
    작성 날짜: 2026/11/10
    """
    found = [index for index, heading in enumerate(headings) if heading.text == name]
    if len(found) != 1:
        reason = "heading_not_found" if not found else "heading_ambiguous"
        raise ServiceError(
            ErrorCode.INVALID_SELECTOR, "section을 찾을 수 없습니다.", {"reason": reason}
        )
    target = headings[found[0]]
    end = byte_size
    for heading in headings[found[0] + 1 :]:
        if heading.level <= target.level:
            end = heading.offset
            break
    return ByteSpan(target.offset, end)
