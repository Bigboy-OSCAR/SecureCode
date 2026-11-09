"""PDF document parsing module with strict page isolation & mock fallback support."""

import re
import os
import hashlib
from typing import List, Dict, Any, Union

class PdfParser:
    """PDF content parser enforcing strict page boundaries."""

    def parse_pdf(self, file_input: Union[str, bytes]) -> Dict[str, Any]:
        if isinstance(file_input, str):
            if not os.path.exists(file_input):
                raise FileNotFoundError(f"PDF file not found: {file_input}")
            with open(file_input, "rb") as f:
                content_bytes = f.read()
        else:
            content_bytes = file_input

        if not content_bytes or len(content_bytes) < 8:
            raise ValueError("EMPTY_OR_INVALID_PDF")

        if not content_bytes.startswith(b"%PDF"):
            raise ValueError("INVALID_PDF_HEADER")

        if b"/Encrypt" in content_bytes:
            raise ValueError("ENCRYPTED_PDF_NOT_SUPPORTED")

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

        # /Page 객체 매칭 위치 파악
        page_matches = list(re.finditer(rb'/Type\s*/Page\b', content_bytes))
        total_pages = len(page_matches)

        if total_pages == 0:
            return []

        pages_data = []
        for idx in range(total_pages):
            page_num = idx + 1
            if target_pages and page_num not in target_pages:
                continue

            start_pos = page_matches[idx].start()
            end_pos = page_matches[idx + 1].start() if idx + 1 < total_pages else len(content_bytes)
            page_chunk = content_bytes[start_pos:end_pos]

            # BT...ET 텍스트 블록 파싱
            text_blocks = re.findall(rb'BT[\s\S]*?ET', page_chunk)
            extracted_text = ""
            for block in text_blocks:
                matches = re.findall(rb'\((.*?)\)', block)
                for m in matches:
                    try:
                        extracted_text += m.decode('utf-8', errors='ignore') + " "
                    except Exception:
                        pass

            pages_data.append({
                "page_num": page_num,
                "text": extracted_text.strip()
            })

        return pages_data

    def extract_text(self, content_bytes: bytes, start_page: int = 1, end_page: int = None) -> str:
        target = list(range(start_page, (end_page or start_page) + 1))
        pages = self.parse_pages(content_bytes, target_pages=target)
        return "\n".join([p["text"] for p in pages if p["text"]])
