"""완료 항목 감사에서 발견한 경로·범위·변경 검증 회귀 시험."""

from pathlib import Path

import pytest

from securecode_context.pointers.models.runtime import InvalidSelector, RuntimePut, ScopeForbidden
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.source.index import LineIndexer
from securecode_context.pointers.source.models import SourceRegistrationRequest
from securecode_context.pointers.source.readers import BoundedSourceReader
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.source.search import BoundedSourceSearcher


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
    original = "한글abc한글"
    try:
        descriptor = store.put(RuntimePut("workspace", "session", "text/plain", original.encode()))
        pointer_id = descriptor.pointer.split("/")[-1].split("?")[0]
        offset = 0
        result = ""
        while True:
            part = store.read("workspace", "session", pointer_id, offset, max_bytes=4)
            result += part.content
            assert part.byte_size <= 4
            if part.next_cursor is None:
                break
            offset = int(part.next_cursor)
        assert result == original
        with pytest.raises(InvalidSelector):
            store.read("workspace", "session", pointer_id, max_bytes=1_000_000)
        with pytest.raises(InvalidSelector):
            store.list("workspace", "session", limit=-1)
    finally:
        store.close()


def _source(tmp_path: Path, text: str) -> tuple[SourceRegistry, str, Path]:
    """함수 이름: _source()
    기능: 임시 workspace 파일을 등록한다.
    인자: tmp_path -> 임시 폴더, text -> 원문
    반환값: 등록부, 포인터, 원본 경로
    작성 날짜: 2026/11/09
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "source.txt"
    source.write_text(text)
    registry = SourceRegistry(workspace_roots={"ws": str(workspace)})
    descriptor = registry.register(SourceRegistrationRequest("ws", str(source)))
    return registry, descriptor.pointer, source


def test_source_symlink_replacement_is_rejected(tmp_path: Path) -> None:
    """함수 이름: test_source_symlink_replacement_is_rejected()
    기능: 동일 내용의 외부 파일로 교체해 hash 검사를 통과하는 경로 이탈을 막는다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    registry, pointer, source = _source(tmp_path, "same contents")
    outside = tmp_path / "outside.txt"
    outside.write_text("same contents")
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(ValueError, match="FORBIDDEN"):
        BoundedSourceReader(registry).read_range(pointer)


def test_source_detects_change_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """함수 이름: test_source_detects_change_before_return()
    기능: 조회 시작 후 변경된 원문을 정상 결과로 반환하지 않는다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 변경 시점 주입
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    registry, pointer, source = _source(tmp_path, "before\n")
    original_stat = registry.stat
    calls = 0

    def stat_with_change(value: str):
        """함수 이름: stat_with_change()
        기능: 조회 종료 검증 직전 원문 변경을 주입한다.
        인자: value -> 포인터
        반환값: 원래 stat 결과
        작성 날짜: 2026/11/09
        """
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("after\n")
        return original_stat(value)

    monkeypatch.setattr(registry, "stat", stat_with_change)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        BoundedSourceReader(registry).read_range(pointer)


def test_source_long_line_is_not_silently_truncated(tmp_path: Path) -> None:
    """함수 이름: test_source_long_line_is_not_silently_truncated()
    기능: 거대한 한 줄을 메모리에 읽거나 성공한 빈 결과로 숨기지 않는다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    registry, pointer, _ = _source(tmp_path, "needle" + "x" * 100_000)
    with pytest.raises(ValueError, match="cap exceeded"):
        BoundedSourceReader(registry).read_range(pointer)
    result = BoundedSourceSearcher(registry).search(pointer, "needle")
    assert result["truncated"] is True


def test_source_json_requires_pointer_and_bounds_output(tmp_path: Path) -> None:
    """함수 이름: test_source_json_requires_pointer_and_bounds_output()
    기능: 임의 경로 조회와 큰 JSON 전체 결과를 거부한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    registry, pointer, source = _source(tmp_path, '{"small": 7, "large": "' + "x" * 20_000 + '"}')
    reader = BoundedSourceReader(registry)
    assert reader.read_json_path(pointer, "$.small") == 7
    with pytest.raises(ValueError, match="PAYLOAD_TOO_LARGE"):
        reader.read_json_path(pointer)
    with pytest.raises(KeyError, match="NOT_FOUND"):
        reader.read_json_path(str(source))


def test_line_index_keeps_unterminated_last_line(tmp_path: Path) -> None:
    """함수 이름: test_line_index_keeps_unterminated_last_line()
    기능: 개행이 없는 마지막 줄과 한 줄 파일의 범위를 보존한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/09
    """
    source = tmp_path / "text.txt"
    source.write_bytes(b"first\nlast")
    index = LineIndexer(str(source))
    assert index.get_line_bounds(1) == (0, 6)
    assert index.get_line_bounds(2) == (6, 10)
