"""텍스트 PDF 페이지 추출(4.9). pypdf로 page tree 순서대로 페이지별 텍스트를 뽑는다.

OCR·암호 해제는 하지 않는다. 이 모듈은 격리된 worker 프로세스 안에서만 실행한다(worker.py).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from securecode_context.pdf.limits import MAX_PAGE_TEXT_BYTES


class PdfRejectedError(Exception):
    """
    클래스 이름: PdfRejectedError
    기능: 문서 전체를 읽을 수 없는 결과. state는 unsupported 또는 failed, reason은 계약 PdfJobStatus 값이다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, state: str, reason: str) -> None:
        """
        함수 이름: __init__()
        기능: 상태와 이유를 저장한다.
        인자: state -> unsupported/failed, reason -> 계약 이유
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        super().__init__(f"{state}:{reason}")
        self.state = state
        self.reason = reason


@dataclass(frozen=True)
class ExtractedPage:
    """
    클래스 이름: ExtractedPage
    기능: 페이지 하나의 텍스트 또는 제외 이유(empty_page·scanned_page·unreadable_page).
    작성 날짜: 2026/11/10
    """

    number: int
    text: str | None
    excluded: str | None = None


def _has_images(page: object) -> bool:
    """
    함수 이름: _has_images()
    기능: 페이지 리소스에 이미지가 있는지 본다(스캔 페이지 판정용). 읽을 수 없으면 False다.
    인자: page -> pypdf PageObject
    반환값: 이미지가 있으면 True
    작성 날짜: 2026/11/10
    """
    try:
        return len(page.images) > 0  # type: ignore[attr-defined]
    except Exception:
        return False


def _page(number: int, page: object) -> ExtractedPage:
    """
    함수 이름: _page()
    기능: 페이지 텍스트를 뽑고 비었으면 이미지 유무로 빈/스캔 페이지를 가린다.
    인자: number -> 1부터 시작하는 페이지 번호, page -> pypdf PageObject
    반환값: ExtractedPage
    작성 날짜: 2026/11/10
    """
    try:
        text = page.extract_text() or ""  # type: ignore[attr-defined]
        size = len(text.encode("utf-8"))
    except Exception:
        return ExtractedPage(number, None, "unreadable_page")
    if size > MAX_PAGE_TEXT_BYTES:
        return ExtractedPage(number, None, "unreadable_page")
    if not text.strip():
        return ExtractedPage(number, None, "scanned_page" if _has_images(page) else "empty_page")
    return ExtractedPage(number, text)


def extract_pages(path: Path, page_limit: int) -> list[ExtractedPage]:
    """
    함수 이름: extract_pages()
    기능: PDF를 열어 암호화·페이지 수를 확인하고 page tree 순서로 페이지를 추출한다.
        읽을 수 있는 페이지가 하나도 없으면 scanned_document/empty_document로 거절한다.
    인자: path -> 서비스가 복사한 원본, page_limit -> 최대 페이지 수
    반환값: 페이지 목록
    작성 날짜: 2026/11/10
    """
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise PdfRejectedError("unsupported", "encrypted")
        pages = list(reader.pages)
    except PdfRejectedError:
        raise
    except Exception as error:
        raise PdfRejectedError("failed", "damaged") from error
    if not pages:
        raise PdfRejectedError("unsupported", "empty_document")
    if len(pages) > page_limit:
        raise PdfRejectedError("unsupported", "page_limit")
    extracted = [_page(index + 1, page) for index, page in enumerate(pages)]
    if all(page.text is None for page in extracted):
        scanned = any(page.excluded == "scanned_page" for page in extracted)
        raise PdfRejectedError("unsupported", "scanned_document" if scanned else "empty_document")
    return extracted
