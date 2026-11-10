"""4.6 Source 부분 읽기: line/byte/section/json_path, UTF-8·CRLF·긴 줄, bytes/token cap과 cursor."""

import json
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers import limits
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.read_models import ReadOutcome, ReadRequest, Selector
from support.source_fixtures import WS_A, code_of, open_adapter, single_workspace, workspace_file


def _setup(tmp_path: Path, name: str, data: bytes) -> tuple[SourceAdapter, str, Path]:
    """
    함수 이름: _setup()
    기능: 파일 하나를 만들고 등록한 adapter를 연다.
    인자: tmp_path -> 임시 폴더, name -> 파일 이름, data -> 내용
    반환값: adapter, 포인터, 파일 경로
    작성 날짜: 2026/11/10
    """
    roots, root = single_workspace(tmp_path)
    (root / name).write_bytes(data)
    adapter = open_adapter(tmp_path, roots)
    pointer = adapter.registry.register(WS_A, workspace_file(name)).items[0].pointer
    return adapter, pointer, root / name


def _read(
    adapter: SourceAdapter, pointer: str, selector: Selector | None = None, **caps: object
) -> ReadOutcome:
    """
    함수 이름: _read()
    기능: 읽기 요청을 보낸다.
    인자: adapter -> Source adapter, pointer -> URI, selector -> 범위, caps -> max_bytes/max_tokens/cursor
    반환값: ReadOutcome
    작성 날짜: 2026/11/10
    """
    return adapter.reader.read(WS_A, ReadRequest(pointer, selector, **caps))  # type: ignore[arg-type]


def _assert_exact(outcome: ReadOutcome, original: bytes) -> None:
    """
    함수 이름: _assert_exact()
    기능: 반환 본문이 원본의 표시 구간과 정확히 같은지 확인한다.
    인자: outcome -> 읽기 결과, original -> 원본 바이트
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    assert outcome.span is not None
    assert original[outcome.span.start : outcome.span.end] == outcome.content.encode("utf-8")


def test_line_ranges_with_crlf_korean_and_unterminated_last_line(tmp_path: Path) -> None:
    """
    함수 이름: test_line_ranges_with_crlf_korean_and_unterminated_last_line()
    기능: CRLF·한글 줄 범위가 원본 구간과 같고, 마지막 개행 유무와 범위 밖 줄을 정확히 처리하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "첫 줄\r\n둘째 가나다\r\n셋째\r\n끝".encode()
    adapter, pointer, _ = _setup(tmp_path, "notes.txt", original)
    with adapter.registry:
        middle = _read(adapter, pointer, Selector("line", 2, 3))
        assert middle.content == "둘째 가나다\r\n셋째"
        _assert_exact(middle, original)
        assert _read(adapter, pointer, Selector("line", 4)).content == "끝"
        with pytest.raises(ServiceError) as outside:
            _read(adapter, pointer, Selector("line", 5))
        assert outside.value.details["reason"] == "line_out_of_range"
        with pytest.raises(ServiceError) as reversed_range:
            _read(adapter, pointer, Selector("line", 3, 2))
        assert reversed_range.value.details["reason"] == "end_before_start"


