"""4.3 RuntimeStore 실디스크 통합: 재시작, 동시 저장, 여러 인스턴스 용량 원자성, 10,001개 발급, 재시작 복구."""

import concurrent.futures
import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import pytest

from securecode_context.pointers.models.runtime import PointerNotFound, QuotaExceeded, RuntimePut
from securecode_context.pointers.runtime import store as store_module
from securecode_context.pointers.runtime.db import utc_now
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.text.models import ReadRequest
from support.helpers import FixedTokenCounter

WS, SES = "ws-1", "ses-1"


def _pid(pointer: str) -> str:
    """
    함수 이름: _pid()
    기능: 포인터 URI에서 ID를 꺼낸다.
    인자: pointer -> URI
    반환값: UUID
    작성 날짜: 2026/11/10
    """
    return pointer.rsplit("/", 1)[-1].split("?")[0]


def _db(root: Path) -> sqlite3.Connection:
    """
    함수 이름: _db()
    기능: 시험에서 저장소 DB를 직접 연다(상태 주입·확인용).
    인자: root -> 저장소 폴더
    반환값: SQLite 연결
    작성 날짜: 2026/11/10
    """
    return sqlite3.connect(root / "runtime.sqlite3", isolation_level=None)


def test_restart_keeps_data_and_reads(tmp_path: Path) -> None:
    """
    함수 이름: test_restart_keeps_data_and_reads()
    기능: 닫고 다시 연 저장소에서 같은 출력을 checksum 검증 후 읽는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "runtime"
    first = RuntimeStore(root)
    pointer = first.put(RuntimePut(WS, SES, "text/plain", "지속 데이터\n".encode())).pointer
    first.close()
    second = RuntimeStore(root)
    try:
        outcome = RuntimeReader(second, FixedTokenCounter()).read(WS, SES, ReadRequest(pointer))
        assert outcome.content == "지속 데이터\n"
        assert second.last_recovery.lost_rows == 0
    finally:
        second.close()


def test_concurrent_puts_in_one_store(tmp_path: Path) -> None:
    """
    함수 이름: test_concurrent_puts_in_one_store()
    기능: 8개 스레드의 50회 동시 저장이 모두 고유 ID로 남는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store = RuntimeStore(tmp_path / "runtime")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pointers = list(
                pool.map(
                    lambda index: (
                        store.put(
                            RuntimePut(WS, SES, "text/plain", f"value-{index}".encode())
                        ).pointer
                    ),
                    range(50),
                )
            )
        assert len(set(pointers)) == 50
        assert len(store.list_pointers(WS, SES, limit=100)["items"]) == 50
    finally:
        store.close()


def test_session_quota_is_atomic_across_store_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_session_quota_is_atomic_across_store_instances()
    기능: 같은 DB를 쓰는 두 저장소가 동시에 저장해도 세션 합계가 한도를 넘지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 세션 한도 축소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    monkeypatch.setattr(store_module, "MAX_SESSION_BYTES", 10_000)
    root = tmp_path / "runtime"
    stores = [RuntimeStore(root), RuntimeStore(root)]

    def save(index: int) -> str:
        """
        함수 이름: save()
        기능: 번갈아 다른 인스턴스로 1,000바이트를 저장한다.
        인자: index -> 순번
        반환값: ok 또는 quota
        작성 날짜: 2026/11/10
        """
        try:
            stores[index % 2].put(RuntimePut(WS, SES, "text/plain", b"x" * 1000))
        except QuotaExceeded:
            return "quota"
        return "ok"

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(save, range(30)))
        with _db(root) as connection:
            used = connection.execute(
                "SELECT SUM(byte_size), COUNT(*) FROM runtime_pointers WHERE state = 'ready'"
            ).fetchone()
        assert results.count("ok") == 10 and results.count("quota") == 20
        assert used == (10_000, 10)
        assert len(list(stores[0].blobs.rglob("*.blob"))) == 10
    finally:
        for store in stores:
            store.close()


