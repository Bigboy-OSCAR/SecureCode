"""완료 항목 감사에서 발견한 경로·범위·변경 검증 회귀 시험."""

from pathlib import Path

import pytest

from securecode_context.common.errors import ServiceError
from securecode_context.pointers.models.runtime import InvalidSelector, RuntimePut, ScopeForbidden
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.text.models import ReadRequest
from support.helpers import FixedTokenCounter


@pytest.mark.parametrize("scope", ["..", "../escape", "/tmp/escape", "a/b", "a\\b"])
def test_runtime_rejects_path_scope(tmp_path: Path, scope: str) -> None:
    """함수 이름: test_runtime_rejects_path_scope()
    기능: scope가 저장 경로를 이탈시키지 못함을 검증한다.
    인자: tmp_path -> 임시 폴더, scope -> 위험한 식별자
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    store = RuntimeStore(tmp_path / "runtime")
    try:
        with pytest.raises(ScopeForbidden):
            store.put(RuntimePut(scope, "session", "text/plain", b"secret"))
        with pytest.raises(ScopeForbidden):
            store.clear_session("workspace", scope)
    finally:
        store.close()


def test_runtime_utf8_cursor_and_caps(tmp_path: Path) -> None:
    """함수 이름: test_runtime_utf8_cursor_and_caps()
    기능: 한글 경계가 잘린 작은 조회를 이어 붙여도 원문을 보존하고 상한을 강제한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    store = RuntimeStore(tmp_path / "runtime")
    reader = RuntimeReader(store, FixedTokenCounter())
    original = "한글abc한글"
    try:
        descriptor = store.put(RuntimePut("workspace", "session", "text/plain", original.encode()))
        result = ""
        cursor = None
        while True:
            part = reader.read(
                "workspace", "session", ReadRequest(descriptor.pointer, max_bytes=4, cursor=cursor)
            )
            result += part.content
            assert len(part.content.encode()) <= 4
            cursor = part.next_cursor
            if cursor is None:
                break
        assert result == original
        with pytest.raises(ServiceError):
            reader.read(
                "workspace", "session", ReadRequest(descriptor.pointer, max_bytes=1_000_000)
            )
        with pytest.raises(InvalidSelector):
            store.list_pointers("workspace", "session", limit=-1)
    finally:
        store.close()


# Source registry/read regressions from the 2026-11-09 review moved on 2026-11-10 to
# test_source_policy.py, test_source_reads.py, test_source_search.py and test_source_read_changes.py
# (4.5/4.6 rewrite: scoped resolve, seek index, caps and revision-bound cursors).
