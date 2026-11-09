"""PDF document parsing module with strict page isolation."""

import re
import os
import hashlib
from typing import List, Dict, Any, Union

class PdfParser:
    """PDF content parser enforcing strict page boundaries."""

    def parse_pdf(self, file_input: Union[str, bytes]) -> Dict[str, Any]:
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
        if not content_bytes or not content_bytes.startswith(b"%PDF"):
            return []

        # /Page 객체 인덱스 기반 분할
        raw_pages = re.split(rb'/Type\s*/Page\b|/Page\b', content_bytes)
        if len(raw_pages) <= 1:
            raw_pages = [content_bytes]
        else:
            raw_pages = raw_pages[1:]

        total_pages = len(raw_pages)
        pages_data = []

        for idx, page_content in enumerate(raw_pages, start=1):
            if target_pages and idx not in target_pages:
                continue

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
                "page_num": idx,
                "text": extracted_text.strip()
            })

        return pages_data

    def extract_text(self, content_bytes: bytes, start_page: int = 1, end_page: int = None) -> str:
        target = list(range(start_page, (end_page or start_page) + 1))
        pages = self.parse_pages(content_bytes, target_pages=target)
        return "\n".join([p["text"] for p in pages if p["text"]])
