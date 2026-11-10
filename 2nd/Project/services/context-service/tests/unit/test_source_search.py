"""4.6 Source 검색: 한글·NFD·CRLF, 줄/바이트 위치와 원본 구간, 결과·bytes·token 상한, scan 상한과 cursor."""

import unicodedata
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.read_models import SearchOutcome, SearchRequest
from securecode_context.pointers.text import search_scan
from support.source_fixtures import WS_A, code_of, open_adapter, single_workspace, workspace_file


def _setup(tmp_path: Path, name: str, data: bytes) -> tuple[SourceAdapter, str]:
    """
    함수 이름: _setup()
    기능: 파일 하나를 만들고 등록한 adapter를 연다.
    인자: tmp_path -> 임시 폴더, name -> 파일 이름, data -> 내용
    반환값: adapter와 포인터
    작성 날짜: 2026/11/10
    """
    roots, root = single_workspace(tmp_path)
    (root / name).write_bytes(data)
    adapter = open_adapter(tmp_path, roots)
    return adapter, adapter.registry.register(WS_A, workspace_file(name)).items[0].pointer


def _search(adapter: SourceAdapter, pointer: str, query: str, **options: object) -> SearchOutcome:
    """
    함수 이름: _search()
    기능: 검색 요청을 보낸다.
    인자: adapter -> Source adapter, pointer -> URI, query -> 검색어, options -> limit/상한/cursor
    반환값: SearchOutcome
    작성 날짜: 2026/11/10
    """
    request = SearchRequest(pointer, query, **options)  # type: ignore[arg-type]
    return adapter.searcher.search(WS_A, request)


def _all_pages(
    adapter: SourceAdapter, pointer: str, query: str, **options: object
) -> list[SearchOutcome]:
    """
    함수 이름: _all_pages()
    기능: next_cursor가 없을 때까지 검색을 이어 간다.
    인자: adapter, pointer, query -> 검색 대상, options -> 요청 옵션
    반환값: 페이지 목록
    작성 날짜: 2026/11/10
    """
    pages = [_search(adapter, pointer, query, **options)]
    while pages[-1].next_cursor is not None:
        pages.append(_search(adapter, pointer, query, cursor=pages[-1].next_cursor, **options))
        assert len(pages) < 200
    return pages


def test_korean_search_reports_line_offset_and_exact_snippet(tmp_path: Path) -> None:
    """
    함수 이름: test_korean_search_reports_line_offset_and_exact_snippet()
    기능: 한글 검색의 줄 번호·일치 위치와, 미리보기가 원본 구간과 같고 CR을 포함하지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "def hello():\r\n    # 처리 함수\r\n    print('안녕')\r\n".encode()
    adapter, pointer = _setup(tmp_path, "code.py", original)
    with adapter.registry:
        result = _search(adapter, pointer, "처리")
    assert [(match.line, match.byte_offset) for match in result.matches] == [
        (2, original.index("처리".encode()))
    ]
    match = result.matches[0]
    assert match.content == "    # 처리 함수"
    assert original[match.span.start : match.span.end] == match.content.encode()
    assert (result.truncated, result.next_cursor) == (False, None)


def test_nfd_source_is_found_by_nfc_query(tmp_path: Path) -> None:
    """
    함수 이름: test_nfd_source_is_found_by_nfc_query()
    기능: 조합형(NFD)으로 저장된 한글도 지우거나 바꾸지 않고 찾는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = unicodedata.normalize("NFD", "제목: 한글 문서\n").encode()
    adapter, pointer = _setup(tmp_path, "nfd.txt", original)
    with adapter.registry:
        result = _search(adapter, pointer, "한글")
    assert len(result.matches) == 1
    assert unicodedata.normalize("NFC", result.matches[0].content) == "제목: 한글 문서"


