"""4.3 Runtime 부분 읽기·검색.

line/byte/한글 section/JSON, bytes·token cap과 범위 cursor, checksum 손상, 검사한다.
"""

import json
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.models.runtime import BlobCorrupt, RuntimePut
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.text import search_scan
from securecode_context.pointers.text.models import ReadRequest, SearchRequest, Selector
from support.helpers import FixedTokenCounter

WS, SES = "ws-1", "ses-1"


@pytest.fixture
def runtime(tmp_path: Path) -> tuple[RuntimeStore, RuntimeReader]:
    """
    함수 이름: runtime()
    기능: 실디스크 저장소와 시험 계수기(바이트=토큰) reader를 만든다.
    인자: tmp_path -> 임시 폴더
    반환값: (저장소, reader)
    작성 날짜: 2026/11/10
    """
    store = RuntimeStore(tmp_path / "runtime")
    yield store, RuntimeReader(store, FixedTokenCounter())  # type: ignore[misc]
    store.close()


def _put(store: RuntimeStore, data: bytes, media_type: str = "text/plain") -> str:
    """
    함수 이름: _put()
    기능: 출력을 저장하고 URI를 돌려준다.
    인자: store -> 저장소, data -> 본문, media_type -> 형식
    반환값: Runtime URI
    작성 날짜: 2026/11/10
    """
    return store.put(RuntimePut(WS, SES, media_type, data)).pointer


def test_selectors_return_exact_stored_ranges(runtime: tuple[RuntimeStore, RuntimeReader]) -> None:
    """
    함수 이름: test_selectors_return_exact_stored_ranges()
    기능: line(CRLF)·byte·한글 section·JSON 값이 저장 원문과 정확히 같은 구간인지 확인한다.
    인자: runtime -> 저장소와 reader
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store, reader = runtime
    log = "# 빌드\r\n시작\r\n## 오류\r\n실패: 테스트 3개\r\n# 배포\r\n완료\r\n".encode()
    pointer = _put(store, log)
    line = reader.read(WS, SES, ReadRequest(pointer, Selector("line", 4)))
    assert line.content == "실패: 테스트 3개"
    section = reader.read(WS, SES, ReadRequest(pointer, Selector("section", section="빌드")))
    assert "실패" in section.content and "배포" not in section.content
    for outcome in (line, section):
        assert outcome.span is not None
        assert log[outcome.span.start : outcome.span.end] == outcome.content.encode()
    clipped = reader.read(WS, SES, ReadRequest(pointer, Selector("byte", 0, 4)))
    assert (clipped.content, clipped.truncated) == ("# ", True)
    data = json.dumps({"result": {"failed": ["테스트3"]}}).encode()
    json_pointer = _put(store, data, "application/json")
    value = reader.read(
        WS, SES, ReadRequest(json_pointer, Selector("json_path", path="/result/failed/0"))
    )
    assert value.content == '"테스트3"'
    with pytest.raises(ServiceError) as unsupported:
        reader.read(WS, SES, ReadRequest(pointer, Selector("json_path", path="/a")))
    assert unsupported.value.code is ErrorCode.INVALID_SELECTOR


def test_caps_and_cursor_cover_long_line(runtime: tuple[RuntimeStore, RuntimeReader]) -> None:
    """
    함수 이름: test_caps_and_cursor_cover_long_line()
    기능: 개행 없는 긴 한글 줄을 bytes/token 상한으로 이어 읽으면 연속 구간이고 합치면 원문과 같은지 확인한다.
    인자: runtime -> 저장소와 reader
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store, reader = runtime
    original = ("가나다라" * 30_000).encode()
    pointer = _put(store, original)
    pieces: list[bytes] = []
    cursor = None
    expected = 0
    while True:
        outcome = reader.read(
            WS, SES, ReadRequest(pointer, max_bytes=16384, max_tokens=5000, cursor=cursor)
        )
        body = outcome.content.encode()
        assert len(body) <= 5000 and outcome.token_count == len(body)
        assert outcome.span is not None and outcome.span.start == expected
        assert outcome.io.max_chunk <= 64 * 1024
        expected = outcome.span.end
        pieces.append(body)
        cursor = outcome.next_cursor
        if cursor is None:
            break
    assert b"".join(pieces) == original


def test_cursor_and_uri_scope_binding(runtime: tuple[RuntimeStore, RuntimeReader]) -> None:
    """
    함수 이름: test_cursor_and_uri_scope_binding()
    기능: 다른 세션 URI는 FORBIDDEN, 다른 포인터·selector·변조 cursor는 INVALID_POINTER인지 확인한다.
    인자: runtime -> 저장소와 reader
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store, reader = runtime
    first = _put(store, b"0123456789" * 10)
    second = _put(store, b"abcdefghij" * 10)
    cursor = reader.read(WS, SES, ReadRequest(first, max_bytes=10)).next_cursor
    with pytest.raises(ServiceError) as foreign:
        reader.read(WS, "ses-other", ReadRequest(first))
    assert foreign.value.code is ErrorCode.FORBIDDEN
    for target, selector, token in [
        (second, None, cursor),
        (first, Selector("line", 1), cursor),
        (first, None, "tampered"),
    ]:
        with pytest.raises(ServiceError) as rejected:
            reader.read(WS, SES, ReadRequest(target, selector, max_bytes=10, cursor=token))
        assert rejected.value.code is ErrorCode.INVALID_POINTER


def test_corrupted_chunk_is_never_returned(runtime: tuple[RuntimeStore, RuntimeReader]) -> None:
    """
    함수 이름: test_corrupted_chunk_is_never_returned()
    기능: 저장 뒤 blob 바이트가 바뀌면 그 청크를 읽는 읽기·검색이 원문 대신 BlobCorrupt인지 확인한다.
    인자: runtime -> 저장소와 reader
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store, reader = runtime
    pointer = _put(store, b"a" * 70_000 + b"needle")
    blob = next(store.blobs.rglob("*.blob"))
    data = bytearray(blob.read_bytes())
    data[69_000] = ord("b")
    blob.write_bytes(bytes(data))
    assert reader.read(WS, SES, ReadRequest(pointer, Selector("byte", 0, 100))).content == "a" * 100
    with pytest.raises(BlobCorrupt):
        reader.read(WS, SES, ReadRequest(pointer, Selector("byte", 68_000, 70_000)))
    with pytest.raises(BlobCorrupt):
        reader.search(WS, SES, SearchRequest(pointer, "needle"))


def test_search_lines_limit_and_scan_cursor(
    runtime: tuple[RuntimeStore, RuntimeReader], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_search_lines_limit_and_scan_cursor()
    기능: 한글 검색의 줄 출처, limit 페이지, scan 상한 cursor가 중복·누락 없이 이어지는지 확인한다.
    인자: runtime -> 저장소와 reader, monkeypatch -> scan 상한 축소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    store, reader = runtime
    lines = [
        f"{index:05} {'오류 발생' if index % 1000 == 0 else '정상'}" for index in range(30_000)
    ]
    pointer = _put(store, "\n".join(lines).encode())
    monkeypatch.setattr(search_scan, "SCAN_LIMIT_BYTES", 64 * 1024)
    found: list[int] = []
    cursor = None
    calls = 0
    while True:
        outcome = reader.search(WS, SES, SearchRequest(pointer, "오류", limit=7, cursor=cursor))
        calls += 1
        assert outcome.io.bytes_read <= 2 * 64 * 1024
        found += [match.line for match in outcome.matches]
        cursor = outcome.next_cursor
        if cursor is None:
            break
    assert found == [index + 1 for index in range(0, 30_000, 1000)] and calls > 5
