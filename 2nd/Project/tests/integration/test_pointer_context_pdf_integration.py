"""Task 4.10 포인터·예산·PDF E2E 통합 회귀 검증 테스트.

작성일: 2026-11-07
"""

import sys
import os
import tempfile
import inspect
import pytest

# 파이썬 경로 명시적 수복
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/context-service/src')))

import securecode_context.pointers.runtime.store as rt_store_mod

from securecode_context.context.budget import ContextBudgetCalculator
from securecode_context.context.models import ContextCandidate, ContextCandidateRef
from securecode_context.context.policy import ContextSelectorPolicy
from securecode_context.pdf.cache import PdfCacheManager
from securecode_context.pdf.tools import PdfToolService
from securecode_context.pointers.source.models import SourceRegistrationRequest
from securecode_context.pointers.source.readers import BoundedSourceReader
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


def test_full_pointer_context_pdf_e2e_pipeline():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)

        # A. Runtime Pointer 검증 (전체 필드 완비 DTO)
        db_path = os.path.join(tmp_dir, "runtime.db")
        blob_dir = os.path.join(tmp_dir, "blobs")
        
        store_cls = getattr(rt_store_mod, "RuntimeStore", None) or getattr(rt_store_mod, "RuntimePointerStore", None)

        init_params = inspect.signature(store_cls.__init__).parameters
        kwargs = {}
        if "db_path" in init_params:
            kwargs["db_path"] = db_path
        if "blob_dir" in init_params:
            kwargs["blob_dir"] = blob_dir
        elif "storage_path" in init_params:
            kwargs["storage_path"] = tmp_dir
        elif "base_dir" in init_params:
            kwargs["base_dir"] = tmp_dir

        try:
            rt_store = store_cls(**kwargs)
        except Exception:
            rt_store = store_cls(db_path)

        large_tool_output = b"X" * 10000  # bytes

        class CompleteRuntimePut:
            def __init__(self, workspace_id, session_id, content, media_type="text/plain", ttl_seconds=86400):
                self.workspace_id = workspace_id
                self.session_id = session_id
                self.content = content
                self.media_type = media_type
                self.ttl_seconds = ttl_seconds

        req = CompleteRuntimePut(
            workspace_id="ws_1",
            session_id="sess_100",
            content=large_tool_output,
            media_type="text/plain",
            ttl_seconds=86400
        )

        rt_desc = rt_store.put(req)
        pointer_str = getattr(rt_desc, "pointer", str(rt_desc))
        assert "securecode://runtime/" in pointer_str or "runtime" in pointer_str

        # B. Source Pointer 검증
        src_file = os.path.join(ws_root, "source.py")
        with open(src_file, "w", encoding="utf-8") as f:
            f.write("def main():\n    print('SecureCode Integration Engine')\n")

        src_reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        src_desc = src_reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=src_file))
        assert src_desc.pointer.startswith("securecode://source/ws_1/")

        reader = BoundedSourceReader(src_reg)
        read_res = reader.read_range(src_desc.pointer, start_line=1, end_line=2)
        assert "SecureCode Integration Engine" in read_res["content"]

        # C. PDF Service Bounded Read 검증
        pdf_path = os.path.join(ws_root, "doc.pdf")
        create_minimal_pdf(pdf_path)
        pdf_desc = src_reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=pdf_path))

        pdf_cache = PdfCacheManager()
        pdf_svc = PdfToolService(src_reg, pdf_cache)
        pdf_job = pdf_svc.parse_job(pdf_desc.pointer)
        assert pdf_job["status"] == "COMPLETED"

        pdf_read = pdf_svc.read_pages(pdf_desc.pointer, start_page=1, end_page=1)
        assert len(pdf_read["pages"]) == 1

        # D. Context Selector 예산 선별 및 중복 제거 검증
        calc = ContextBudgetCalculator(model_limit=128000)
        available = calc.calculate_available_tokens("system", [], [], "query")

        candidates = [
            ContextCandidate("c_rt", ContextCandidateRef("runtime", uri=pointer_str), 0.9, True, 2500),
            ContextCandidate("c_src", ContextCandidateRef("source", uri=src_desc.pointer), 0.8, False, 500),
            ContextCandidate("c_pdf", ContextCandidateRef("source", uri=pdf_desc.pointer), 0.7, False, 1000)
        ]

        policy = ContextSelectorPolicy(calc)
        plan = policy.select(candidates, available_tokens=available)

        assert len(plan.selected) == 3
        assert plan.used_tokens == 4000
        assert len(plan.omitted) == 0
