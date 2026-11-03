from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore


def test_put_and_read_full_content(tmp_path):
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


def test_read_with_cursor(tmp_path):
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
