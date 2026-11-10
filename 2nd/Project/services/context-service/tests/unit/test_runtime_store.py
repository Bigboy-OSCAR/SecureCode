"""4.3 RuntimeStore 저장·수명주기.

저장·descriptor·preview, 범위·origin·UTF-8·TTL 검사, 용량, 삭제·만료·세션 정리 상태, 디스크 오류 정리를 검사한다.
"""

import errno
import os
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from securecode_context.pointers.models.runtime import (
    NotStorable,
    PointerExpired,
    PointerNotFound,
    QuotaExceeded,
    RuntimeDescriptor,
    RuntimePut,
    ScopeForbidden,
    StorageUnavailable,
)
from securecode_context.pointers.runtime import blob
from securecode_context.pointers.runtime import store as store_module
from securecode_context.pointers.runtime.db import utc_now
from securecode_context.pointers.runtime.store import RuntimeStore

WS, SES = "ws-1", "ses-1"


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    """
    함수 이름: store()
    기능: 임시 폴더의 실디스크 저장소를 만든다.
    인자: tmp_path -> 임시 폴더
    반환값: RuntimeStore
    작성 날짜: 2026/11/10
    """
    instance = RuntimeStore(tmp_path / "runtime")
    yield instance  # type: ignore[misc]
    instance.close()


def _put(
    store: RuntimeStore, text: str, session: str = SES, **options: object
) -> RuntimeDescriptor:
    """
    함수 이름: _put()
    기능: 텍스트 하나를 저장한다.
    인자: store -> 저장소, text -> 본문, session -> 세션, options -> RuntimePut 추가 값
    반환값: RuntimeDescriptor
    작성 날짜: 2026/11/10
    """
    return store.put(RuntimePut(WS, session, "text/plain", text.encode(), **options))  # type: ignore[arg-type]


def _pid(descriptor: RuntimeDescriptor) -> str:
    """
    함수 이름: _pid()
    기능: 포인터 URI에서 ID를 꺼낸다.
    인자: descriptor -> descriptor
    반환값: UUID
    작성 날짜: 2026/11/10
    """
    return descriptor.pointer.rsplit("/", 1)[-1].split("?")[0]


def _files(store: RuntimeStore) -> list[Path]:
    """
    함수 이름: _files()
    기능: blob 폴더의 모든 파일(임시 포함)을 나열한다.
    인자: store -> 저장소
    반환값: 파일 목록
    작성 날짜: 2026/11/10
    """
    return [path for path in store.blobs.rglob("*") if path.is_file()]


def test_descriptor_preview_and_provenance(store: RuntimeStore) -> None:
    """
    함수 이름: test_descriptor_preview_and_provenance()
    기능: UUID URI, 크기, checksum, 512바이트 이하 한글 경계 preview, origin이 기록되는지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    text = "가" * 400
    descriptor = _put(store, text, origin="run_command", truncated_before_storage=True)
    data = descriptor.to_dict()
    assert data["pointer"] == f"securecode://runtime/{WS}/{SES}/{_pid(descriptor)}?v=1"
    assert data["byte_size"] == 1200 and len(descriptor.checksum) == 64
    assert len(data["preview"].encode()) <= 512 and data["preview"] == "가" * 170
    assert data["provenance"]["origin"] == "run_command"
    assert data["provenance"]["truncated_before_storage"] is True
    assert data["available_operations"] == ["read", "search"]


def test_scope_origin_utf8_and_ttl_checks(store: RuntimeStore) -> None:
    """
    함수 이름: test_scope_origin_utf8_and_ttl_checks()
    기능: 경로가 되는 범위, 제한된 읽기 출력의 재저장, 잘못된 UTF-8, 잘못된 TTL을 저장 전에 거부하는지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    with pytest.raises(ScopeForbidden):
        store.put(RuntimePut("..", SES, "text/plain", b"x"))
    with pytest.raises(NotStorable) as bounded:
        _put(store, "x", origin="runtime_read")
    assert bounded.value.reason == "bounded_read"
    with pytest.raises(NotStorable):
        store.put(RuntimePut(WS, SES, "text/plain", b"ok \xff bad"))
    with pytest.raises(Exception) as ttl:
        _put(store, "x", ttl_seconds=0)
    assert getattr(ttl.value, "reason", None) == "invalid_ttl"
    assert _files(store) == []
    assert store.list_pointers(WS, SES)["items"] == []


