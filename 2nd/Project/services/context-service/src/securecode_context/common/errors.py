"""공통 오류 코드와 서비스 예외. 코드 표는 contracts/common/error-codes.json과 계약 시험으로 맞춘다."""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """
    클래스 이름: ErrorCode
    기능: contracts/common/api-error.schema.json의 ErrorCode 값을 그대로 정의한다.
    작성 날짜: 2026/11/04
    """

    INVALID_POINTER = "INVALID_POINTER"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    INVALID_SELECTOR = "INVALID_SELECTOR"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    PARSE_FAILED = "PARSE_FAILED"
    NO_MATCH = "NO_MATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    TOKENIZER_UNAVAILABLE = "TOKENIZER_UNAVAILABLE"
    SDK_UNAVAILABLE = "SDK_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    CANCELLED = "CANCELLED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    BOOTSTRAP_CODE_INVALID = "BOOTSTRAP_CODE_INVALID"
    BOOTSTRAP_CODE_EXPIRED = "BOOTSTRAP_CODE_EXPIRED"
    ORIGIN_REJECTED = "ORIGIN_REJECTED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RUN_ALREADY_ACTIVE = "RUN_ALREADY_ACTIVE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_DIGEST_MISMATCH = "APPROVAL_DIGEST_MISMATCH"
    APPROVAL_ALREADY_DECIDED = "APPROVAL_ALREADY_DECIDED"
    PROTECTION_UNAVAILABLE = "PROTECTION_UNAVAILABLE"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorRule:
    """
    클래스 이름: ErrorRule
    기능: 오류 코드 하나의 HTTP 상태와 기본 재시도 가능 여부를 담는다.
    작성 날짜: 2026/11/04
    """

    http_status: int
    retryable: bool


ERROR_RULES: dict[ErrorCode, ErrorRule] = {
    ErrorCode.INVALID_POINTER: ErrorRule(400, False),
    ErrorCode.NOT_FOUND: ErrorRule(404, False),
    ErrorCode.EXPIRED: ErrorRule(410, False),
    ErrorCode.FORBIDDEN: ErrorRule(403, False),
    ErrorCode.SOURCE_CHANGED: ErrorRule(409, False),
    ErrorCode.INVALID_SELECTOR: ErrorRule(400, False),
    ErrorCode.UNSUPPORTED_FORMAT: ErrorRule(415, False),
    ErrorCode.UNSUPPORTED_LANGUAGE: ErrorRule(422, False),
    ErrorCode.PARSE_FAILED: ErrorRule(422, False),
    ErrorCode.NO_MATCH: ErrorRule(200, False),
    ErrorCode.BUDGET_EXCEEDED: ErrorRule(413, False),
    ErrorCode.TOKENIZER_UNAVAILABLE: ErrorRule(503, True),
    ErrorCode.SDK_UNAVAILABLE: ErrorRule(503, True),
    ErrorCode.PROVIDER_ERROR: ErrorRule(502, True),
    ErrorCode.APPROVAL_REJECTED: ErrorRule(409, False),
    ErrorCode.CANCELLED: ErrorRule(409, False),
    ErrorCode.UNAUTHENTICATED: ErrorRule(401, False),
    ErrorCode.BOOTSTRAP_CODE_INVALID: ErrorRule(401, False),
    ErrorCode.BOOTSTRAP_CODE_EXPIRED: ErrorRule(401, False),
    ErrorCode.ORIGIN_REJECTED: ErrorRule(403, False),
    ErrorCode.VALIDATION_FAILED: ErrorRule(422, False),
    ErrorCode.PAYLOAD_TOO_LARGE: ErrorRule(413, False),
    ErrorCode.QUOTA_EXCEEDED: ErrorRule(507, False),
    ErrorCode.RUN_ALREADY_ACTIVE: ErrorRule(409, True),
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorRule(409, False),
    ErrorCode.APPROVAL_EXPIRED: ErrorRule(410, False),
    ErrorCode.APPROVAL_DIGEST_MISMATCH: ErrorRule(409, False),
    ErrorCode.APPROVAL_ALREADY_DECIDED: ErrorRule(409, False),
    ErrorCode.PROTECTION_UNAVAILABLE: ErrorRule(503, True),
    ErrorCode.INDEX_NOT_READY: ErrorRule(409, True),
    ErrorCode.RATE_LIMITED: ErrorRule(429, True),
    ErrorCode.SERVICE_UNAVAILABLE: ErrorRule(503, True),
    ErrorCode.NOT_IMPLEMENTED: ErrorRule(501, False),
    ErrorCode.INTERNAL_ERROR: ErrorRule(500, False),
}

ErrorDetailValue = str | int | float | bool | None


class ServiceError(Exception):
    """
    클래스 이름: ServiceError
    기능: 계약된 ApiError로 변환되는 서비스 예외. 메시지는 사용자에게 보여도 안전해야 한다.
    작성 날짜: 2026/11/04
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, ErrorDetailValue] | None = None,
        retryable: bool | None = None,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 오류 코드·메시지·세부 정보·재시도 여부를 저장한다.
        인자: code -> 계약 오류 코드
            message -> 사용자에게 보여도 되는 500자 이하 메시지
            details -> 경로·키·원문이 없는 스칼라 값 사전
            retryable -> None이면 오류 코드의 기본값을 쓴다
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = ERROR_RULES[code].retryable if retryable is None else retryable

    @property
    def http_status(self) -> int:
        """
        함수 이름: http_status()
        기능: 오류 코드에 정해진 HTTP 상태를 돌려준다.
        인자: 없음
        반환값: HTTP 상태 코드
        작성 날짜: 2026/11/04
        """
        return ERROR_RULES[self.code].http_status
