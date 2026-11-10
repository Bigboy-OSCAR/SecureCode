"""Runtime 출력의 형식별 selector 정책. 도구 출력은 UTF-8 텍스트로 저장한다."""

from securecode_context.pointers import limits

JSON_MEDIA = "application/json"
TEXT_MEDIAS = frozenset({"text/plain", "text/markdown", "text/x-log", JSON_MEDIA})


def supported_selectors(media_type: str, byte_size: int) -> list[str]:
    """
    함수 이름: supported_selectors()
    기능: 줄·바이트·한글 제목 section은 모든 텍스트 출력에, JSON 구조 조회는 8 MiB 이하 JSON에만 연다.
    인자: media_type -> 형식, byte_size -> 크기
    반환값: 계약 supported_selectors
    작성 날짜: 2026/11/10
    """
    selectors = ["line", "byte", "section"]
    if media_type == JSON_MEDIA and byte_size <= limits.MAX_JSON_PATH_BYTES:
        selectors.append("json_path")
    return selectors
