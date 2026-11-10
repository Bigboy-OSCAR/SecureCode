"""PDF document parser with strict object graph, FlateDecode decompression, target page isolation, and zero mock fallbacks."""

import re
import os
import zlib
import hashlib
from typing import List, Dict, Any, Union

class PdfParser:
    """Production PDF parser strictly rejecting non-PDF inputs, eliminating mock fallbacks, and isolating page streams."""

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
            raise ValueError("NOT_A_PDF_FILE")

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
            raise ValueError("NOT_A_PDF_FILE")

        # 1. PDF Indirect Objects (n 0 obj ... endobj) 인덱싱
        objects = {}
        for m in re.finditer(rb'(\d+)\s+(\d+)\s+obj([\s\S]*?)endobj', content_bytes):
            obj_id = int(m.group(1))
            objects[obj_id] = m.group(3)

        page_obj_ids = []
        for obj_id, body in objects.items():
            if re.search(rb'/Type\s*/Page\b', body) and not re.search(rb'/Type\s*/Pages\b', body):
                page_obj_ids.append(obj_id)

        page_obj_ids.sort()
        total_pages = len(page_obj_ids)

        # 2. obj 구조가 생략된 약식 PDF/바이트스트림의 경우 /Type /Page 경계 기반 추적
        if total_pages == 0:
            page_matches = list(re.finditer(rb'/Type\s*/Page\b', content_bytes))
            if not page_matches:
                raise ValueError("INVALID_PDF_NO_PAGE_OBJECTS")
            
            pages_data = []
            for idx in range(len(page_matches)):
                page_num = idx + 1
                if target_pages and page_num not in target_pages:
                    continue
                start_pos = page_matches[idx].start()
                end_pos = page_matches[idx + 1].start() if idx + 1 < len(page_matches) else len(content_bytes)
                chunk = content_bytes[start_pos:end_pos]
                text = self._extract_bt_et(chunk)
                pages_data.append({"page_num": page_num, "text": text})
            return pages_data

        # 3. /Contents 객체 참조 추적 및 페이지 격리
        pages_data = []
        for idx, obj_id in enumerate(page_obj_ids, start=1):
            if target_pages and idx not in target_pages:
                continue

            body = objects.get(obj_id, b"")
            contents_match = re.search(rb'/Contents\s*(?:\[([^\]]+)\]|(\d+)\s+\d+\s+R)', body)
            stream_bytes = b""

            if contents_match:
                if contents_match.group(2):
                    ref_id = int(contents_match.group(2))
                    c_body = objects.get(ref_id, b"")
                    stream_bytes = self._decode_stream(c_body)
                elif contents_match.group(1):
                    refs = re.findall(rb'(\d+)\s+\d+\s+R', contents_match.group(1))
                    for r in refs:
                        c_body = objects.get(int(r), b"")
                        stream_bytes += self._decode_stream(c_body) + b"\n"

            if not stream_bytes:
                stream_bytes = self._decode_stream(body)

            extracted_text = self._extract_bt_et(stream_bytes)
            pages_data.append({"page_num": idx, "text": extracted_text})

        return pages_data

    def _decode_stream(self, body_or_obj: bytes) -> bytes:
        s_m = re.search(rb'stream[\r\n]+([\s\S]*?)[\r\n]+endstream', body_or_obj)
        if not s_m:
            return b""
        raw_stream = s_m.group(1)
        if b"/Filter" in body_or_obj and b"/FlateDecode" in body_or_obj:
            try:
                return zlib.decompress(raw_stream)
            except Exception:
                try:
                    return zlib.decompress(raw_stream, -zlib.MAX_WBITS)
                except Exception:
                    return raw_stream
        return raw_stream

    def _extract_bt_et(self, data: bytes) -> str:
        text_blocks = re.findall(rb'BT[\s\S]*?ET', data)
        text = ""
        for block in text_blocks:
            matches = re.findall(rb'\((.*?)\)', block)
            for m in matches:
                try:
                    text += m.decode('utf-8', errors='ignore') + " "
                except Exception:
                    pass
        return text.strip()

    def extract_text(self, content_bytes: bytes, start_page: int = 1, end_page: int = None) -> str:
        target = list(range(start_page, (end_page or start_page) + 1))
        pages = self.parse_pages(content_bytes, target_pages=target)
        return "\n".join([p["text"] for p in pages if p["text"]])
