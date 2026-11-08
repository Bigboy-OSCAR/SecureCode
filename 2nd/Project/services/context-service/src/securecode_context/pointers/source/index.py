"""Source Pointer Line Offset Indexer.

작성일: 2026-11-07
"""

import os
from typing import List, Tuple


class LineIndexer:
    """파일의 줄 시작 바이트 오프셋 인덱스 생성 및 관리."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.line_offsets: List[int] = []
        self._build_index()

    def _build_index(self) -> None:
        self.line_offsets = [0]
        with open(self.file_path, "rb") as f:
            while chunk := f.read(65536):
                start = 0
                while (idx := chunk.find(b"\n", start)) != -1:
                    self.line_offsets.append(f.tell() - len(chunk) + idx + 1)
                    start = idx + 1

    def get_line_bounds(self, line_number: int) -> Tuple[int, int]:
        """1-indexed 줄 번호에 대한 (start_offset, end_offset) 반환."""
        if line_number < 1 or line_number >= len(self.line_offsets):
            raise IndexError(f"INVALID_SELECTOR: Line number {line_number} out of range")
        start = self.line_offsets[line_number - 1]
        if line_number < len(self.line_offsets) - 1:
            end = self.line_offsets[line_number]
        else:
            end = os.path.getsize(self.file_path)
        return start, end
