"""Source file reader implementation with bounded line and memory limits."""

import os
import json
from typing import Any, Dict, Optional

MAX_LINE_BYTES = 65536      # 64 KB per line limit
MAX_TOTAL_BYTES = 1048576   # 1 MB total read limit

class BoundedSourceReader:
    """Bounded line and byte reader for workspace source files."""

    def __init__(self, registry: Any = None):
        self.registry = registry

    def read_range(self, pointer: str, start_line: int = 1, end_line: int = 100, max_bytes: int = MAX_TOTAL_BYTES) -> Dict[str, Any]:
        """
        D3, D5 fix: Bounded read with pointer verification & change check.
        """
        if not self.registry:
            raise ValueError("Registry not configured")

        desc = self.registry.stat(pointer)
        file_path = desc.real_path

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
                    total_bytes_read += len(chunk)

                    if total_bytes_read > max_bytes:
                        break

                    lines.append(chunk.decode("utf-8", errors="replace").rstrip("\r\n"))
                current_line += 1

        content = "\n".join(lines)

        return {
            "pointer": pointer,
            "lines": lines,
            "content": content,
            "bytes_read": total_bytes_read,
            "truncated": total_bytes_read >= max_bytes
        }

    def read_json_path(self, file_path: str, json_path: Optional[str] = None) -> Any:
        """
        D4 fix: Query JSON content by path instead of returning entire 500KB file.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not json_path or json_path == "$":
            return data

        keys = [k for k in json_path.strip("$. ").split(".") if k]
        curr = data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return None
        return curr

SourceReader = BoundedSourceReader
