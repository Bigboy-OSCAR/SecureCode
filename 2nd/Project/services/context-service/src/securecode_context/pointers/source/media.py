"""Source 형식 판별과 형식별 크기·연산·selector 정책."""

import codecs

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers import limits

MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024
PREVIEW_BYTES = 512
PDF_MEDIA = "application/pdf"
JSON_MEDIA = "application/json"
MARKDOWN_MEDIA = "text/markdown"
TEXT_MEDIA = "text/plain"

_BY_EXTENSION = {
    ".pdf": PDF_MEDIA,
    ".json": JSON_MEDIA,
    ".md": MARKDOWN_MEDIA,
    ".markdown": MARKDOWN_MEDIA,
}


def _unsupported(reason: str) -> ServiceError:
    """
    함수 이름: _unsupported()
    기능: 등록할 수 없는 형식 오류를 만든다.
    인자: reason -> details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(
        ErrorCode.UNSUPPORTED_FORMAT, "지원하지 않는 파일 형식입니다.", {"reason": reason}
    )


def _is_utf8_text(head: bytes) -> bool:
    """
    함수 이름: _is_utf8_text()
    기능: 앞부분이 NUL 없는 UTF-8인지 확인한다. 잘린 마지막 코드 포인트는 허용한다.
    인자: head -> 파일 앞부분
    반환값: 텍스트로 볼 수 있으면 True
    작성 날짜: 2026/11/10
    """
    if b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")("strict").decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def detect_media(name: str, head: bytes) -> str:
    """
    함수 이름: detect_media()
    기능: 확장자와 내용 서명이 일치할 때만 형식을 정한다. PDF 위장·텍스트 위장 이진 파일은 거부한다.
    인자: name -> 파일 이름, head -> 파일 앞부분
    반환값: media type
    작성 날짜: 2026/11/10
    """
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    declared = _BY_EXTENSION.get(suffix, TEXT_MEDIA)
    looks_pdf = head.startswith(b"%PDF-")
    if declared == PDF_MEDIA:
        if not looks_pdf:
            raise _unsupported("pdf_signature_missing")
        return PDF_MEDIA
    if looks_pdf:
        raise _unsupported("extension_mismatch")
    if not _is_utf8_text(head):
        raise _unsupported("binary_content")
    return declared


def size_limit(media_type: str) -> int:
    """
    함수 이름: size_limit()
    기능: 형식별 등록 크기 상한을 돌려준다(로드맵 0.7).
    인자: media_type -> 판별한 형식
    반환값: 최대 바이트
    작성 날짜: 2026/11/10
    """
    return MAX_PDF_BYTES if media_type == PDF_MEDIA else MAX_SOURCE_BYTES


def available_operations(media_type: str) -> list[str]:
    """
    함수 이름: available_operations()
    기능: 형식이 제공할 포인터 연산을 정한다. PDF 본문은 파싱 뒤 4.9 페이지 읽기·검색으로만 읽는다.
    인자: media_type -> 형식
    반환값: 계약 available_operations
    작성 날짜: 2026/11/10
    """
    return ["read", "search"]


def supported_selectors(media_type: str, byte_size: int) -> list[str]:
    """
    함수 이름: supported_selectors()
    기능: 형식과 크기에 맞는 selector 종류를 정한다. JSON 구조 조회는 8 MiB 이하만 연다.
    인자: media_type -> 형식, byte_size -> 원본 크기
    반환값: 계약 supported_selectors
    작성 날짜: 2026/11/10
    """
    if media_type == PDF_MEDIA:
        return ["pdf_page"]
    selectors = ["line", "byte"]
    if media_type == MARKDOWN_MEDIA:
        selectors.append("section")
    if media_type == JSON_MEDIA and byte_size <= limits.MAX_JSON_PATH_BYTES:
        selectors.append("json_path")
    return selectors


def preview_of(media_type: str, head: bytes) -> str:
    """
    함수 이름: preview_of()
    기능: 512 UTF-8 바이트 이하의 미리보기를 만든다. PDF는 파싱 전이라 비워 둔다.
    인자: media_type -> 형식, head -> 파일 앞부분
    반환값: 미리보기 문자열
    작성 날짜: 2026/11/10
    """
    if media_type == PDF_MEDIA:
        return ""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    return decoder.decode(head[:PREVIEW_BYTES], final=False)
