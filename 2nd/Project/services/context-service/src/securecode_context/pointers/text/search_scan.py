"""리터럴 검색의 제한된 순차 scan. 버퍼는 64 KiB 청크 + 앞 문맥뿐이며 요청마다 scan 바이트·시간 상한이 있다."""

import time
from dataclasses import dataclass

from securecode_context.pointers.text.caps import decode_prefix
from securecode_context.pointers.text.io_meter import CHUNK_BYTES, MeteredFile
from securecode_context.pointers.text.models import ByteSpan, SearchMatch

SCAN_LIMIT_BYTES = 8 * 1024 * 1024
SCAN_LIMIT_SECONDS = 2.0
CONTEXT_BEFORE = 120
CONTEXT_AFTER = 240


@dataclass(frozen=True)
class ScanResult:
    """
    클래스 이름: ScanResult
    기능: 찾은 일치와, 더 볼 원문이 남았을 때 다음 scan 시작 위치·그 줄 번호.
    작성 날짜: 2026/11/10
    """

    matches: list[SearchMatch]
    resume: tuple[int, int] | None


def _align_start(buffer: bytes, index: int) -> int:
    """
    함수 이름: _align_start()
    기능: UTF-8 연속 바이트를 건너 문자 시작으로 옮긴다.
    인자: buffer -> 버퍼, index -> 위치
    반환값: 문자 시작 위치
    작성 날짜: 2026/11/10
    """
    while index < len(buffer) and buffer[index] & 0xC0 == 0x80:
        index += 1
    return index


def _align_end(buffer: bytes, index: int) -> int:
    """
    함수 이름: _align_end()
    기능: 끝 위치가 문자 중간이면 그 문자 시작으로 당긴다.
    인자: buffer -> 버퍼, index -> 반열린 끝 위치
    반환값: 문자 경계 위치
    작성 날짜: 2026/11/10
    """
    while 0 < index < len(buffer) and buffer[index] & 0xC0 == 0x80:
        index -= 1
    return index


def _snippet(buffer: bytes, base: int, hit: int, length: int) -> tuple[str, ByteSpan]:
    """
    함수 이름: _snippet()
    기능: 일치를 포함하고 같은 줄 안에 머무는 짧은 원본 구간을 만든다(줄바꿈 제외).
    인자: buffer -> 버퍼, base -> 버퍼 시작의 원본 위치, hit -> 버퍼 안 일치 위치, length -> 일치 길이
    반환값: 미리보기와 원본 구간
    작성 날짜: 2026/11/10
    """
    line_start = buffer.rfind(b"\n", 0, hit) + 1
    line_end = buffer.find(b"\n", hit + length)
    line_end = len(buffer) if line_end == -1 else line_end
    start = _align_start(buffer, max(line_start, hit - CONTEXT_BEFORE))
    end = _align_end(buffer, min(line_end, hit + length + CONTEXT_AFTER))
    if end > start and buffer[end - 1 : end] == b"\r":
        end -= 1
    # The buffer may end mid-character at a chunk edge; keep only complete characters.
    text, used = decode_prefix(buffer[start:end], False, base + start)
    return text, ByteSpan(base + start, base + start + used)


def scan(file: MeteredFile, start: int, line: int, patterns: list[bytes], limit: int) -> ScanResult:
    """
    함수 이름: scan()
    기능: start부터 일치를 찾는다. limit개, scan 상한, 시간 상한 중 먼저 닿는 곳에서 멈추고 이어갈 위치를 준다.
    인자: file -> 계측 핸들, start/line -> 시작 위치와 그 줄 번호, patterns -> UTF-8 검색어들,
        limit -> 최대 일치 수
    반환값: ScanResult
    작성 날짜: 2026/11/10
    """
    keep = max(max(len(pattern) for pattern in patterns) - 1, CONTEXT_BEFORE)
    deadline = time.monotonic() + SCAN_LIMIT_SECONDS
    buffer, base, base_line, reported = b"", start, line, start
    scanned = 0
    matches: list[SearchMatch] = []
    file.seek(start)
    while True:
        chunk = file.read(CHUNK_BYTES)
        scanned += len(chunk)
        buffer += chunk
        safe = len(buffer) if not chunk else len(buffer) - (max(map(len, patterns)) - 1)
        hits = sorted(
            {
                (index, len(pattern))
                for pattern in patterns
                for index in _find_all(buffer, pattern, reported - base, safe)
            }
        )
        for hit, length in hits:
            if len(matches) == limit:
                return ScanResult(matches, (base + hit, base_line + buffer.count(b"\n", 0, hit)))
            text, span = _snippet(buffer, base, hit, length)
            line_no = base_line + buffer.count(b"\n", 0, hit)
            matches.append(SearchMatch(line_no, base + hit, text, span))
        reported = max(reported, base + safe)
        if not chunk:
            return ScanResult(matches, None)
        if scanned >= SCAN_LIMIT_BYTES or time.monotonic() > deadline:
            return ScanResult(
                matches, (reported, base_line + buffer.count(b"\n", 0, reported - base))
            )
        cut = max(0, len(buffer) - keep)
        base_line += buffer.count(b"\n", 0, cut)
        base += cut
        buffer = buffer[cut:]


def _find_all(buffer: bytes, pattern: bytes, start: int, stop: int) -> list[int]:
    """
    함수 이름: _find_all()
    기능: start 이상 stop 미만에서 시작하는 일치 위치를 모두 찾는다(겹치는 일치 포함).
    인자: buffer -> 버퍼, pattern -> 검색어, start/stop -> 시작 위치 범위
    반환값: 위치 목록
    작성 날짜: 2026/11/10
    """
    found: list[int] = []
    index = buffer.find(pattern, max(0, start))
    while index != -1 and index < stop:
        found.append(index)
        index = buffer.find(pattern, index + 1)
    return found
