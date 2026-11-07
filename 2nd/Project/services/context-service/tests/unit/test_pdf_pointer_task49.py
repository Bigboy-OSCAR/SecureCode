"""Task 4.9 PDF 파싱 및 Source Pointer 연동 단위 테스트.

작성일: 2026-11-07
"""

import os
import tempfile
import pytest
from securecode_context.pdf.cache import PdfCacheManager
from securecode_context.pdf.tools import PdfToolService
from securecode_context.pointers.source.models import SourceRegistrationRequest
from securecode_context.pointers.source.registry import SourceRegistry


def create_minimal_pdf(file_path: str) -> None:
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer << /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
    )
    with open(file_path, "wb") as f:
        f.write(pdf_content)


def test_pdf_parsing_and_bounded_read():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        pdf_path = os.path.join(ws_root, "sample.pdf")

        create_minimal_pdf(pdf_path)

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=pdf_path))

        cache = PdfCacheManager()
        svc = PdfToolService(reg, cache)

        job_res = svc.parse_job(desc.pointer)
        assert job_res["status"] == "COMPLETED"
        assert job_res["total_pages"] >= 1

        read_res = svc.read_pages(desc.pointer, start_page=1, end_page=1)
        assert read_res["start_page"] == 1
        assert len(read_res["pages"]) == 1


def test_pdf_invalid_page_range():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        pdf_path = os.path.join(ws_root, "sample.pdf")

        create_minimal_pdf(pdf_path)

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=pdf_path))

        cache = PdfCacheManager()
        svc = PdfToolService(reg, cache)

        with pytest.raises(ValueError, match="INVALID_SELECTOR"):
            svc.read_pages(desc.pointer, start_page=1, end_page=100)
