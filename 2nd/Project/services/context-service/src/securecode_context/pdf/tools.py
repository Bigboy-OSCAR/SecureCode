"""PDF Source Pointer 연동 Bounded Read Tool.

작성일: 2026-11-07
"""

from typing import Any, Dict, List
from securecode_context.pdf.cache import PdfCacheManager
from securecode_context.pdf.parser import PdfParser
from securecode_context.pointers.source.registry import SourceRegistry


class PdfToolService:
    """PDF Bounded Read 및 상태 서비스 인터페이스."""

    def __init__(self, registry: SourceRegistry, cache: PdfCacheManager):
        self.registry = registry
        self.cache = cache
        self.parser = PdfParser()

    def parse_job(self, pointer: str) -> Dict[str, Any]:
        desc = self.registry.stat(pointer)
        cached = self.cache.get(pointer)
        if cached and cached["file_hash"] == desc.revision:
            return {
                "pointer": pointer,
                "status": "COMPLETED",
                "total_pages": cached["total_pages"],
                "revision": desc.revision
            }

        parsed = self.parser.parse_pdf(desc.real_path)
        self.cache.put(pointer, parsed["file_hash"], parsed["total_pages"], parsed["pages_text"])
        return {
            "pointer": pointer,
            "status": "COMPLETED",
            "total_pages": parsed["total_pages"],
            "revision": parsed["file_hash"]
        }

    def read_pages(self, pointer: str, start_page: int, end_page: int) -> Dict[str, Any]:
        desc = self.registry.stat(pointer)
        cached = self.cache.get(pointer)
        if not cached or cached["file_hash"] != desc.revision:
            self.parse_job(pointer)
            cached = self.cache.get(pointer)

        total_pages = cached["total_pages"]
        if start_page < 1 or end_page > total_pages or start_page > end_page:
            raise ValueError(f"INVALID_SELECTOR: Page range [{start_page}, {end_page}] out of bounds (1-{total_pages})")

        selected_pages: List[Dict[str, Any]] = []
        for p_num in range(start_page, end_page + 1):
            selected_pages.append({
                "page_number": p_num,
                "content": cached["pages_text"][p_num - 1]
            })

        return {
            "pointer": pointer,
            "revision": desc.revision,
            "start_page": start_page,
            "end_page": end_page,
            "pages": selected_pages
        }
