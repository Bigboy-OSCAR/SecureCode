"""응답 bytes/token 상한 적용. UTF-8 문자를 자르지 않고, 토큰 수는 3.2 TokenCounter로만 센다(길이/4 금지)."""

import codecs
from dataclasses import dataclass

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.common.tokens.models import CountMode
from securecode_context.pointers.limits import MAX_READ_BYTES, MAX_READ_TOKENS

MAX_SHRINK_ROUNDS = 8


@dataclass(frozen=True)
class Fitted:
    """
    클래스 이름: Fitted
    기능: 상한 안에 맞춘 본문, 소비한 원본 바이트, 토큰 수와 계수 방식.
    작성 날짜: 2026/11/10
    """

    text: str
    used: int
    token_count: int
    count_mode: str


def check_caps(max_bytes: int, max_tokens: int) -> None:
    """
    함수 이름: check_caps()
    기능: 요청 상한이 계약 범위(16,384바이트, 32,768토큰) 안인지 확인한다.
    인자: max_bytes -> 바이트 상한, max_tokens -> 토큰 상한
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if not 1 <= max_bytes <= MAX_READ_BYTES or not 1 <= max_tokens <= MAX_READ_TOKENS:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED,
            "max_bytes/max_tokens 범위를 벗어났습니다.",
            {"reason": "cap_range"},
        )


def decode_prefix(data: bytes, final: bool, at: int) -> tuple[str, int]:
    """
    함수 이름: decode_prefix()
    기능: 완성된 UTF-8 문자까지만 디코딩한다. 잘못된 바이트나 구간 끝의 미완성 문자는 오류다.
    인자: data -> 원본 바이트, final -> data가 요청 구간 끝까지인지, at -> 오류 위치 계산용 시작 위치
    반환값: 문자열과 소비한 바이트 수
    작성 날짜: 2026/11/10
    """
    try:
        text, used = codecs.utf_8_decode(data, "strict", False)
    except UnicodeDecodeError as error:
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FORMAT,
            "UTF-8로 읽을 수 없는 바이트가 있습니다.",
            {"reason": "invalid_utf8", "byte_offset": at + error.start},
        ) from error
    if final and used < len(data):
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FORMAT,
            "UTF-8 문자가 중간에서 끝났습니다.",
            {"reason": "invalid_utf8", "byte_offset": at + used},
        )
    return text, used


def count_tokens(counter: TokenCounter, text: str) -> tuple[int, str]:
    """
    함수 이름: count_tokens()
    기능: 본문 토큰 수를 센다. 빈 본문은 0(exact)이다.
    인자: counter -> TokenCounter, text -> 본문
    반환값: 토큰 수와 count_mode
    작성 날짜: 2026/11/10
    """
    if not text:
        return 0, CountMode.EXACT.value
    counted = counter.count(text)
    return counted.token_count, counted.count_mode.value


def fit_text(
    data: bytes, final: bool, at: int, max_bytes: int, max_tokens: int, counter: TokenCounter
) -> Fitted:
    """
    함수 이름: fit_text()
    기능: 바이트 상한으로 자른 뒤 토큰 수가 넘으면 비율로 줄여 다시 센다(최대 8회).
    인자: data -> 원본 바이트(상한보다 길 수 있음), final -> 구간 끝 포함 여부, at -> 시작 위치,
        max_bytes/max_tokens -> 상한, counter -> TokenCounter
    반환값: Fitted
    작성 날짜: 2026/11/10
    """
    window = data[:max_bytes]
    text, used = decode_prefix(window, final and len(window) == len(data), at)
    for _ in range(MAX_SHRINK_ROUNDS):
        tokens, mode = count_tokens(counter, text)
        if tokens <= max_tokens:
            return Fitted(text, used, tokens, mode)
        target = int(used * max_tokens / tokens * 0.9)
        text, used = decode_prefix(data[:target], False, at)
        if not text:
            break
    raise ServiceError(
        ErrorCode.BUDGET_EXCEEDED,
        "토큰 상한이 너무 작아 내용을 담을 수 없습니다.",
        {"reason": "token_cap_too_small"},
    )
