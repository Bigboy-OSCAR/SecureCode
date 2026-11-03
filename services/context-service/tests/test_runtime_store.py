from securecode_context.pointers.runtime.store import RuntimeStore


def test_runtime_put_and_read():
    store = RuntimeStore()
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

    assert result == "hello world"
