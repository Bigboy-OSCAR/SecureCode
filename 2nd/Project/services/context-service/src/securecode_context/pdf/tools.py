"""PDF 서비스 facade(4.9): 앱이 쓰는 parse·status·cancel·read·search 연산과 검색 결과 계약 변환.

전체 추출 텍스트를 돌려주는 연산은 없다. parse/status는 Source 식별·페이지 수·job 상태만 돌려주고,
본문은 read(pdf_page selector)와 search 미리보기로만 상한 안에서 나간다.
"""

from pathlib import Path
from typing import Any

from securecode_context.common.tokens import TokenCounter
from securecode_context.pdf.cache import PdfPageCache
from securecode_context.pdf.jobs import PdfJobs
from securecode_context.pdf.pages import PdfPages
from securecode_context.pdf.wire import page_selection
from securecode_context.pointers.source.derived import DerivedCacheDirectory
from securecode_context.pointers.source.read_models import ReadOutcome, ReadRequest
from securecode_context.pointers.source.registry import SourceRegistry


class PdfService:
    """
    클래스 이름: PdfService
    기능: 등록부·파생 캐시를 공유하는 PDF job과 페이지 reader 묶음.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        registry: SourceRegistry,
        derived: DerivedCacheDirectory,
        counter: TokenCounter,
        work_root: Path,
        timeout: float | None = None,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 페이지 캐시·job·reader를 만든다.
        인자: registry -> Source 등록부, derived -> 4.5 파생 캐시 폴더, counter -> TokenCounter,
            work_root -> 파생 캐시와 같은 볼륨의 작업 폴더, timeout -> 파싱 시간 상한(None이면 기본값)
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        cache = PdfPageCache(derived)
        self.jobs = (
            PdfJobs(registry, cache, work_root)
            if timeout is None
            else PdfJobs(registry, cache, work_root, timeout)
        )
        self.pages = PdfPages(registry, cache, counter)

    def parse(self, workspace_id: str, pointer: str) -> dict[str, Any]:
        """
        함수 이름: parse()
        기능: parse job을 제출하거나 같은 job을 돌려준다.
        인자: workspace_id -> 범위, pointer -> 현재 revision URI
        반환값: PdfJobStatus
        작성 날짜: 2026/11/10
        """
        return self.jobs.submit(workspace_id, pointer)

    def read(self, workspace_id: str, request: ReadRequest) -> ReadOutcome:
        """
        함수 이름: read()
        기능: pdf_page selector 읽기.
        인자: workspace_id -> 범위, request -> 읽기 요청
        반환값: ReadOutcome
        작성 날짜: 2026/11/10
        """
        return self.pages.read(workspace_id, request)

    def search(
        self, workspace_id: str, pointer: str, query: str, limit: int, caps: tuple[int, int]
    ) -> dict[str, Any]:
        """
        함수 이름: search()
        기능: 페이지 검색 결과를 PointerSearchResult로 만든다(일치마다 pdf_page selection).
        인자: workspace_id/pointer -> 대상, query -> 검색어, limit -> 최대 수, caps -> 상한
        반환값: PointerSearchResult 사전
        작성 날짜: 2026/11/10
        """
        record, matches, truncated, tokens, mode = self.pages.search(
            workspace_id, pointer, query, limit, caps
        )
        rows = []
        for item in matches:
            span = item.match.span
            row: dict[str, Any] = {
                "line": item.match.line,
                "content": item.match.content,
                "byte_offset": item.match.byte_offset,
            }
            if span.end > span.start:
                row["selection"] = page_selection(
                    record.revision, record.fingerprint, item.page, span.start, span.end
                )
            rows.append(row)
        return {
            "schema_version": "1",
            "pointer": pointer,
            "matches": rows,
            "truncated": truncated,
            "token_count": tokens,
            "count_mode": mode,
        }

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 진행 중 job을 취소하고 정리한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.jobs.close()
