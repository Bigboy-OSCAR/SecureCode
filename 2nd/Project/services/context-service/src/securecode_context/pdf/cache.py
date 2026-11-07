"""PDF Parsed Text Cache Manager.

작성일: 2026-11-07
"""

from typing import Any, Dict, Optional


class PdfCacheManager:
    """페이지별 파싱 텍스트 캐시 저장소."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def put(self, pointer: str, file_hash: str, total_pages: int, pages_text: list) -> None:
        self._cache[pointer] = {
            "file_hash": file_hash,
            "total_pages": total_pages,
            "pages_text": pages_text
        }

    def get(self, pointer: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(pointer)

    def remove(self, pointer: str) -> bool:
        if pointer in self._cache:
            del self._cache[pointer]
            return True
        return False