def test_limit_pages_cover_all_matches_once(tmp_path: Path) -> None:
    """
    함수 이름: test_limit_pages_cover_all_matches_once()
    기능: 250개 일치를 limit 100으로 이어 읽으면 중복·누락 없이 오름차순인지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "".join(f"줄 {index} 대상\n" for index in range(250)).encode()
    adapter, pointer = _setup(tmp_path, "many.txt", original)
    with adapter.registry:
        pages = _all_pages(adapter, pointer, "대상", limit=100)
    lines = [match.line for page in pages for match in page.matches]
    assert [len(page.matches) for page in pages] == [100, 100, 50]
    assert lines == list(range(1, 251))
    assert all(page.truncated for page in pages[:-1]) and not pages[-1].truncated


def test_byte_and_token_caps_drop_matches_and_resume(tmp_path: Path) -> None:
    """
    함수 이름: test_byte_and_token_caps_drop_matches_and_resume()
    기능: 미리보기 합계가 상한을 넘으면 뒤 일치를 다음 페이지로 넘기고 모든 일치를 한 번씩 돌려주는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    original = "".join(f"{index:02} target line\n" for index in range(30)).encode()
    adapter, pointer = _setup(tmp_path, "caps.txt", original)
    with adapter.registry:
        by_bytes = _all_pages(adapter, pointer, "target", max_bytes=100)
        by_tokens = _all_pages(adapter, pointer, "target", max_tokens=60)
    for pages, cap in ((by_bytes, 100), (by_tokens, 60)):
        assert len(pages) > 1
        assert all(
            sum(len(m.content.encode()) + 1 for m in page.matches) <= cap + 1 for page in pages
        )
        assert [m.line for page in pages for m in page.matches] == list(range(1, 31))


def test_scan_limit_returns_cursor_and_keeps_line_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_scan_limit_returns_cursor_and_keeps_line_numbers()
    기능: scan 상한에 닿으면 빈 결과+cursor를 주고, 이어서 찾은 일치의 줄 번호가 정확한지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> scan 상한 축소
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    monkeypatch.setattr(search_scan, "SCAN_LIMIT_BYTES", 128 * 1024)
    filler = "".join(f"filler {index:06}\n" for index in range(40_000)).encode()
    adapter, pointer = _setup(tmp_path, "big.log", filler + "마지막 needle\n".encode())
    with adapter.registry:
        first = _search(adapter, pointer, "needle")
        assert first.matches == [] and first.truncated and first.next_cursor
        assert first.io.bytes_read <= 128 * 1024 + 64 * 1024
        pages = _all_pages(adapter, pointer, "needle")
    found = [match for page in pages for match in page.matches]
    assert [(match.line, match.content) for match in found] == [(40_001, "마지막 needle")]


def test_match_across_chunk_boundary_and_long_line(tmp_path: Path) -> None:
    """
    함수 이름: test_match_across_chunk_boundary_and_long_line()
    기능: 64 KiB 청크 경계에 걸친 일치와 긴 한 줄 안 일치를 한 번씩 찾는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    boundary = 64 * 1024
    original = b"x" * (boundary - 3) + b"needle" + b"y" * 100_000 + b"needle"
    adapter, pointer = _setup(tmp_path, "edge.log", original)
    with adapter.registry:
        result = _search(adapter, pointer, "needle")
    assert [match.byte_offset for match in result.matches] == [boundary - 3, len(original) - 6]
    assert all(match.line == 1 for match in result.matches)


def test_no_match_and_invalid_queries(tmp_path: Path) -> None:
    """
    함수 이름: test_no_match_and_invalid_queries()
    기능: 일치 없음은 오류가 아닌 빈 결과이고, 범위 밖 검색어·limit은 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer = _setup(tmp_path, "a.txt", b"alpha\n")
    with adapter.registry:
        empty = _search(adapter, pointer, "없음")
        assert (empty.matches, empty.truncated, empty.token_count) == ([], False, 0)
        for options in ({"query": "x" * 257}, {"query": "a", "limit": 101}):
            with pytest.raises(ServiceError) as rejected:
                adapter.searcher.search(WS_A, SearchRequest(pointer, **options))  # type: ignore[arg-type]
            assert code_of(rejected) is ErrorCode.VALIDATION_FAILED
