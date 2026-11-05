from securecode_context.pointers.runtime.store import RuntimeStore


def test_runtime_put_and_read() -> None:
    """함수 이름: test_runtime_put_and_read()
    기능: 메모리 런타임 원문 왕복 읽기를 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
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
