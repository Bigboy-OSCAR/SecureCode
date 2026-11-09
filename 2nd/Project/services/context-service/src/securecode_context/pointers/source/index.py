"""Source Pointer Line Offset Indexer.

작성일: 2026-11-07
"""

import os


class LineIndexer:
    """클래스 이름: LineIndexer
    기능: 파일의 줄 시작 바이트 위치를 색인한다.
    작성 날짜: 2026/11/09
    """

    def __init__(self, file_path: str) -> None:
        """함수 이름: __init__()
        기능: 저장소 경로와 workspace 허용 root를 설정한다.
        인자: file_path
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.file_path = file_path
        self.line_offsets: list[int] = []
        self._build_index()

    def _build_index(self) -> None:
        """함수 이름: _build_index()
        기능: 청크에서 개행 위치를 수집한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.line_offsets = [0]
        with open(self.file_path, "rb") as f:
            while chunk := f.read(65536):
                start = 0
                while (idx := chunk.find(b"\n", start)) != -1:
                    self.line_offsets.append(f.tell() - len(chunk) + idx + 1)
                    start = idx + 1

    def get_line_bounds(self, line_number: int) -> tuple[int, int]:
        """함수 이름: get_line_bounds()
        기능: 1부터 시작하는 줄 번호의 바이트 범위를 계산한다.
        인자: line_number
        반환값: 시작 위치와 배타적인 끝 위치
        작성 날짜: 2026/11/09
        """
        if line_number < 1 or line_number > len(self.line_offsets):
            raise IndexError(f"INVALID_SELECTOR: Line number {line_number} out of range")
        start = self.line_offsets[line_number - 1]
        if line_number < len(self.line_offsets):
            end = self.line_offsets[line_number]
        else:
            end = os.path.getsize(self.file_path)
        return start, end
