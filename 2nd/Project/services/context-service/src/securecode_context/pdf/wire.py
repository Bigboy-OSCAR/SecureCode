"""PDF 계약 DTO 변환(4.9): PdfJobStatus와 pdf_page selection."""

from typing import Any

from securecode_context.pdf.cache import PdfManifest
from securecode_context.pdf.limits import PARSER_VERSION


def job_status(
    job_id: str,
    workspace_id: str,
    pointer: str,
    state: str,
    reason: str | None = None,
    manifest: PdfManifest | None = None,
) -> dict[str, Any]:
    """
    함수 이름: job_status()
    기능: 상태별 필드만 담은 PdfJobStatus를 만든다. ready/partial에도 추출 본문은 넣지 않는다.
    인자: job_id/workspace_id/pointer -> 식별, state -> 상태, reason -> 이유, manifest -> 완료 결과
    반환값: PdfJobStatus 사전
    작성 날짜: 2026/11/10
    """
    status: dict[str, Any] = {
        "schema_version": "1",
        "job_id": job_id,
        "workspace_id": workspace_id,
        "pointer": pointer,
        "state": state,
    }
    if state in ("ready", "partial"):
        assert manifest is not None
        status["content_sha256"] = manifest.content_sha256
        status["parser_version"] = manifest.parser_version
        status["page_count"] = manifest.page_count
        if state == "partial":
            status["excluded_pages"] = manifest.excluded()
    elif state not in ("queued", "running"):
        status["reason"] = reason
    return status


def page_selection(
    revision: int, content_sha256: str, page: int, start: int, end: int
) -> dict[str, Any]:
    """
    함수 이름: page_selection()
    기능: 페이지 추출 텍스트 안 반열린 바이트 구간의 PointerSelection을 만든다.
    인자: revision/content_sha256 -> 원본, page -> 1부터, start/end -> 페이지 텍스트 바이트 구간
    반환값: PointerSelection 사전
    작성 날짜: 2026/11/10
    """
    byte_range = {
        "type": "pdf_page",
        "page": page,
        "start": start,
        "end": end,
        "parser_version": PARSER_VERSION,
    }
    return {"revision": revision, "content_sha256": content_sha256, "range": byte_range}
