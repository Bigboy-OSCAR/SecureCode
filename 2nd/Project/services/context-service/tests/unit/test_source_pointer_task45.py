"""Task 4.5 Source Pointer 단위 및 영속성 회귀 시험.

작성일: 2026-11-07
"""

import os
import tempfile
import pytest
from securecode_context.pointers.source.models import SourceRegistrationRequest
from securecode_context.pointers.source.registry import SourceRegistry


def test_source_register_stat_and_unregister():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        db_file = os.path.join(tmp_dir, "registry.db")

        test_file = os.path.join(ws_root, "test.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Hello SecureCode Source Pointer!")

        reg = SourceRegistry(db_path=db_file, workspace_roots={"ws_1": ws_root})
        req = SourceRegistrationRequest(workspace_id="ws_1", target_path=test_file)

        desc = reg.register(req)
        assert desc.pointer.startswith("securecode://source/ws_1/")
        assert desc.byte_size == len("Hello SecureCode Source Pointer!")

        # Stat 확인
        stat_desc = reg.stat(desc.pointer)
        assert stat_desc.revision == desc.revision

        # DB 재시작 복구 시험
        reg2 = SourceRegistry(db_path=db_file, workspace_roots={"ws_1": ws_root})
        stat_desc2 = reg2.stat(desc.pointer)
        assert stat_desc2.pointer == desc.pointer

        # Unregister 시험
        unreg_ok = reg2.unregister(desc.pointer)
        assert unreg_ok is True
        # 원본 파일은 유지되어야 함
        assert os.path.exists(test_file) is True


def test_source_path_traversal_forbidden():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        outside_file = os.path.join(tmp_dir, "secret.txt")
        os.makedirs(ws_root, exist_ok=True)
        with open(outside_file, "w") as f:
            f.write("secret")

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        req = SourceRegistrationRequest(workspace_id="ws_1", target_path=outside_file, allow_external=False)

        with pytest.raises(ValueError, match="FORBIDDEN"):
            reg.register(req)


def test_source_changed_detection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = os.path.join(tmp_dir, "workspace")
        os.makedirs(ws_root, exist_ok=True)
        test_file = os.path.join(ws_root, "data.txt")
        with open(test_file, "w") as f:
            f.write("v1")

        reg = SourceRegistry(db_path=":memory:", workspace_roots={"ws_1": ws_root})
        desc = reg.register(SourceRegistrationRequest(workspace_id="ws_1", target_path=test_file))

        # 파일 내용 변경
        with open(test_file, "w") as f:
            f.write("v2_modified")

        with pytest.raises(ValueError, match="SOURCE_CHANGED"):
            reg.stat(desc.pointer)
