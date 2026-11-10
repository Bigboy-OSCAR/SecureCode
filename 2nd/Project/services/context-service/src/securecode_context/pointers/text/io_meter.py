"""원본 파일 읽기를 고정 크기 청크로 제한하고 실제 읽은 바이트·최대 버퍼를 계측한다."""

from dataclasses import dataclass
from typing import Protocol

CHUNK_BYTES = 64 * 1024


class SeekableReader(Protocol):
    """
    클래스 이름: SeekableReader
    기능: 원본 파일 핸들 또는 checksum을 확인하는 Runtime blob 읽기 객체의 공통 모양.
    작성 날짜: 2026/11/10
    """

    def read(self, size: int = -1, /) -> bytes:
        """
        함수 이름: read()
        기능: 현재 위치에서 최대 size 바이트를 읽는다.
        인자: size -> 최대 바이트
        반환값: 읽은 바이트
        작성 날짜: 2026/11/10
        """
        ...

    def seek(self, offset: int, whence: int = 0, /) -> int:
        """
        함수 이름: seek()
        기능: 위치를 옮긴다.
        인자: offset -> 위치, whence -> 기준
        반환값: 새 위치
        작성 날짜: 2026/11/10
        """
        ...


@dataclass
class IoStats:
    """
    클래스 이름: IoStats
    기능: 한 요청에서 원본에서 읽은 총 바이트, 한 번에 요청한 최대 크기, seek 횟수.
    작성 날짜: 2026/11/10
    """

    bytes_read: int = 0
    max_chunk: int = 0
    seeks: int = 0


class MeteredFile:
    """
    클래스 이름: MeteredFile
    기능: 열린 원본을 감싸 모든 read를 CHUNK_BYTES 이하로 나누고 계측한다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, file: SeekableReader, stats: IoStats) -> None:
        """
        함수 이름: __init__()
        기능: 원본 핸들과 계측 대상을 보관한다.
        인자: file -> 검증된 원본 핸들, stats -> 누적할 계측값
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._file = file
        self.stats = stats

    def seek(self, offset: int) -> None:
        """
        함수 이름: seek()
        기능: 절대 위치로 이동한다.
        인자: offset -> 0부터 시작하는 바이트 위치
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._file.seek(offset)
        self.stats.seeks += 1

    def read(self, size: int) -> bytes:
        """
        함수 이름: read()
        기능: 최대 size 바이트를 CHUNK_BYTES 단위로 읽는다.
        인자: size -> 읽을 최대 바이트
        반환값: 읽은 바이트(파일 끝이면 더 짧다)
        작성 날짜: 2026/11/10
        """
        parts: list[bytes] = []
        remaining = size
        while remaining > 0:
            request = min(remaining, CHUNK_BYTES)
            chunk = self._file.read(request)
            self.stats.max_chunk = max(self.stats.max_chunk, request)
            self.stats.bytes_read += len(chunk)
            if not chunk:
                break
            parts.append(chunk)
            remaining -= len(chunk)
        return b"".join(parts)

    def read_range(self, start: int, end: int) -> bytes:
        """
        함수 이름: read_range()
        기능: [start, end) 구간만 seek 후 읽는다.
        인자: start/end -> 반열린 바이트 구간
        반환값: 구간 바이트
        작성 날짜: 2026/11/10
        """
        self.seek(start)
        return self.read(max(0, end - start))
