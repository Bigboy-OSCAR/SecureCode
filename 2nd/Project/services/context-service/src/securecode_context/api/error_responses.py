"""ServiceError와 프레임워크 오류를 계약 ErrorResponse로 바꾼다. 입력 원문·경로·스택은 응답에 넣지 않는다."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from securecode_context.common.errors import ErrorCode, ServiceError

LOGGER = logging.getLogger("securecode_context.api")


def build_error_response(error: ServiceError, request_id: str) -> JSONResponse:
    """
    함수 이름: build_error_response()
    기능: ServiceError를 ErrorResponse JSON과 정해진 HTTP 상태로 만든다.
    인자: error -> 서비스 오류
        request_id -> 요청 상관 ID
    반환값: JSONResponse
    작성 날짜: 2026/11/04
    """
    body: dict[str, object] = {
        "code": error.code.value,
        "message": error.message[:500],
        "retryable": error.retryable,
        "request_id": request_id,
    }
    if error.details:
        body["details"] = error.details
    return JSONResponse(
        {"schema_version": "1", "error": body},
        status_code=error.http_status,
        headers={"X-Request-Id": request_id},
    )


def _request_id_of(request: Request) -> str:
    """
    함수 이름: _request_id_of()
    기능: 미들웨어가 붙인 request_id를 읽는다.
    인자: request -> 현재 요청
    반환값: request_id 문자열
    작성 날짜: 2026/11/04
    """
    return str(getattr(request.state, "request_id", "req_unassigned0"))


async def handle_service_error(request: Request, error: Exception) -> JSONResponse:
    """
    함수 이름: handle_service_error()
    기능: 처리기에서 던진 ServiceError를 응답으로 바꾼다.
    인자: request -> 현재 요청
        error -> ServiceError
    반환값: JSONResponse
    작성 날짜: 2026/11/04
    """
    if not isinstance(error, ServiceError):
        raise error
    return build_error_response(error, _request_id_of(request))


async def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    """
    함수 이름: handle_validation_error()
    기능: 본문 검증 실패를 VALIDATION_FAILED로 바꾼다. FastAPI 기본 응답과 달리 입력값을 되돌려 주지 않는다.
    인자: request -> 현재 요청
        error -> RequestValidationError
    반환값: JSONResponse
    작성 날짜: 2026/11/04
    """
    if not isinstance(error, RequestValidationError):
        raise error
    # Unknown JSON keys and route values can themselves contain private input.
    service_error = ServiceError(ErrorCode.VALIDATION_FAILED, "요청 형식이 올바르지 않습니다.")
    return build_error_response(service_error, _request_id_of(request))


async def handle_http_error(request: Request, error: Exception) -> JSONResponse:
    """
    함수 이름: handle_http_error()
    기능: 라우팅 404/405를 계약 오류로 바꾼다.
    인자: request -> 현재 요청
        error -> StarletteHTTPException
    반환값: JSONResponse
    작성 날짜: 2026/11/04
    """
    if not isinstance(error, StarletteHTTPException):
        raise error
    code = ErrorCode.NOT_FOUND if error.status_code in (404, 405) else ErrorCode.INTERNAL_ERROR
    message = (
        "요청한 경로가 없습니다." if code is ErrorCode.NOT_FOUND else "서버 오류가 발생했습니다."
    )
    return build_error_response(ServiceError(code, message), _request_id_of(request))


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """
    함수 이름: handle_unexpected_error()
    기능: 예상하지 못한 예외를 INTERNAL_ERROR로 바꾸고 종류만 기록한다(메시지는 redaction 필터를 거친다).
    인자: request -> 현재 요청
        error -> 처리되지 않은 예외
    반환값: JSONResponse
    작성 날짜: 2026/11/04
    """
    request_id = _request_id_of(request)
    LOGGER.error("unhandled %s request_id=%s", type(error).__name__, request_id)
    service_error = ServiceError(ErrorCode.INTERNAL_ERROR, "서버 오류가 발생했습니다.")
    return build_error_response(service_error, request_id)


def register_error_handlers(app: FastAPI) -> None:
    """
    함수 이름: register_error_handlers()
    기능: 위 처리기들을 앱에 등록한다.
    인자: app -> FastAPI 앱
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    app.add_exception_handler(ServiceError, handle_service_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
