"""4.6 bounded I/O 계측: 64 MiB 이상 텍스트에서 반복 범위 조회·검색이 파일 크기만큼 읽지 않는지 측정한다."""

import tracemalloc
from collections.abc import Iterator

import pytest

from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.read_models import ReadRequest, SearchRequest, Selector
from securecode_context.pointers.text import search_scan
from securecode_context.pointers.text.io_meter import CHUNK_BYTES
from support.source_fixtures import WS_A, open_adapter, single_workspace, workspace_file

TARGET_BYTES = 64 * 1024 * 1024 + 1
LINE = "line {:07d} 한글 패딩 텍스트 padding text\n"


@pytest.fixture(scope="module")
def big_source(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[SourceAdapter, str, bytes, int]]:
    """
    함수 이름: big_source()
    기능: 64 MiB를 넘는 텍스트를 만들고 등록한다(모듈에서 한 번).
    인자: tmp_path_factory -> 임시 폴더 생성기
    반환값: adapter, 포인터, 한 줄 예시 바이트, 줄 수
    작성 날짜: 2026/11/10
    """
    tmp_path = tmp_path_factory.mktemp("bounded")
    roots, root = single_workspace(tmp_path)
    written = 0
    lines = 0
    with (root / "huge.log").open("wb") as handle:
        while written < TARGET_BYTES:
            block = "".join(LINE.format(lines + offset + 1) for offset in range(10_000)).encode()
            handle.write(block)
            written += len(block)
            lines += 10_000
    adapter = open_adapter(tmp_path, roots)
    pointer = adapter.registry.register(WS_A, workspace_file("huge.log")).items[0].pointer
    yield adapter, pointer, LINE.format(1).encode(), lines
    adapter.close()


def test_repeated_late_line_reads_are_bounded(
    big_source: tuple[SourceAdapter, str, bytes, int],
) -> None:
    """
    함수 이름: test_repeated_late_line_reads_are_bounded()
    기능: 최초 색인은 순차 scan 1회, 이후 뒤쪽 줄 반복 조회는 각각 128 KiB 이하만 읽고 버퍼는 64 KiB 이하인지 측정한다.
    인자: big_source -> 등록된 대형 원본
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, sample, lines = big_source
    size = adapter.registry.stat(WS_A, pointer).byte_size
    assert size >= 64 * 1024 * 1024
    first = adapter.reader.read(WS_A, ReadRequest(pointer, Selector("line", lines - 5)))
    assert first.io.bytes_read >= size  # one-time sequential index build (documented)
    assert first.io.max_chunk <= CHUNK_BYTES
    targets = [lines - 1, lines // 2, 7, lines - 3, 1]
    total = 0
    for target in targets:
        outcome = adapter.reader.read(WS_A, ReadRequest(pointer, Selector("line", target)))
        assert outcome.content == LINE.format(target).rstrip("\n")
        assert outcome.io.bytes_read <= 2 * CHUNK_BYTES + len(sample) + 2
        assert outcome.io.max_chunk <= CHUNK_BYTES
        total += outcome.io.bytes_read
    assert total < size // 50
    print(f"[bounded-io] size={size} first={first.io.bytes_read} repeat_total={total}")


def test_byte_range_and_cursor_reads_touch_only_the_window(
    big_source: tuple[SourceAdapter, str, bytes, int],
) -> None:
    """
    함수 이름: test_byte_range_and_cursor_reads_touch_only_the_window()
    기능: 파일 끝 근처 바이트 범위와 cursor 이어 읽기가 요청 상한만큼만 읽고,
        파이썬 메모리 최고치가 작게 유지되는지 측정한다.
    인자: big_source -> 등록된 대형 원본
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, sample, _ = big_source
    size = adapter.registry.stat(WS_A, pointer).byte_size
    start = size - 100 * len(sample)  # every line has the same byte length, so this is a line start
    request = ReadRequest(pointer, Selector("byte", start, size), max_bytes=4096)
    tracemalloc.start()
    try:
        outcome = adapter.reader.read(WS_A, request)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert outcome.io.bytes_read <= 4096 + 1 and peak < 1024 * 1024
    assert outcome.span is not None and outcome.span.start == start
    following = adapter.reader.read(
        WS_A,
        ReadRequest(
            pointer, Selector("byte", start, size), max_bytes=4096, cursor=outcome.next_cursor
        ),
    )
    assert following.span is not None and following.span.start == outcome.span.end
    assert following.io.bytes_read <= 4096
    print(f"[bounded-io] byte window read={outcome.io.bytes_read} peak_alloc={peak}")


def test_search_scan_per_call_is_capped(big_source: tuple[SourceAdapter, str, bytes, int]) -> None:
    """
    함수 이름: test_search_scan_per_call_is_capped()
    기능: 대형 원본 검색이 호출마다 scan 상한(8 MiB)+청크 1개 이하만 읽고 cursor로 이어지는지 측정한다.
    인자: big_source -> 등록된 대형 원본
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    adapter, pointer, _, _ = big_source
    outcome = adapter.searcher.search(WS_A, SearchRequest(pointer, "존재하지 않는 검색어"))
    assert outcome.matches == [] and outcome.next_cursor is not None
    assert outcome.io.bytes_read <= search_scan.SCAN_LIMIT_BYTES + CHUNK_BYTES
    assert outcome.io.max_chunk <= CHUNK_BYTES
