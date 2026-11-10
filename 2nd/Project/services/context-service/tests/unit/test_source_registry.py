"""4.5 Source 등록부 수명주기: 디스크 등록·목록·stat·revision·재시작·등록 해제·provenance."""

import hashlib
import os
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source import lifecycle
from securecode_context.pointers.source.models import SourceStatus
from support.source_fixtures import (
    WS_A,
    WS_B,
    code_of,
    make_workspaces,
    open_registry,
    workspace_file,
)


def test_register_list_stat_restart_unregister_keeps_original(tmp_path: Path) -> None:
    """
    함수 이름: test_register_list_stat_restart_unregister_keeps_original()
    기능: 디스크 등록부가 재시작 뒤에도 같은 등록을 돌려주고, 해제해도 원본은 남는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    original = roots.roots[WS_A] / "docs" / "설계.md"
    original.parent.mkdir()
    original.write_text("# 설계\n본문\n", encoding="utf-8")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("docs/설계.md")).items[0]
        assert record.pointer == f"securecode://source/{WS_A}/{record.source_id}?v=1"
        assert record.media_type == "text/markdown"
        assert record.byte_size == original.stat().st_size
        assert [item.pointer for item in registry.list_sources(WS_A).items] == [record.pointer]
    with open_registry(tmp_path, roots) as restarted:
        assert restarted.stat(WS_A, record.pointer).fingerprint == record.fingerprint
        restarted.unregister(WS_A, record.pointer)
        restarted.unregister(WS_A, record.pointer)
        with pytest.raises(ServiceError) as missing:
            restarted.stat(WS_A, record.pointer)
        assert code_of(missing) is ErrorCode.NOT_FOUND
        assert restarted.list_sources(WS_A).items == []
    assert original.read_text(encoding="utf-8") == "# 설계\n본문\n"


def test_duplicate_register_reuses_and_change_bumps_revision(tmp_path: Path) -> None:
    """
    함수 이름: test_duplicate_register_reuses_and_change_bumps_revision()
    기능: 같은 내용은 같은 포인터, 바뀐 내용은 changed 표시 후 refresh에서 새 revision임을 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    path = roots.roots[WS_A] / "a.txt"
    path.write_text("v1\n")
    with open_registry(tmp_path, roots) as registry:
        first = registry.register(WS_A, workspace_file("a.txt")).items[0]
        assert registry.register(WS_A, workspace_file("a.txt")).items[0].pointer == first.pointer
        path.write_text("v2 changed\n")
        with pytest.raises(ServiceError) as changed:
            registry.stat(WS_A, first.pointer)
        assert code_of(changed) is ErrorCode.SOURCE_CHANGED
        assert registry.list_sources(WS_A).items[0].status is SourceStatus.CHANGED
        refreshed = registry.refresh(WS_A, first.pointer)
        assert (refreshed.source_id, refreshed.revision) == (first.source_id, 2)
        assert registry.stat(WS_A, refreshed.pointer).revision == 2
        with pytest.raises(ServiceError) as stale:
            registry.stat(WS_A, first.pointer)
        assert code_of(stale) is ErrorCode.SOURCE_CHANGED
        assert stale.value.details["current_revision"] == 2


