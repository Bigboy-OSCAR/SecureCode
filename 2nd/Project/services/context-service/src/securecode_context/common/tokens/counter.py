"""TokenCounter 포트와 입력 검사. 최종 provider framing과 총 요청 gate는 4.8이 확장한다."""

from dataclasses import dataclass
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.models import MAX_COUNT_TEXT_BYTES, TokenCount


@dataclass(frozen=True)
class CounterStatus:
    """
    클래스 이름: CounterStatus
    기능: health에 보일 계수기 준비 상태(설정 여부와 미설정 이유)를 담는다.
    작성 날짜: 2026/11/04
    """

    configured: bool
    reason: str | None = None


class TokenCounter(Protocol):
    """
    클래스 이름: TokenCounter
    기능: 본문 텍스트의 토큰 수를 세는 포트. 실패 시 TOKENIZER_UNAVAILABLE을 던지고 길이/4를 쓰지 않는다.
    작성 날짜: 2026/11/04
    """

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: text 하나의 토큰 수를 센다.
        인자: text -> 계수할 본문
            model_id -> 생략하면 설정 모델, 다르면 TOKENIZER_UNAVAILABLE
        반환값: TokenCount
        작성 날짜: 2026/11/04
        """
        ...

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 계수기 준비 상태를 돌려준다.
        인자: 없음
        반환값: CounterStatus
        작성 날짜: 2026/11/04
        """
        ...


def measure_countable_text(text: str) -> int:
    """
    함수 이름: measure_countable_text()
    기능: 계수 전에 Unicode 유효성(외톨이 surrogate 금지)과 1 MiB 상한을 검사한다.
    인자: text -> 계수할 본문
    반환값: UTF-8 바이트 수
    작성 날짜: 2026/11/04
    """
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED,
            "텍스트에 올바르지 않은 Unicode 문자가 있습니다.",
            {"reason": "invalid_unicode"},
        ) from error

    if not encoded:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED, "빈 텍스트는 계수할 수 없습니다.", {"reason": "empty"}
        )
    if len(encoded) > MAX_COUNT_TEXT_BYTES:
        raise ServiceError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            "계수할 텍스트가 너무 큽니다.",
            {"max_bytes": MAX_COUNT_TEXT_BYTES, "text_bytes": len(encoded)},
        )
    return len(encoded)


class UnavailableTokenCounter:
    """
    클래스 이름: UnavailableTokenCounter
    기능: 키가 없거나 지원하지 않는 설정일 때 모든 계수를 TOKENIZER_UNAVAILABLE로 거절한다.
    작성 날짜: 2026/11/04
    """

    def __init__(self, reason: str) -> None:
        """
        함수 이름: __init__()
        기능: 사용할 수 없는 이유를 저장한다.
        인자: reason -> 예: api_key_missing, provider_not_supported
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        self.reason = reason

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 입력을 검사한 뒤 항상 TOKENIZER_UNAVAILABLE을 던진다(추정값을 만들지 않는다).
        인자: text -> 계수할 본문
            model_id -> 무시한다
        반환값: 반환하지 않는다
        작성 날짜: 2026/11/04
        """
        measure_countable_text(text)
        raise ServiceError(
            ErrorCode.TOKENIZER_UNAVAILABLE,
            "토큰 계수기를 사용할 수 없습니다. 서버 설정을 확인하세요.",
            {"reason": self.reason},
            retryable=False,
        )

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 미설정 상태와 이유를 돌려준다.
        인자: 없음
        반환값: configured=False인 CounterStatus
        작성 날짜: 2026/11/04
        """
        return CounterStatus(configured=False, reason=self.reason)
