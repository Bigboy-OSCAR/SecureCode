"""Runtime blob bounded 검색.

작성일: 2026-11-06
"""

from typing import Any


def search_blob(
    content: bytes, pattern: str, max_matches: int = 100, max_scan_bytes: int = 1_048_576
) -> dict[str, Any]:
    text = content[:max_scan_bytes].decode("utf-8", errors="replace")
    matches: list[dict[str, Any]] = []
    position = 0
    while len(matches) < max_matches:
        found = text.find(pattern, position)
        if found == -1:
            break
        line = text.count("\n", 0, found) + 1
        line_start = text.rfind("\n", 0, found) + 1
        line_end = text.find("\n", found)
        if line_end == -1:
            line_end = len(text)
        matches.append(
            {
                "line": line,
                "column": found - line_start + 1,
                "line_text": text[line_start:line_end][:512],
            }
        )
        position = found + len(pattern)
    truncated = text.find(pattern, position) != -1
    return {
        "matches": matches,
        "match_count": len(matches),
        "truncated": truncated,
        "next_cursor": str(position) if truncated else None,
    }
