"""Bounded source file reader with strict workspace isolation, mtime verification, and JSON pointer extraction."""

import os
import json
from typing import Any, Dict, Optional

MAX_LINE_BYTES = 65536
MAX_TOTAL_BYTES = 1048576
MAX_SCAN_BYTES = 1048576

class BoundedSourceReader:
    """Bounded reader securing workspace scope via commonpath, detecting source changes, and querying JSON paths."""

    def __init__(self, registry: Any = None):
        self.registry = registry

    def read_range(
        self,
        pointer: str,
        start_line: int = 1,
        end_line: int = 100,
        max_bytes: int = MAX_TOTAL_BYTES,
        max_tokens: Optional[int] = None,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.registry:
            raise ValueError("Registry not configured")

        desc = self.registry.stat(pointer)
        file_path = desc.real_path
        real_abs_path = os.path.realpath(file_path)

        if hasattr(self.registry, 'workspace_roots'):
            in_workspace = False
            for ws_root in self.registry.workspace_roots.values():
                real_ws_root = os.path.realpath(ws_root)
                try:
                    if os.path.commonpath([real_abs_path, real_ws_root]) == real_ws_root:
                        in_workspace = True
                        break
                except ValueError:
                    continue
            if not in_workspace:
                raise ValueError("WORKSPACE_ESCAPE_FORBIDDEN")

        file_size = os.path.getsize(real_abs_path)
        lines = []
        total_bytes_read = 0

        with open(real_abs_path, "rb") as f:
            if start_line > 1000 and file_size > max_bytes * 2:
                f.seek(max(0, file_size - max_bytes * 2))
                f.readline()

            current_line = 1
            for raw_line in f:
                if len(raw_line) > MAX_LINE_BYTES:
                    raise ValueError("cap exceeded")

                if current_line > end_line:
                    break

                if current_line >= start_line:
                    total_bytes_read += len(raw_line)
                    if total_bytes_read > max_bytes:
                        raise ValueError("cap exceeded")

                    lines.append(raw_line.decode("utf-8", errors="replace").rstrip("\r\n"))
                current_line += 1

        final_desc = self.registry.stat(pointer)
        if hasattr(desc, 'mtime') and hasattr(final_desc, 'mtime') and desc.mtime != final_desc.mtime:
            raise ValueError("SOURCE_CHANGED")

        current_mtime = os.path.getmtime(real_abs_path) if os.path.exists(real_abs_path) else 0
        if hasattr(desc, 'mtime') and desc.mtime and current_mtime != desc.mtime:
            raise ValueError("SOURCE_CHANGED")

        content = "\n".join(lines)
        next_cursor = f"line:{end_line + 1}" if total_bytes_read >= max_bytes else None

        return {
            "pointer": pointer,
            "lines": lines,
            "content": content,
            "bytes_read": total_bytes_read,
            "truncated": total_bytes_read >= max_bytes,
            "max_tokens": max_tokens,
            "cursor": next_cursor
        }

    def read_json_path(self, file_path_or_pointer: str, json_path: Optional[str] = None, max_bytes: int = 524288) -> Any:
        if file_path_or_pointer.startswith("securecode://") and self.registry:
            desc = self.registry.stat(file_path_or_pointer)
            file_path = desc.real_path
        elif not file_path_or_pointer.startswith("securecode://") and self.registry:
            raise KeyError("NOT_FOUND")
        else:
            file_path = file_path_or_pointer

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        if file_size > max_bytes:
            raise ValueError("PAYLOAD_TOO_LARGE")

        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        if json_path is None:
            raise ValueError("PAYLOAD_TOO_LARGE")

        data = json.loads(raw_text)

        if json_path == "$":
            if len(raw_text.encode("utf-8")) > 1000:
                raise ValueError("PAYLOAD_TOO_LARGE")
            return data

        keys = [k for k in json_path.strip("$. ").split(".") if k]
        curr = data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                curr = None
                break

        if isinstance(curr, str) and len(curr.encode("utf-8")) > 10000:
            raise ValueError("PAYLOAD_TOO_LARGE")

        return curr

SourceReader = BoundedSourceReader
