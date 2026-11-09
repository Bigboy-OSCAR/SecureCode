"""등록된 Source에서 제한된 양의 줄과 검색 결과만 읽는다."""

from typing import Any

from securecode_context.pointers.source.readers import (
    MAX_LINE_BYTES,
    MAX_SCAN_BYTES,
    MAX_TOTAL_BYTES,
)
from securecode_context.pointers.source.registry import SourceRegistry


class BoundedSourceSearcher:
    """클래스 이름: BoundedSourceSearcher
    기능: 검색 스캔과 미리보기 크기를 제한하고 조회 후 revision을 확인한다.
    작성 날짜: 2026/11/09
    """

    def __init__(self, registry: SourceRegistry) -> None:
        """함수 이름: __init__()
        기능: 검색할 Source 등록부를 보관한다.
        인자: registry -> Source 등록부
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.registry = registry

    def search(self, pointer: str, query: str, max_matches: int = 50) -> dict[str, Any]:
        """함수 이름: search()
        기능: 줄 번호와 제한된 미리보기를 반환한다. 상한 도달은 잘림으로 표시한다.
        인자: pointer -> 등록된 포인터, query -> 리터럴 검색어, max_matches -> 결과 개수 상한
        반환값: 검색 결과와 잘림 상태
        작성 날짜: 2026/11/09
        """
        if not 1 <= len(query) <= 256 or not 1 <= max_matches <= 100:
            raise ValueError("INVALID_SELECTOR: Invalid query or match cap")
        descriptor = self.registry.stat(pointer)
        matches: list[dict[str, Any]] = []
        scanned = 0
        output_bytes = 0
        truncated = False
        with open(descriptor.real_path, "rb") as stream:
            line_number = 0
            while True:
                raw = stream.readline(min(MAX_LINE_BYTES, MAX_SCAN_BYTES - scanned) + 1)
                if not raw:
                    break
                scanned += len(raw)
                if scanned > MAX_SCAN_BYTES or len(raw) > MAX_LINE_BYTES:
                    truncated = True
                    break
                line_number += 1
                if query in raw.decode("utf-8", errors="strict"):
                    content = raw[:512].decode("utf-8", errors="ignore").strip()
                    # Reserve metadata overhead for every match as well as preview bytes.
                    output_bytes += len(content.encode("utf-8")) + 128
                    if output_bytes > MAX_TOTAL_BYTES:
                        truncated = True
                        break
                    matches.append({"line_number": line_number, "content": content})
                    if len(matches) >= max_matches:
                        truncated = True
                        break
        self.registry.stat(pointer)
        return {
            "pointer": pointer,
            "query": query,
            "matches": matches,
            "total_matches": len(matches),
            "truncated": truncated,
        }
