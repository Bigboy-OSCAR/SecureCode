"""포인터 저장소의 바이트 단위 읽기와 TTL 경계."""

import codecs

MAX_READ_BYTES = 16 * 1024
MAX_READ_TOKENS = 32 * 1024
MAX_SEARCH_LIMIT = 100
MAX_QUERY_CHARS = 256
MAX_JSON_PATH_BYTES = 8 * 1024 * 1024
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MAX_TTL_SECONDS = 2**31 - 1


def check_read_limit(max_bytes: int) -> None:
    """함수 이름: check_read_limit()
    기능: 한 번의 포인터 읽기에 적용할 출력 상한을 검사한다.
    인자: max_bytes -> 요청한 바이트 수
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    if not 1 <= max_bytes <= MAX_READ_BYTES:
        raise ValueError("invalid max_bytes")


def check_ttl(ttl_seconds: int) -> None:
    """함수 이름: check_ttl()
    기능: TTL이 저장 가능한 범위인지 확인한다. 0이면 즉시 만료된다.
    인자: ttl_seconds -> 수명(초)
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    if not 0 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError("invalid ttl_seconds")


def utf8_prefix(data: bytes) -> tuple[str, int]:
    """함수 이름: utf8_prefix()
    기능: 마지막의 미완성 코드 포인트 직전까지 엄격하게 디코딩한다.
    인자: data -> 제한된 바이트 범위
    반환값: 디코딩한 문자열과 소비한 바이트 수
    작성 날짜: 2026/11/05
    """
    return codecs.utf_8_decode(data, "strict", False)
