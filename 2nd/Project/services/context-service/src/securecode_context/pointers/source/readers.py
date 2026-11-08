MAX_BOUNDED_LINES = 1000
MAX_BOUNDED_BYTES = 16384
"""Source Pointer Bounded Reader.

작성일: 2026-11-07
"""

import json
from typing import Any, Dict, Optional
from securecode_context.pointers.source.index import LineIndexer
from securecode_context.pointers.source.registry import SourceRegistry


class BoundedSourceReader:
    """seek 기반 Bounded I/O Reader."""

    def __init__(self, registry: SourceRegistry):
        self.registry = registry

    def read_range(self, pointer: str, start_line: Optional[int] = None, end_line: Optional[int] = None, max_bytes: int = 16384) -> Dict[str, Any]:
        desc = self.registry.stat(pointer)
        real_p = desc.real_path

        indexer = LineIndexer(real_p)
        total_lines = len(indexer.line_offsets) - 1

        s_line = start_line or 1
        e_line = end_line or total_lines
        if s_line > e_line or s_line < 1 or e_line > total_lines:
            raise ValueError(f"INVALID_SELECTOR: Line range [{s_line}, {e_line}] invalid")

        start_bytes, _ = indexer.get_line_bounds(s_line)
        _, end_bytes = indexer.get_line_bounds(e_line)
        target_len = min(end_bytes - start_bytes, max_bytes)

        with open(real_p, "rb") as f:
            f.seek(start_bytes)
            content_bytes = f.read(target_len)
            bytes_read = len(content_bytes)

        self.registry.stat(pointer)
        content_text = content_bytes.decode("utf-8", errors="replace")
        truncated = (end_bytes - start_bytes) > max_bytes

        return {
            "content": content_text,
            "pointer": pointer,
            "revision": desc.revision,
            "truncated": truncated,
            "bytes_read": bytes_read,
            "start_line": s_line,
            "end_line": e_line
        }

    def read_json_path(self, pointer: str, json_path: str) -> Dict[str, Any]:
        desc = self.registry.stat(pointer)
        if desc.byte_size > 8 * 1024 * 1024:
            raise ValueError("EXCEEDED: JSON file exceeds 8 MiB limit")

        with open(desc.real_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.registry.stat(pointer)
        return {"pointer": pointer, "json_path": json_path, "data": data}
