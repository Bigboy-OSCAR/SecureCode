"""RuntimeStore 실디스크 통합 테스트.

작성일: 2026-11-06
"""

import concurrent.futures

from securecode_context.pointers.models.runtime import RuntimePut
from securecode_context.pointers.runtime.store import RuntimeStore


def _pid(descriptor):
    return descriptor.pointer.split("/")[-1].split("?")[0]


def test_restart_recovery(tmp_path):
    root = tmp_path / ".securecode" / "runtime"
    first = RuntimeStore(root)
    d = first.put(RuntimePut("ws-1", "session-1", "text/plain", b"persistent data"))
    pointer_id = _pid(d)
    first.close()
    second = RuntimeStore(root)
    result = second.read("ws-1", "session-1", pointer_id)
    assert result.content == "persistent data"
    second.close()


def test_concurrent_puts(tmp_path):
    store = RuntimeStore(tmp_path / ".securecode" / "runtime")

    def save(index):
        return store.put(
            RuntimePut("ws-1", "session-1", "text/plain", f"value-{index}".encode())
        ).pointer

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        pointers = list(pool.map(save, range(50)))
    assert len(pointers) == 50
    assert store.list("ws-1", "session-1", limit=100)["has_more"] is False
    store.close()


def test_many_pointers_and_session_clear(tmp_path):
    store = RuntimeStore(tmp_path / ".securecode" / "runtime")
    request = RuntimePut("ws-1", "session-1", "text/plain", b"x")
    for _ in range(10_001):
        store.put(request)
    assert store.list("ws-1", "session-1", limit=1)["has_more"] is True
    assert store.clear_session("ws-1", "session-1") == 10_001
    assert store.list("ws-1", "session-1")["pointers"] == []
    store.close()
