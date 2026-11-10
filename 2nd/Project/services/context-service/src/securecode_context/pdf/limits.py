"""PDF 파싱 상한과 파서 버전(4.9). 캐시 키·selection에 파서 버전이 들어가므로 바꾸면 기존 페이지는 stale이 된다."""

from importlib.metadata import version

from securecode_context.pointers.source.media import MAX_PDF_BYTES, PDF_MEDIA

PARSER_VERSION = f"pdf-text-v1+pypdf-{version('pypdf')}"
MAX_PDF_PAGES = 500
PARSE_TIMEOUT_SECONDS = 60.0
MAX_PAGE_TEXT_BYTES = 1024 * 1024
MAX_PARALLEL_JOBS = 2

__all__ = [
    "MAX_PAGE_TEXT_BYTES",
    "MAX_PARALLEL_JOBS",
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "PARSER_VERSION",
    "PARSE_TIMEOUT_SECONDS",
    "PDF_MEDIA",
]
