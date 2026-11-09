"""PDF document parsing module with strict /Contents stream resolution."""

import re
import os
import hashlib
from typing import List, Dict, Any, Union

class PdfParser:
    """PDF content parser enforcing strict object graph and /Contents stream resolution."""

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

        # Encrypted PDF check
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

        # 객체 블록 파싱 (obj ... endobj)
        objects = {}
        for m in re.finditer(rb'(\d+)\s+(\d+)\s+obj([\s\S]*?)endobj', content_bytes):
            obj_id = int(m.group(1))
            objects[obj_id] = m.group(3)

        # /Type /Page 찾기
        page_obj_ids = []
        for obj_id, body in objects.items():
            if re.search(rb'/Type\s*/Page\b', body) and not re.search(rb'/Type\s*/Pages\b', body):
                page_obj_ids.append(obj_id)

        page_obj_ids.sort()
        total_pages = len(page_obj_ids)
        if total_pages == 0:
            return []

        pages_data = []
        for idx, obj_id in enumerate(page_obj_ids, start=1):
            if target_pages and idx not in target_pages:
                continue

            body = objects.get(obj_id, b"")
            extracted_text = ""

            # /Contents 객체 레퍼런스 추적
            contents_match = re.search(rb'/Contents\s*(?:\[([^\]]+)\]|(\d+)\s+\d+\s+R)', body)
            stream_bytes = b""

            if contents_match:
                if contents_match.group(2):
                    ref_id = int(contents_match.group(2))
                    c_body = objects.get(ref_id, b"")
                    s_m = re.search(rb'stream[\r\n]+([\s\S]*?)[\r\n]+endstream', c_body)
                    if s_m:
                        stream_bytes = s_m.group(1)
                elif contents_match.group(1):
                    refs = re.findall(rb'(\d+)\s+\d+\s+R', contents_match.group(1))
                    for r in refs:
                        c_body = objects.get(int(r), b"")
                        s_m = re.search(rb'stream[\r\n]+([\s\S]*?)[\r\n]+endstream', c_body)
                        if s_m:
                            stream_bytes += s_m.group(1) + b"\n"

            if not stream_bytes:
                stream_bytes = body

            # BT...ET 텍스트 블록 추출
            text_blocks = re.findall(rb'BT[\s\S]*?ET', stream_bytes)
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
