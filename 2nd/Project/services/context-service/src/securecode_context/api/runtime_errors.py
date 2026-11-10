"""Runtime 저장소 오류를 계약 ServiceError(ApiError)로 옮긴다."""

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.models.runtime import RuntimeStoreError


def translate(error: RuntimeStoreError) -> ServiceError:
    """
    함수 이름: translate()
    기능: 저장소 오류 code를 공용 ErrorCode로, reason을 details.reason으로 옮긴다.
        알 수 없는 code는 내부 오류로 처리한다.
    인자: error -> Runtime 저장소 오류
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    try:
        code = ErrorCode(error.code)
    except ValueError:
        code = ErrorCode.INTERNAL_ERROR
    details: dict[str, str | int | float | bool | None] = (
        {"reason": error.reason} if error.reason else {}
    )
    return ServiceError(code, str(error), details)
