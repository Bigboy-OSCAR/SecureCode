from pathlib import Path

import pytest

from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore


def test_put_and_read_full_content(tmp_path: Path) -> None:
    """함수 이름: test_put_and_read_full_content()
    기능: SQLite 저장 후 전체 읽기 결과를 확인한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = SQLiteRuntimeStore(db_path=tmp_path / "test.db")

    pointer_id = store.put(
        content="hello world",
        workspace_id="w1",
        session_id="s1",
    )

    result = store.read(
        pointer_id=pointer_id,
        workspace_id="w1",
        session_id="s1",
    )

    assert result.content == "hello world"
    assert result.next_cursor is None
    assert result.truncated is False


def test_read_with_cursor(tmp_path: Path) -> None:
    """함수 이름: test_read_with_cursor()
    기능: 커서가 다음 ASCII 조각을 이어 읽는지 확인한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = SQLiteRuntimeStore(db_path=tmp_path / "test.db")

    content = "0123456789" * 10
    pointer_id = store.put(
        content=content,
        workspace_id="w1",
        session_id="s1",
    )

    first = store.read(
        pointer_id=pointer_id,
        workspace_id="w1",
        session_id="s1",
        max_bytes=10,
    )

    assert first.content == "0123456789"
    assert first.next_cursor == 10
    assert first.truncated is True

    second = store.read(
        pointer_id=pointer_id,
        workspace_id="w1",
        session_id="s1",
        cursor=first.next_cursor,
        max_bytes=10,
    )

    assert second.content == "0123456789"
    assert second.next_cursor == 20


def test_utf8_roundtrip_and_limits(tmp_path: Path) -> None:
    """함수 이름: test_utf8_roundtrip_and_limits()
    기능: 다중 바이트 문자를 자르지 않고 이어 읽으며 유효하지 않은 위치·한도를 거부한다.
    인자: tmp_path -> 임시 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = SQLiteRuntimeStore(tmp_path / "data.db")
    payload = "a한💾글b"
    pointer = store.put(payload, "space", "session")
    text, cursor = "", 0
    while True:
        chunk = store.read(pointer, "space", "session", cursor, 4)
        text += chunk.content
        if chunk.next_cursor is None:
            break
        assert chunk.next_cursor == len(text.encode()) > cursor
        cursor = chunk.next_cursor
    assert text == payload
    for offset, limit in [(1, 1), (2, 4), (-1, 1), (999, 1), (0, 0), (0, 16385)]:
        with pytest.raises(ValueError):
            store.read(pointer, "space", "session", offset, limit)


def test_session_and_expiration(tmp_path: Path) -> None:
    """함수 이름: test_session_and_expiration()
    기능: 범위가 다른 읽기·삭제와 만료 항목을 두 저장소 모두에서 검사한다.
    인자: tmp_path -> 임시 디렉터리, persistent -> SQLite 사용 여부
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = SQLiteRuntimeStore(tmp_path / "data.db")
    pointer = store.put("sensitive", "space", "a")
    other_session = store.put("other", "space", "b")
    for workspace, session in [("other", "a"), ("space", "b")]:
        with pytest.raises(PermissionError):
            store.read(pointer, workspace, session)
        assert not store.delete(pointer, workspace, session)
        assert pointer not in store.list(workspace, session)
    expired = store.put("expire", "space", "a", ttl_seconds=0)
    with pytest.raises(TimeoutError):
        store.read(expired, "space", "a")
    assert store.list("space", "a") == [pointer]
    assert store.clear_session("space", "a") == 1
    assert store.list("space", "b") == [other_session]
    with pytest.raises(KeyError):
        store.read(pointer, "space", "a")
