"""PDF 페이지 후보 resolver(4.9). Source 후보 중 PDF는 pdf_page selection이 있어야 읽는다.

대상은 (PDF 경로, 원본 SHA-256, 파서 버전, 페이지)이고 구간은 그 페이지 추출 텍스트의 바이트 구간이다.
selection 없는 PDF 후보(파일 전체)는 넣지 않는다(no_match).
"""

from dataclasses import dataclass, replace

from securecode_context.context.models import Candidate, Material, Span, Wire
from securecode_context.pdf.limits import PARSER_VERSION
from securecode_context.pdf.pages import PdfPages
from securecode_context.pdf.wire import page_selection
from securecode_context.pointers.source.models import SourceRecord


@dataclass(frozen=True)
class PdfTarget:
    """
    클래스 이름: PdfTarget
    기능: 해석한 PDF 페이지 대상.
    작성 날짜: 2026/11/10
    """

    pointer: str
    revision: int
    content_sha256: str
    page: int
    display: str


class PdfResolver:
    """
    클래스 이름: PdfResolver
    기능: workspace 범위의 PDF 페이지 후보를 해석하고 4.9 페이지 reader로 상한 안에서 읽는다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, pages: PdfPages, workspace_id: str) -> None:
        """
        함수 이름: __init__()
        기능: 페이지 reader와 범위를 저장한다.
        인자: pages -> PdfPages, workspace_id -> 인증된 범위
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._pages = pages
        self._workspace_id = workspace_id

    def inspect(self, candidate: Candidate, record: SourceRecord) -> Candidate:
        """
        함수 이름: inspect()
        기능: selection의 revision·해시·파서 버전을 확인하고 페이지 구간을 대상 구간으로 정한다.
        인자: candidate -> Source 후보, record -> 해석한 PDF 레코드
        반환값: 상태·구간을 채운 후보
        작성 날짜: 2026/11/10
        """
        selection: Wire | None = candidate.ref.get("selection")
        if selection is None or selection["range"]["type"] != "pdf_page":
            return replace(candidate, status="no_match")
        page_range = selection["range"]
        current = (record.revision, record.fingerprint, PARSER_VERSION)
        wanted = (selection["revision"], selection["content_sha256"], page_range["parser_version"])
        if wanted != current:
            return replace(candidate, status="stale")
        if not 0 <= page_range["start"] < page_range["end"]:
            return replace(candidate, status="no_match")
        page = page_range["page"]
        key = ("pdf", str(record.relative_path), record.fingerprint, PARSER_VERSION, str(page))
        target = PdfTarget(
            record.pointer, record.revision, record.fingerprint, page, record.pointer
        )
        span = Span(key, page_range["start"], page_range["end"])
        return replace(candidate, span=span, handle=target)

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 페이지 텍스트의 구간을 읽고 pdf_page selection을 출처로 붙인다.
        인자: candidate -> PDF 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        target: PdfTarget = candidate.handle
        size = min(span.end - span.start, 16 * 1024)
        caps = (size, min(max_tokens, 32 * 1024))
        outcome = self._pages.read_span(
            self._workspace_id, target.pointer, target.page, (span.start, span.end), caps
        )
        assert outcome.span is not None
        got = outcome.span
        selection = page_selection(
            target.revision, target.content_sha256, target.page, got.start, got.end
        )
        ref: Wire = {"kind": "source", "pointer": target.pointer, "selection": selection}
        return Material(
            content=outcome.content,
            token_count=outcome.token_count,
            count_mode=outcome.count_mode,
            span=Span(span.object_key, got.start, got.end),
            citation={"ref": ref},
            complete=got.end == span.end,
        )
