"""4.6 읽기·검색 중 원본 변경, 오래된 cursor·revision, 원본 삭제, 경로 이탈, 다른 workspace 거부."""

from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.read_models import ReadRequest, SearchRequest, Selector
from securecode_context.pointers.text import engine, search_scan
from support.source_fixtures import (
    WS_A,
    WS_B,
    code_of,
    make_dir_link,
    make_workspaces,
    open_adapter,
    workspace_file,
)


def _setup(tmp_path: Path, relative: str, data: bytes) -> tuple[SourceAdapter, str, Path]:
    """
    함수 이름: _setup()
    기능: WS_A에 파일을 만들고 등록한 adapter를 연다.
    인자: tmp_path -> 임시 폴더, relative -> 상대 경로, data -> 내용
    반환값: adapter, 포인터, 파일 경로
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    path = roots.roots[WS_A] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    adapter = open_adapter(tmp_path, roots)
    pointer = adapter.registry.register(WS_A, workspace_file(relative)).items[0].pointer
    return adapter, pointer, path


def test_change_during_read_is_source_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_change_during_read_is_source_changed()
    기능: 원본을 읽은 직후·반환 전에 파일이 바뀌면 섞인 결과 대신 SOURCE_CHANGED인지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 변경 시점 주입
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "a.txt", b"before\n" * 100)
    original_fit = engine.fit_text

    def fit_then_change(*args: object, **kwargs: object) -> object:
        """
        함수 이름: fit_then_change()
        기능: 읽은 본문을 맞춘 직후 원본에 내용을 덧붙인다.
        인자: args/kwargs -> fit_text 인자
        반환값: 원래 결과
        작성 날짜: 2026/11/10
        """
        result = original_fit(*args, **kwargs)  # type: ignore[arg-type]
        with path.open("ab") as handle:
            handle.write(b"appended during read\n")
        return result

    monkeypatch.setattr(engine, "fit_text", fit_then_change)
    with adapter.registry, pytest.raises(ServiceError) as changed:
        adapter.reader.read(WS_A, ReadRequest(pointer, Selector("line", 1, 2)))
    assert code_of(changed) is ErrorCode.SOURCE_CHANGED


def test_change_during_search_is_source_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_change_during_search_is_source_changed()
    기능: 검색 scan 직후 원본이 바뀌면 결과를 내보내지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 변경 시점 주입
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "a.txt", b"needle\n" * 10)
    original_scan = search_scan.scan

    def scan_then_change(*args: object, **kwargs: object) -> object:
        """
        함수 이름: scan_then_change()
        기능: scan 직후 원본을 바꾼다.
        인자: args/kwargs -> scan 인자
        반환값: 원래 결과
        작성 날짜: 2026/11/10
        """
        result = original_scan(*args, **kwargs)  # type: ignore[arg-type]
        path.write_bytes(b"other content\n")
        return result

    monkeypatch.setattr(search_scan, "scan", scan_then_change)
    with adapter.registry, pytest.raises(ServiceError) as changed:
        adapter.searcher.search(WS_A, SearchRequest(pointer, "needle"))
    assert code_of(changed) is ErrorCode.SOURCE_CHANGED


def test_stale_cursor_and_revision_after_refresh(tmp_path: Path) -> None:
    """
    함수 이름: test_stale_cursor_and_revision_after_refresh()
    기능: 변경 뒤 이전 cursor로 새 원문을 읽지 못하고, refresh 뒤에도 이전 cursor·포인터를 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "a.txt", b"0123456789" * 20)
    with adapter.registry:
        first = adapter.reader.read(WS_A, ReadRequest(pointer, max_bytes=10))
        assert first.next_cursor is not None
        path.write_bytes(b"ABCDEFGHIJ" * 20)
        with pytest.raises(ServiceError) as changed:
            adapter.reader.read(WS_A, ReadRequest(pointer, max_bytes=10, cursor=first.next_cursor))
        assert code_of(changed) is ErrorCode.SOURCE_CHANGED
        refreshed = adapter.registry.refresh(WS_A, pointer).pointer
        with pytest.raises(ServiceError) as stale_cursor:
            adapter.reader.read(
                WS_A, ReadRequest(refreshed, max_bytes=10, cursor=first.next_cursor)
            )
        assert code_of(stale_cursor) is ErrorCode.SOURCE_CHANGED
        fresh = adapter.reader.read(WS_A, ReadRequest(refreshed, max_bytes=10))
        assert fresh.content == "ABCDEFGHIJ" and fresh.record.revision == 2


def test_deleted_original_and_other_workspace(tmp_path: Path) -> None:
    """
    함수 이름: test_deleted_original_and_other_workspace()
    기능: 다른 workspace 읽기·검색은 FORBIDDEN, 원본 삭제 뒤 읽기는 NOT_FOUND인지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "a.txt", b"secret\n")
    with adapter.registry:
        with pytest.raises(ServiceError) as foreign_read:
            adapter.reader.read(WS_B, ReadRequest(pointer))
        with pytest.raises(ServiceError) as foreign_search:
            adapter.searcher.search(WS_B, SearchRequest(pointer, "secret"))
        assert {code_of(foreign_read), code_of(foreign_search)} == {ErrorCode.FORBIDDEN}
        path.unlink()
        with pytest.raises(ServiceError) as missing:
            adapter.reader.read(WS_A, ReadRequest(pointer))
        assert code_of(missing) is ErrorCode.NOT_FOUND


def test_path_swapped_to_link_is_forbidden_for_reads(tmp_path: Path) -> None:
    """
    함수 이름: test_path_swapped_to_link_is_forbidden_for_reads()
    기능: 등록 뒤 상위 폴더를 같은 내용의 외부 링크로 바꾸면 읽기·검색이 경로 재검증에서 거부되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "docs/a.txt", b"same\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.txt").write_bytes(b"same\n")
    path.unlink()
    path.parent.rmdir()
    make_dir_link(path.parent, outside)
    with adapter.registry:
        for action in (
            lambda: adapter.reader.read(WS_A, ReadRequest(pointer)),
            lambda: adapter.searcher.search(WS_A, SearchRequest(pointer, "same")),
        ):
            with pytest.raises(ServiceError) as denied:
                action()
            assert code_of(denied) is ErrorCode.FORBIDDEN
