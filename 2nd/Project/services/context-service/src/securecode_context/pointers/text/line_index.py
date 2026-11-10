"""줄 오프셋 색인. 최초 생성은 64 KiB 청크 순차 scan이고, 이후 줄 위치는 seek + 최대 64 KiB scan으로 찾는다.

색인은 64 KiB 청크마다 그 청크에서 처음 시작하는 줄의 (줄 번호, 바이트 위치)만 저장한다.
어떤 줄의 시작도 가장 가까운 앞 checkpoint에서 64 KiB 안에 있으므로 반복 조회가 파일 크기에 비례하지 않는다.
"""

import bisect
from dataclasses import dataclass

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.text.io_meter import CHUNK_BYTES, MeteredFile
from securecode_context.pointers.text.models import ByteSpan


def _invalid(reason: str) -> ServiceError:
    """
    함수 이름: _invalid()
    기능: 범위 오류를 만든다.
    인자: reason -> details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(ErrorCode.INVALID_SELECTOR, "범위가 올바르지 않습니다.", {"reason": reason})


@dataclass(frozen=True)
class LineIndex:
    """
    클래스 이름: LineIndex
    기능: 한 revision·identity의 줄 수와 청크별 줄 시작 checkpoint.
    작성 날짜: 2026/11/10
    """

    byte_size: int
    line_count: int
    ends_with_newline: bool
    lines: tuple[int, ...]
    offsets: tuple[int, ...]


def build_line_index(file: MeteredFile, byte_size: int) -> LineIndex:
    """
    함수 이름: build_line_index()
    기능: 파일을 한 번 순차로 읽어 줄 수와 checkpoint를 만든다(최초 1회, 메모리는 청크 1개).
    인자: file -> 계측 핸들, byte_size -> 등록 크기
    반환값: LineIndex
    작성 날짜: 2026/11/10
    """
    lines, offsets = [1], [0]
    newlines = 0
    position = 0
    previous_last = b"\n"
    file.seek(0)
    while chunk := file.read(CHUNK_BYTES):
        first = 0 if previous_last == b"\n" else chunk.find(b"\n") + 1
        checkpoint = position + first
        if position > 0 and (first > 0 or previous_last == b"\n") and checkpoint < byte_size:
            line_before = newlines + (1 if first > 0 and previous_last != b"\n" else 0)
            lines.append(line_before + 1)
            offsets.append(checkpoint)
        newlines += chunk.count(b"\n")
        position += len(chunk)
        previous_last = chunk[-1:]
    if position != byte_size:
        raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본 크기가 색인 도중 바뀌었습니다.")
    ends_with_newline = position > 0 and previous_last == b"\n"
    line_count = newlines + (0 if ends_with_newline or position == 0 else 1)
    return LineIndex(byte_size, line_count, ends_with_newline, tuple(lines), tuple(offsets))


def line_start(file: MeteredFile, index: LineIndex, line: int) -> int:
    """
    함수 이름: line_start()
    기능: 가장 가까운 checkpoint로 seek한 뒤 남은 개행만 세어 줄 시작 위치를 찾는다.
    인자: file -> 계측 핸들, index -> 줄 색인, line -> 1부터 시작하는 줄 번호
    반환값: 줄 시작 바이트 위치
    작성 날짜: 2026/11/10
    """
    if not 1 <= line <= index.line_count:
        raise _invalid("line_out_of_range")
    slot = bisect.bisect_right(index.lines, line) - 1
    need = line - index.lines[slot]
    position = index.offsets[slot]
    file.seek(position)
    while need > 0:
        chunk = file.read(CHUNK_BYTES)
        if not chunk:
            raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 색인과 다릅니다.")
        count = chunk.count(b"\n")
        if count < need:
            need -= count
            position += len(chunk)
            continue
        found = -1
        for _ in range(need):
            found = chunk.find(b"\n", found + 1)
        return position + found + 1
    return position


def line_span(file: MeteredFile, index: LineIndex, first: int, last: int) -> ByteSpan:
    """
    함수 이름: line_span()
    기능: first~last 줄(양끝 포함)의 바이트 구간을 계산한다. 마지막 줄의 줄바꿈(LF/CRLF)은 제외한다.
    인자: file -> 계측 핸들, index -> 줄 색인, first/last -> 줄 범위
    반환값: ByteSpan
    작성 날짜: 2026/11/10
    """
    if last < first:
        raise _invalid("end_before_start")
    if last > index.line_count:
        raise _invalid("line_out_of_range")
    start = line_start(file, index, first)
    if last < index.line_count:
        end = line_start(file, index, last + 1) - 1
    elif index.ends_with_newline:
        end = index.byte_size - 1
    else:
        end = index.byte_size
    if end > start and file.read_range(end - 1, end) == b"\r":
        end -= 1
    return ByteSpan(start, max(start, end))
