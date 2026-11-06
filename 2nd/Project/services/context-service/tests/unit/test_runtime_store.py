"""RuntimeStore 단위 테스트.

작성일: 2026-11-06
"""

from pathlib import Path

import pytest

from securecode_context.pointers.models.runtime import (
    PointerNotFound,
    QuotaExceeded,
    RuntimePut,
    ScopeForbidden,
)
from securecode_context.pointers.runtime.store import MAX_OBJECT_BYTES, RuntimeStore


@pytest.fixture()
def store(tmp_path: Path):
    s = RuntimeStore(tmp_path / ".securecode" / "runtime")
    yield s
    s.close()


def _pid(descriptor):
    return descriptor.pointer.split("/")[-1].split("?")[0]


def test_put_and_read_roundtrip(store):
    d = store.put(RuntimePut("ws-1", "session-1", "text/plain", "한글\n둘째줄".encode()))
    result = store.read("ws-1", "session-1", _pid(d))
    assert result.content == "한글\n둘째줄"
    assert result.truncated is False


def test_scope_isolation(store):
    d = store.put(RuntimePut("ws-1", "session-1", "text/plain", b"secret"))
    with pytest.raises(PointerNotFound):
        store.read("ws-1", "session-2", _pid(d))


def test_invalid_scope(store):
    with pytest.raises(ScopeForbidden):
        store.put(RuntimePut("", "session-1", "text/plain", b"x"))


def test_object_quota(store):
    with pytest.raises(QuotaExceeded):
        store.put(RuntimePut("ws-1", "session-1", "text/plain", b"x" * (MAX_OBJECT_BYTES + 1)))


def test_idempotent_delete(store):
    d = store.put(RuntimePut("ws-1", "session-1", "text/plain", b"data"))
    store.delete("ws-1", "session-1", _pid(d))
    store.delete("ws-1", "session-1", _pid(d))


def test_search_returns_line_sources(store):
    d = store.put(RuntimePut("ws-1", "session-1", "text/plain", b"first\nneedle here\nthird"))
    result = store.search("ws-1", "session-1", _pid(d), "needle")
    assert result["match_count"] == 1
    assert result["matches"][0]["line"] == 2