def test_trailing_newline_does_not_add_a_line(tmp_path: Path) -> None:
    """
    함수 이름: test_trailing_newline_does_not_add_a_line()
    기능: 개행으로 끝나는 파일의 마지막 줄이 개행 없이 반환되고 빈 줄이 추가되지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, _ = _setup(tmp_path, "a.log", b"x\ny\n")
    with adapter.registry:
        assert _read(adapter, pointer, Selector("line", 2)).content == "y"
        with pytest.raises(ServiceError):
            _read(adapter, pointer, Selector("line", 3))


def test_byte_ranges_respect_utf8_boundaries(tmp_path: Path) -> None:
    """
    함수 이름: test_byte_ranges_respect_utf8_boundaries()
    기능: 문자 중간 시작은 거부하고, 문자 중간 끝은 가장 긴 유효 앞부분과 truncated를 돌려주는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "가나다".encode()
    adapter, pointer, _ = _setup(tmp_path, "k.txt", original)
    with adapter.registry:
        clipped = _read(adapter, pointer, Selector("byte", 0, 4))
        assert (clipped.content, clipped.truncated, clipped.next_cursor) == ("가", True, None)
        _assert_exact(clipped, original)
        for selector, reason in [
            (Selector("byte", 1, 6), "utf8_boundary"),
            (Selector("byte", 6, 3), "end_before_start"),
            (Selector("byte", 0, 10), "byte_out_of_range"),
        ]:
            with pytest.raises(ServiceError) as rejected:
                _read(adapter, pointer, selector)
            assert rejected.value.details["reason"] == reason


def test_markdown_section_by_korean_heading(tmp_path: Path) -> None:
    """
    함수 이름: test_markdown_section_by_korean_heading()
    기능: 한글 제목 section이 하위 제목을 포함하고 같은 수준 제목 앞에서 끝나며, 코드 펜스 안 #은 무시하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    text = "# 개요\n소개\n```\n# 코드 안 주석\n```\n## 세부\n내용\n# 다음\n끝\n# 중복\n# 중복\n"
    original = text.encode()
    adapter, pointer, _ = _setup(tmp_path, "doc.md", original)
    with adapter.registry:
        section = _read(adapter, pointer, Selector("section", section="개요"))
        assert section.content.startswith("# 개요\n") and section.content.endswith("내용\n")
        assert "# 다음" not in section.content
        _assert_exact(section, original)
        for name, reason in [("코드 안 주석", "heading_not_found"), ("중복", "heading_ambiguous")]:
            with pytest.raises(ServiceError) as rejected:
                _read(adapter, pointer, Selector("section", section=name))
            assert rejected.value.details["reason"] == reason


def test_json_path_is_capped_full_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    함수 이름: test_json_path_is_capped_full_parse()
    기능: JSON Pointer 값 조회, 없는 경로 오류, 구조 조회 상한 초과 시 크기 오류와 line 읽기 대안을 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 구조 조회 상한 축소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    document = {"a": {"b/c": [1, {"한글": "값"}]}, "padding": "x" * 200}
    adapter, pointer, _ = _setup(tmp_path, "data.json", json.dumps(document).encode())
    with adapter.registry:
        value = _read(adapter, pointer, Selector("json_path", path="/a/b~1c/1/한글"))
        assert (value.content, value.span) == ('"값"', None)
        with pytest.raises(ServiceError) as missing:
            _read(adapter, pointer, Selector("json_path", path="/a/zzz"))
        assert code_of(missing) is ErrorCode.INVALID_SELECTOR
        monkeypatch.setattr(limits, "MAX_JSON_PATH_BYTES", 64)
        with pytest.raises(ServiceError) as too_large:
            _read(adapter, pointer, Selector("json_path", path="/a"))
        assert code_of(too_large) is ErrorCode.PAYLOAD_TOO_LARGE
        assert _read(adapter, pointer, Selector("line", 1), max_bytes=10).content == '{"a": {"b/'


def test_byte_and_token_caps_with_contiguous_cursor(tmp_path: Path) -> None:
    """
    함수 이름: test_byte_and_token_caps_with_contiguous_cursor()
    기능: 작은 bytes/token 상한으로 cursor를 따라 읽으면 구간이 이어지고 합치면 원본과 같은지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "".join(f"{index:03} 한글 줄 내용\n" for index in range(200)).encode()
    adapter, pointer, _ = _setup(tmp_path, "long.txt", original)
    with adapter.registry:
        pieces: list[bytes] = []
        cursor: str | None = None
        expected_start = 0
        for _ in range(1000):
            outcome = _read(adapter, pointer, max_bytes=100, max_tokens=70, cursor=cursor)
            body = outcome.content.encode()
            assert len(body) <= 70 and outcome.token_count == len(body)
            assert outcome.count_mode == "provider_estimate"
            assert outcome.span is not None and outcome.span.start == expected_start
            expected_start = outcome.span.end
            pieces.append(body)
            cursor = outcome.next_cursor
            if cursor is None:
                break
        assert b"".join(pieces) == original