def test_metadata_only_change_keeps_revision_without_false_change(tmp_path: Path) -> None:
    """
    함수 이름: test_metadata_only_change_keeps_revision_without_false_change()
    기능: 수정 시각만 바뀌면 재해시 후 같은 revision으로 계속 쓸 수 있는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    path = roots.roots[WS_A] / "a.txt"
    path.write_text("same\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("a.txt")).items[0]
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        assert registry.stat(WS_A, record.pointer).revision == 1


def test_unchanged_stat_does_not_rehash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    함수 이름: test_unchanged_stat_does_not_rehash()
    기능: identity가 같으면 반복 stat이 전체 파일을 다시 해시하지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> hash 호출 감시
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / "big.log").write_bytes(b"line\n" * 100_000)
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("big.log")).items[0]

        def fail_hash(*_args: object) -> tuple[str, bytes]:
            """
            함수 이름: fail_hash()
            기능: 재해시가 일어나면 시험을 실패시킨다.
            인자: _args -> 무시
            반환값: 없음
            작성 날짜: 2026/11/10
            """
            raise AssertionError("unchanged stat must not rehash")

        monkeypatch.setattr(lifecycle, "hash_stable", fail_hash)
        for _ in range(3):
            assert registry.stat(WS_A, record.pointer).revision == 1


def test_deleted_original_is_missing_then_recoverable(tmp_path: Path) -> None:
    """
    함수 이름: test_deleted_original_is_missing_then_recoverable()
    기능: 원본 삭제는 NOT_FOUND(original_missing)·missing 상태이고, 같은 내용 복구 시 다시 ready인지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    path = roots.roots[WS_A] / "a.txt"
    path.write_text("keep\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("a.txt")).items[0]
        path.unlink()
        with pytest.raises(ServiceError) as missing:
            registry.stat(WS_A, record.pointer)
        assert (code_of(missing), missing.value.details["reason"]) == (
            ErrorCode.NOT_FOUND,
            "original_missing",
        )
        assert registry.list_sources(WS_A).items[0].status is SourceStatus.MISSING
        path.write_text("keep\n")
        assert registry.stat(WS_A, record.pointer).status is SourceStatus.READY


def test_workspace_scope_is_isolated(tmp_path: Path) -> None:
    """
    함수 이름: test_workspace_scope_is_isolated()
    기능: 다른 workspace가 포인터를 stat·refresh·해제할 수 없고 목록에도 보이지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / "a.txt").write_text("a\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("a.txt")).items[0]
        for action in (registry.stat, registry.refresh, registry.unregister, registry.resolve):
            with pytest.raises(ServiceError) as denied:
                action(WS_B, record.pointer)
            assert code_of(denied) is ErrorCode.FORBIDDEN
        assert registry.list_sources(WS_B).items == []
        forged = record.pointer.replace(WS_A, WS_B)
        with pytest.raises(ServiceError) as unknown:
            registry.stat(WS_B, forged)
        assert code_of(unknown) is ErrorCode.NOT_FOUND
        assert registry.stat(WS_A, record.pointer).revision == 1


def test_list_pages_with_scoped_cursor(tmp_path: Path) -> None:
    """
    함수 이름: test_list_pages_with_scoped_cursor()
    기능: 목록 cursor가 이어 읽기를 하고 다른 workspace에서는 거절되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    for index in range(3):
        (roots.roots[WS_A] / f"f{index}.txt").write_text(f"{index}\n")
    with open_registry(tmp_path, roots) as registry:
        for index in range(3):
            registry.register(WS_A, workspace_file(f"f{index}.txt"))
        first = registry.list_sources(WS_A, limit=2)
        assert len(first.items) == 2 and first.next_cursor is not None
        second = registry.list_sources(WS_A, limit=2, cursor=first.next_cursor)
        assert len(second.items) == 1 and second.next_cursor is None
        with pytest.raises(ServiceError) as foreign:
            registry.list_sources(WS_B, limit=2, cursor=first.next_cursor)
        assert code_of(foreign) is ErrorCode.INVALID_POINTER


def test_lookup_provides_symbol_provenance_pointer(tmp_path: Path) -> None:
    """
    함수 이름: test_lookup_provides_symbol_provenance_pointer()
    기능: 3.3 SourceRegistryPort.lookup이 같은 경로·내용 해시에만 포인터를 주는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    source = b"def run():\n    return 1\n"
    (roots.roots[WS_A] / "pkg").mkdir()
    (roots.roots[WS_A] / "pkg" / "mod.py").write_bytes(source)
    digest = hashlib.sha256(source).hexdigest()
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("pkg/mod.py")).items[0]
        assert registry.lookup(WS_A, "pkg/mod.py", digest) == record.pointer
        assert registry.lookup(WS_A, "pkg/mod.py", "0" * 64) is None
        assert registry.lookup(WS_B, "pkg/mod.py", digest) is None


def test_resolve_port_returns_verified_location(tmp_path: Path) -> None:
    """
    함수 이름: test_resolve_port_returns_verified_location()
    기능: 4.6/4.9용 resolve가 허용 root와 실제 경로를 주고, 오래된 revision은 거절하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    path = roots.roots[WS_A] / "a.txt"
    path.write_text("a\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("a.txt")).items[0]
        resolved = registry.resolve(WS_A, record.pointer)
        assert resolved.real_path == path.resolve()
        assert resolved.root == roots.roots[WS_A].resolve()
        with pytest.raises(ServiceError) as malformed:
            registry.resolve(WS_A, "securecode://source/ws_00000001/../x?v=1")
        assert code_of(malformed) is ErrorCode.INVALID_POINTER


def test_derived_cache_is_reference_counted(tmp_path: Path) -> None:
    """
    함수 이름: test_derived_cache_is_reference_counted()
    기능: 여러 등록이 공유한 파생 캐시는 마지막 참조 해제 때만 지워지고, 내용 변경 refresh도 참조를 푼다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / "a.txt").write_text("a\n")
    (roots.roots[WS_B] / "b.txt").write_text("b\n")
    cache_dir = tmp_path / "data" / "derived"
    with open_registry(tmp_path, roots) as registry:
        first = registry.register(WS_A, workspace_file("a.txt")).items[0]
        second = registry.register(WS_B, workspace_file("b.txt")).items[0]
        (cache_dir / "shared").mkdir()
        (cache_dir / "only_b").mkdir()
        registry.attach_derived(WS_A, first.pointer, "shared")
        registry.attach_derived(WS_B, second.pointer, "shared")
        registry.attach_derived(WS_B, second.pointer, "only_b")
        registry.unregister(WS_A, first.pointer)
        assert (cache_dir / "shared").is_dir()
        (roots.roots[WS_B] / "b.txt").write_text("b changed\n")
        registry.refresh(WS_B, second.pointer)
        assert not (cache_dir / "shared").exists()
        assert not (cache_dir / "only_b").exists()
    assert (roots.roots[WS_A] / "a.txt").exists()
