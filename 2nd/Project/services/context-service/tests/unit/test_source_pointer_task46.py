"""Task 4.6 Bounded I/O 및 검색 단위 테스트.

작성일: 2026-11-07
"""

import os
import tempfile
import pytest
from securecode_context.pointers.source.models import SourceRegistrationRequest
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.source.readers import BoundedSourceReader
from securecode_context.pointers.source.search import BoundedSourceSearcher


def test_bounded_line_reading_and_bytes_count():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        test_file = os.path.join(ws_root, "large.txt")

        with open(test_file, "w", encoding="utf-8") as f:
            for i in range(1, 1001):
                f.write("Line " + str(i) + ": test sample line text\n")

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=test_file))

        reader = BoundedSourceReader(reg)
        res = reader.read_range(desc.pointer, start_line=10, end_line=20, max_bytes=1024)

        assert "Line 10:" in res["content"]
        assert "Line 20:" in res["content"]
        assert res["bytes_read"] <= 1024

def test_source_search_and_korean_support():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        test_file = os.path.join(ws_root, "code.py")

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def hello():\n    # 처리 함수\n    print('안녕')\n")

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=test_file))

        searcher = BoundedSourceSearcher(reg)
        res = searcher.search(desc.pointer, query="처리")

        assert len(res["matches"]) == 1
        assert res["matches"][0]["line_number"] == 2

def test_source_read_modified_during_read_fails():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        test_file = os.path.join(ws_root, "data.txt")

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("v1 data\n")

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=test_file))

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("v2 modified data\n")

        reader = BoundedSourceReader(reg)
        with pytest.raises(ValueError, match="SOURCE_CHANGED"):
            reader.read_range(desc.pointer, start_line=1, end_line=1)