def test_long_single_line_is_paged_not_loaded(tmp_path: Path) -> None:
    """
    함수 이름: test_long_single_line_is_paged_not_loaded()
    기능: 개행 없는 긴 한 줄도 16 KiB씩 cursor로 읽고 한 번에 읽은 양이 상한을 넘지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = b"needle" + b"x" * 100_000
    adapter, pointer, _ = _setup(tmp_path, "one.log", original)
    with adapter.registry:
        first = _read(adapter, pointer, Selector("line", 1))
        assert len(first.content) == 16384 and first.truncated and first.next_cursor
        assert first.io.max_chunk <= 64 * 1024
        # The first line read also builds the line index; a repeat read is bounded by the cap.
        repeat = _read(adapter, pointer, Selector("line", 1))
        assert repeat.io.bytes_read <= 16384 + 2
        second = _read(adapter, pointer, Selector("line", 1), cursor=first.next_cursor)
        assert second.span is not None and second.span.start == 16384
        assert second.io.bytes_read <= 16384


def test_corrupt_utf8_is_reported_with_offset(tmp_path: Path) -> None:
    """
    함수 이름: test_corrupt_utf8_is_reported_with_offset()
    기능: 등록 뒤쪽의 깨진 UTF-8 바이트를 대체 문자로 숨기지 않고 위치와 함께 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = b"a" * 9000 + b"\xff" + b"tail"
    adapter, pointer, _ = _setup(tmp_path, "bad.txt", original)
    with adapter.registry:
        with pytest.raises(ServiceError) as corrupt:
            _read(adapter, pointer, Selector("byte", 8990, 9005))
        assert code_of(corrupt) is ErrorCode.UNSUPPORTED_FORMAT
        assert corrupt.value.details == {"reason": "invalid_utf8", "byte_offset": 9000}
        assert _read(adapter, pointer, Selector("byte", 0, 10)).content == "a" * 10


def test_cursor_is_bound_to_request(tmp_path: Path) -> None:
    """
    함수 이름: test_cursor_is_bound_to_request()
    기능: 다른 selector·다른 원본·변조 cursor를 INVALID_POINTER로 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, path = _setup(tmp_path, "a.txt", b"0123456789" * 10)
    (path.parent / "b.txt").write_bytes(b"0123456789" * 10)
    with adapter.registry:
        other = adapter.registry.register(WS_A, workspace_file("b.txt")).items[0].pointer
        cursor = _read(adapter, pointer, Selector("line", 1), max_bytes=10).next_cursor
        assert cursor is not None
        for target, selector, token in [
            (pointer, Selector("byte", 0), cursor),
            (other, Selector("line", 1), cursor),
            (pointer, Selector("line", 1), "not-a-cursor"),
        ]:
            with pytest.raises(ServiceError) as rejected:
                _read(adapter, target, selector, cursor=token)
            assert code_of(rejected) is ErrorCode.INVALID_POINTER


def test_pdf_source_is_left_to_page_tools(tmp_path: Path) -> None:
    """
    함수 이름: test_pdf_source_is_left_to_page_tools()
    기능: PDF 원문 바이트를 텍스트 읽기로 내보내지 않는지 확인한다(4.9 페이지 도구 범위).
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, _ = _setup(tmp_path, "a.pdf", b"%PDF-1.4\n%%EOF\n")
    with adapter.registry, pytest.raises(ServiceError) as rejected:
        _read(adapter, pointer)
    assert rejected.value.details["reason"] == "pdf_requires_page_tool"
