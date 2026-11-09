"""Bounded source file reader with line & byte memory limits."""

import json
from typing import Any

from securecode_context.pointers.source.registry import SourceRegistry

MAX_LINE_BYTES = 65_536
MAX_TOTAL_BYTES = 16_384
MAX_SCAN_BYTES = 1_048_576
MAX_JSON_BYTES = 8 * 1_048_576


class BoundedSourceReader:
    """클래스 이름: BoundedSourceReader
    기능: 등록된 파일을 제한된 메모리로 읽고 조회 전후 revision을 확인한다.
    작성 날짜: 2026/11/09
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        """함수 이름: __init__()
        기능: 조회 권한과 revision을 검증할 등록부를 보관한다.
        인자: registry -> Source 등록부
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.registry = registry

    def read_range(self, pointer: str, start_line: int = 1, end_line: int = 100, max_bytes: int = MAX_TOTAL_BYTES) -> Dict[str, Any]:
        if not self.registry:
            raise ValueError("Registry not configured")

        desc = self.registry.stat(pointer)
        file_path = desc.real_path

        real_abs_path = os.path.realpath(file_path)
        if hasattr(self.registry, 'workspace_roots'):
            in_workspace = False
            for ws_root in self.registry.workspace_roots.values():
                real_ws_root = os.path.realpath(ws_root)
                if real_abs_path.startswith(real_ws_root):
                    in_workspace = True
                    break
            if not in_workspace:
                raise ValueError("WORKSPACE_ESCAPE_FORBIDDEN")

        current_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        if hasattr(desc, 'mtime') and desc.mtime and current_mtime != desc.mtime:
            raise ValueError("SOURCE_CHANGED")

        lines = []
        total_bytes_read = 0

        with open(file_path, "rb") as f:
            current_line = 1
            for raw_line in f:
                if current_line > end_line:
                    break
                if current_line >= start_line:
                    chunk = raw_line[:MAX_LINE_BYTES]
                    if total_bytes_read + len(chunk) > max_bytes:
                        allowed = max_bytes - total_bytes_read
                        if allowed > 0:
                            lines.append(chunk[:allowed].decode("utf-8", errors="replace"))
                            total_bytes_read += allowed
                        break

                    total_bytes_read += len(chunk)
                    lines.append(chunk.decode("utf-8", errors="replace").rstrip("\r\n"))
                current_line += 1

        content = "\n".join(lines)

        return {
            "pointer": pointer,
            "lines": lines,
            "content": "\n".join(lines),
            "bytes_read": scanned,
            "truncated": truncated,
        }

    def read_json_path(self, file_path: str, json_path: Optional[str] = None, max_bytes: int = 524288) -> Any:
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        if file_size > max_bytes:
            raise ValueError("JSON_EXCEEDS_MAX_BYTES")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)


SourceReader = BoundedSourceReader
