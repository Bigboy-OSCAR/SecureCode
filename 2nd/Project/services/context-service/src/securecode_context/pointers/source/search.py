"""Source Pointer Bounded Searcher.

작성일: 2026-11-07
"""

from typing import Any, Dict, List
from securecode_context.pointers.source.registry import SourceRegistry


class BoundedSourceSearcher:
    """Streaming pattern searcher."""

    def __init__(self, registry: SourceRegistry):
        self.registry = registry

    def search(self, pointer: str, query: str, max_matches: int = 50) -> Dict[str, Any]:
        desc = self.registry.stat(pointer)
        matches: List[Dict[str, Any]] = []

        line_num = 1
        with open(desc.real_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if query in line:
                    matches.append({
                        "line_number": line_num,
                        "content": line.strip()
                    })
                    if len(matches) >= max_matches:
                        break
                line_num += 1

        self.registry.stat(pointer)
        return {
            "pointer": pointer,
            "query": query,
            "matches": matches,
            "total_matches": len(matches),
            "truncated": len(matches) >= max_matches
        }
