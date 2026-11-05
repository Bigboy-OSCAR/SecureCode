import os
from pathlib import Path
from typing import BinaryIO

import pytest

from securecode_context.pointers.source.store import SourceStore


def test_source_register_and_read(tmp_path: Path) -> None:
    """함수 이름: test_source_register_and_read()
    기능: 원본의 줄 선택 범위를 검사한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    file_path = tmp_path / "sample.txt"
    file_path.write_text("line1\nline2\nline3")

    store = SourceStore(root_dir=str(tmp_path))
    source_id = store.register("sample.txt", workspace_id="w1")

    result = store.read(
        source_id=source_id,
        workspace_id="w1",
        start_line=2,
        end_line=3,
    )

    assert result == "line2\nline3"


def test_late_lines_and_short_utf8_window(tmp_path: Path) -> None:
    """함수 이름: test_late_lines_and_short_utf8_window()
    기능: 긴 첫 줄 이후의 선택 범위에 바이트 한도를 적용하고 CRLF를 처리한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    path = tmp_path / "log"
    path.write_bytes(("x" * 100_000 + "\r\n가나다\r\nend\n").encode())
    store = SourceStore(str(tmp_path))
    pointer = store.register("log", "w")
    assert store.read(pointer, "w", 2, 3, 8) == "가나"
    assert store.read(pointer, "w", 3, 3, 3) == "end"
    for start, end, cap in [(0, 1, 1), (2, 1, 1), (1, 1, 0)]:
        with pytest.raises(ValueError):
            store.read(pointer, "w", start, end, cap)


def test_changed_version_and_revoked_id(tmp_path: Path) -> None:
    """함수 이름: test_changed_version_and_revoked_id()
    기능: 같은 크기·mtime으로 교체한 원본과 등록 해제 후 이전 ID의 재사용을 검증한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    path = tmp_path / "source"
    path.write_text("old")
    store = SourceStore(str(tmp_path))
    pointer = store.register("source", "w")
    assert store.register("source", "w") == pointer
    saved = path.stat()
    replacement = tmp_path / "replacement"
    replacement.write_text("new")
    os.utime(replacement, ns=(saved.st_atime_ns, saved.st_mtime_ns))
    replacement.replace(path)
    with pytest.raises(ValueError, match="changed"):
        store.read(pointer, "w")
    new_pointer = store.register("source", "w")
    assert pointer != new_pointer
    assert not store.unregister(new_pointer, "other")
    with pytest.raises(PermissionError):
        store.read(new_pointer, "other")
    assert store.unregister(new_pointer, "w")
    assert store.register("source", "w") != new_pointer
    assert path.read_text() == "new"


def test_workspace_escape_after_registration(tmp_path: Path) -> None:
    """함수 이름: test_workspace_escape_after_registration()
    기능: 등록 후 디렉터리가 외부 경로 링크로 바뀌어도 원문이 반환되지 않는지 검사한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    root, outside = tmp_path / "root", tmp_path / "outside"
    sub = root / "sub"
    sub.mkdir(parents=True)
    outside.mkdir()
    (sub / "file").write_text("ok")
    (outside / "file").write_text("secret")
    store = SourceStore(str(root))
    pointer = store.register("sub/file", "w")
    sub.rename(root / "original")
    sub.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        store.read(pointer, "w")
    for path in ["sub/file", str(outside / "file"), "../outside/file"]:
        with pytest.raises(PermissionError):
            store.register(path, "w")


def test_change_during_read_rejects_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """함수 이름: test_change_during_read_rejects_the_result()
    기능: 요청 처리 도중 원본 내용이 바뀌면 이전 결과를 반환하지 않는지 확인한다.
    인자: tmp_path -> 임시 경로, monkeypatch -> 조회와 검증 사이에 원본을 교체
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    path = tmp_path / "source"
    path.write_text("previous")
    store = SourceStore(str(tmp_path))
    pointer = store.register("source", "w")
    original = store._read_lines

    def replace_during_read(file: BinaryIO, start: int, end: int | None, limit: int) -> str:
        """함수 이름: replace_during_read()
        기능: 원문 조각을 읽은 직후 같은 파일의 내용을 바꾼다.
        인자: file/start/end/limit -> 기존 읽기 인자
        반환값: 검증 대상으로 삼을 이전 원문
        작성 날짜: 2026/11/05
        """
        text = original(file, start, end, limit)
        path.write_text("changed after reading")
        return text

    monkeypatch.setattr(store, "_read_lines", replace_during_read)
    with pytest.raises(ValueError, match="changed"):
        store.read(pointer, "w")