def test_ten_thousand_and_one_objects(tmp_path: Path) -> None:
    """
    함수 이름: test_ten_thousand_and_one_objects()
    기능: 10,001개를 발급해 표본 조회·전체 목록 순회·세션 정리가 정확한지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store = RuntimeStore(tmp_path / "runtime")
    try:
        pointers = [
            store.put(RuntimePut(WS, SES, "text/plain", f"{index}".encode())).pointer
            for index in range(10_001)
        ]
        assert len(set(pointers)) == 10_001
        for index in (0, 5_000, 10_000):
            assert store.stat(WS, SES, _pid(pointers[index])).preview == str(index)
        listed = 0
        cursor = None
        while True:
            page = store.list_pointers(WS, SES, limit=100, cursor=cursor)
            listed += len(page["items"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        assert listed == 10_001
        assert store.clear_session(WS, SES) == 10_001
        assert store.list_pointers(WS, SES)["items"] == []
        assert list(store.blobs.rglob("*.blob")) == []
    finally:
        store.close()


def test_recovery_after_crash_and_lost_blob(tmp_path: Path) -> None:
    """
    함수 이름: test_recovery_after_crash_and_lost_blob()
    기능: 중단된 저장 예약·고아 blob·사라진 blob 행을 재시작 때 정리하고 정상 출력은 남기는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "runtime"
    store = RuntimeStore(root)
    kept = store.put(RuntimePut(WS, SES, "text/plain", b"kept")).pointer
    lost = store.put(RuntimePut(WS, SES, "text/plain", b"lost")).pointer
    crashed = store.open_writer(RuntimePut(WS, SES, "text/plain", b""))
    crashed.write(b"half written")
    temp = crashed.blob.temp
    crashed.blob._stream.close()  # simulate a process that died mid-write (handle released)
    store.close()
    old = (utc_now() - timedelta(hours=2)).isoformat()
    with _db(root) as connection:
        connection.execute(
            "UPDATE runtime_pointers SET created_at = ? WHERE state = 'pending'", (old,)
        )
    next(path for path in root.rglob("*.blob") if path.stem == _pid(lost)).unlink()
    orphan = temp.parent / "00000000-0000-4000-8000-000000000000.blob"
    orphan.write_bytes(b"no row")
    stale = time.time() - 3600
    os.utime(orphan, (stale, stale))
    reopened = RuntimeStore(root)
    try:
        report = reopened.last_recovery
        assert (report.stale_pending, report.lost_rows, report.orphan_files) == (1, 1, 1)
        assert not temp.exists() and not orphan.exists()
        assert reopened.stat(WS, SES, _pid(kept)).preview == "kept"
        with pytest.raises(PointerNotFound) as missing:
            reopened.stat(WS, SES, _pid(lost))
        assert missing.value.reason == "lost"
    finally:
        reopened.close()


def test_db_failure_at_commit_leaves_no_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_db_failure_at_commit_leaves_no_orphan()
    기능: blob을 확정한 뒤 DB 완료 기록이 실패하면 blob과 예약 행을 모두 지우는지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> DB 오류 주입
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store = RuntimeStore(tmp_path / "runtime")
    real = store_module.transaction
    calls = 0

    def failing_second(connection: sqlite3.Connection) -> object:
        """
        함수 이름: failing_second()
        기능: 두 번째 트랜잭션(완료 기록)에서 DB 오류를 낸다.
        인자: connection -> 연결
        반환값: 실제 트랜잭션 컨텍스트
        작성 날짜: 2026/11/10
        """
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real(connection)

    monkeypatch.setattr(store_module, "transaction", failing_second)
    try:
        with pytest.raises(sqlite3.OperationalError):
            store.put(RuntimePut(WS, SES, "text/plain", b"never visible"))
        monkeypatch.setattr(store_module, "transaction", real)
        assert list(store.blobs.rglob("*")) == [] or all(p.is_dir() for p in store.blobs.rglob("*"))
        with _db(store.root) as connection:
            assert connection.execute("SELECT COUNT(*) FROM runtime_pointers").fetchone() == (0,)
    finally:
        store.close()
