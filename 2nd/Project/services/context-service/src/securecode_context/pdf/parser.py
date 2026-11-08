"""PDF document parsing and text extraction module."""

import re
import os
import hashlib
from typing import List, Dict, Any, Union

class PdfParser:
    """PDF content parser supporting page-bound reading."""

    def parse_pdf(self, file_input: Union[str, bytes]) -> Dict[str, Any]:
        """Parse PDF file path or bytes into structured dictionary payload."""
        if isinstance(file_input, str):
            if not os.path.exists(file_input):
                return {"file_hash": "", "total_pages": 0, "pages_text": []}
            with open(file_input, "rb") as f:
                content_bytes = f.read()
        else:
            content_bytes = file_input

        file_hash = hashlib.sha256(content_bytes).hexdigest()
        pages = self.parse_pages(content_bytes)
        pages_text = [p["text"] for p in pages]

        return {
            "file_hash": file_hash,
            "total_pages": len(pages_text),
            "pages_text": pages_text
        }

    def parse_pages(self, content_bytes: bytes, target_pages: List[int] = None) -> List[Dict[str, Any]]:
        """
        Extract text page by page based on PDF /Page object streams.
        D1 fix: Only selected pages are extracted to prevent full text leak.
        D2 fix: No dummy text ('Sample PDF Page Text') is generated for empty pages.
        """
        if not content_bytes or not content_bytes.startswith(b"%PDF"):
            return []

        raw_pages = content_bytes.split(b"/Type /Page")
        if len(raw_pages) <= 1:
            raw_pages = content_bytes.split(b"/Page")

        pages_data = []
        total_pages = max(1, len(raw_pages) - 1)

        for page_idx in range(1, total_pages + 1):
            if target_pages and page_idx not in target_pages:
                continue

            page_content = raw_pages[page_idx] if page_idx < len(raw_pages) else b""
            text_blocks = re.findall(rb'BT[\s\S]*?ET', page_content)
            extracted_text = ""
            for block in text_blocks:
                matches = re.findall(rb'\((.*?)\)', block)
                for m in matches:
                    try:
                        extracted_text += m.decode('utf-8', errors='ignore') + " "
                    except Exception:
                        pass

            pages_data.append({
                "page_num": page_idx,
                "text": extracted_text.strip()
            })

        return pages_data

    def extract_text(self, content_bytes: bytes, start_page: int = 1, end_page: int = None) -> str:
        target = list(range(start_page, (end_page or start_page) + 1)) if end_page else [start_page]
        pages = self.parse_pages(content_bytes, target_pages=target)
        return "\n".join([p["text"] for p in pages if p["text"]])