def test_object_and_session_quota_return_errors(
    store: RuntimeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_object_and_session_quota_return_errors()
    기능: 객체·세션 한도 초과는 기존 출력을 지우지 않고 QUOTA_EXCEEDED이며 남은 파일이 없는지 확인한다.
    인자: store -> 저장소, monkeypatch -> 한도 축소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    monkeypatch.setattr(blob, "MAX_OBJECT_BYTES", 100)
    monkeypatch.setattr(store_module, "MAX_SESSION_BYTES", 150)
    with pytest.raises(QuotaExceeded) as too_big:
        _put(store, "x" * 101)
    assert too_big.value.reason == "object_limit"
    first = _put(store, "a" * 100)
    with pytest.raises(QuotaExceeded) as session_full:
        _put(store, "b" * 60)
    assert session_full.value.reason == "session_limit"
    assert store.stat(WS, SES, _pid(first)).byte_size == 100
    assert _put(store, "c" * 50, session="ses-2").byte_size == 50
    assert len(_files(store)) == 2


def test_delete_is_idempotent_and_reports_deleted(store: RuntimeStore) -> None:
    """
    함수 이름: test_delete_is_idempotent_and_reports_deleted()
    기능: 삭제를 두 번 해도 같은 결과이고, 이후 조회는 원문 대신 NOT_FOUND(deleted)인지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    descriptor = _put(store, "remove me")
    other = _put(store, "keep me")
    store.delete(WS, SES, _pid(descriptor))
    store.delete(WS, SES, _pid(descriptor))
    with pytest.raises(PointerNotFound) as deleted:
        store.stat(WS, SES, _pid(descriptor))
    assert deleted.value.reason == "deleted"
    assert store.stat(WS, SES, _pid(other)).preview == "keep me"
    store.delete(WS, "ses-other", _pid(other))
    assert store.stat(WS, SES, _pid(other)).byte_size == 7


def test_expiry_before_and_after_sweep(store: RuntimeStore) -> None:
    """
    함수 이름: test_expiry_before_and_after_sweep()
    기능: 만료 출력은 sweep 전후 모두 EXPIRED이고, sweep은 세션 정리와 별개로 blob을 지우는지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    descriptor = _put(store, "short lived", ttl_seconds=1)
    live = _put(store, "still here")
    past = (utc_now() - timedelta(seconds=5)).isoformat()
    with sqlite3.connect(store.root / "runtime.sqlite3") as connection:
        connection.execute(
            "UPDATE runtime_pointers SET expires_at = ? WHERE pointer_id = ?",
            (past, _pid(descriptor)),
        )
    with pytest.raises(PointerExpired):
        store.stat(WS, SES, _pid(descriptor))
    assert store.sweep_expired() == 1
    with pytest.raises(PointerExpired):
        store.stat(WS, SES, _pid(descriptor))
    assert [path.stem for path in _files(store)] == [_pid(live)]


def test_clear_session_only_touches_that_session(store: RuntimeStore) -> None:
    """
    함수 이름: test_clear_session_only_touches_that_session()
    기능: 세션 정리가 그 세션 출력만 지우고 이후 조회가 NOT_FOUND(session_cleared)인지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    gone = _put(store, "a")
    _put(store, "b")
    kept = _put(store, "c", session="ses-2")
    assert store.clear_session(WS, SES) == 2
    with pytest.raises(PointerNotFound) as cleared:
        store.stat(WS, SES, _pid(gone))
    assert cleared.value.reason == "session_cleared"
    assert store.stat(WS, "ses-2", _pid(kept)).preview == "c"
    assert store.clear_session(WS, SES) == 0


def test_list_pages_and_body_cap(store: RuntimeStore) -> None:
    """
    함수 이름: test_list_pages_and_body_cap()
    기능: 목록이 limit·cursor로 이어지고, 긴 preview가 많으면 64 KiB에서 끊고 표시하는지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    for index in range(150):
        _put(store, f"{index:03}" + "가" * 300)
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = store.list_pointers(WS, SES, limit=100, cursor=cursor)
        pages += 1
        seen += [item["pointer"] for item in page["items"]]
        assert sum(len(item["preview"].encode()) + 512 for item in page["items"]) <= 64 * 1024
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 150 and pages > 2
    first = store.list_pointers(WS, SES, limit=100)
    assert first["truncated_by_bytes"] is True


def test_writer_abort_and_cancel_leave_nothing(store: RuntimeStore) -> None:
    """
    함수 이름: test_writer_abort_and_cancel_leave_nothing()
    기능: 스트리밍 저장을 취소하거나 예외로 중단하면 임시 파일·예약 행이 남지 않는지 확인한다.
    인자: store -> 저장소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    writer = store.open_writer(RuntimePut(WS, SES, "text/plain", b""))
    writer.write(b"partial output")
    writer.abort()
    writer.abort()
    with (
        pytest.raises(RuntimeError),
        store.open_writer(RuntimePut(WS, SES, "text/plain", b"")) as w,
    ):
        w.write(b"started")
        raise RuntimeError("tool cancelled")
    streamed = store.open_writer(RuntimePut(WS, SES, "text/plain", b""))
    for part in (b"line 1\n", "줄 2\n".encode(), b"line 3"):
        streamed.write(part)
    descriptor = streamed.commit()
    assert descriptor.byte_size == len("line 1\n줄 2\nline 3".encode())
    assert [path.name for path in _files(store)] == [f"{_pid(descriptor)}.blob"]
    with sqlite3.connect(store.root / "runtime.sqlite3") as connection:
        states = connection.execute("SELECT state FROM runtime_pointers").fetchall()
    assert states == [("ready",)]


@pytest.mark.parametrize(
    ("number", "expected"), [(errno.ENOSPC, QuotaExceeded), (errno.EIO, StorageUnavailable)]
)
def test_disk_errors_are_explicit_and_cleaned(
    store: RuntimeStore, monkeypatch: pytest.MonkeyPatch, number: int, expected: type[Exception]
) -> None:
    """
    함수 이름: test_disk_errors_are_explicit_and_cleaned()
    기능: rename 단계 디스크 오류를 공간 부족/그 외로 구분해 알리고 임시 파일·예약을 남기지 않는지 확인한다.
    인자: store -> 저장소, monkeypatch -> 오류 주입, number/expected -> errno와 기대 오류
    반환값: 없음
    작성 날짜: 2026/11/10
    """

    def failing_replace(*_args: object) -> None:
        """
        함수 이름: failing_replace()
        기능: 디스크 오류를 낸다.
        인자: _args -> 무시
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        raise OSError(number, os.strerror(number))

    monkeypatch.setattr(blob.os, "replace", failing_replace)
    with pytest.raises(expected):
        _put(store, "will fail")
    monkeypatch.undo()
    assert _files(store) == []
    assert store.list_pointers(WS, SES)["items"] == []
    assert _put(store, "works again").byte_size == 11
