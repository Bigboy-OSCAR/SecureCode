"""내부 API 공통 미들웨어: request_id 부여, 브라우저 Origin 거절, bearer 내부 토큰 검사."""

import hmac
import re
import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from securecode_context.api.error_responses import build_error_response
from securecode_context.common.errors import ErrorCode, ServiceError

REQUEST_ID_PATTERN = re.compile(r"^req_[A-Za-z0-9-]{8,64}$")
RequestHandler = Callable[[Request], Awaitable[Response]]


def resolve_request_id(request: Request) -> str:
    """
    함수 이름: resolve_request_id()
    기능: host가 보낸 X-Request-Id가 계약 형식이면 이어 쓰고 아니면 새로 만든다.
    인자: request -> 현재 요청
    반환값: req_ 접두사의 request_id
    작성 날짜: 2026/11/04
    """
    incoming = request.headers.get("x-request-id", "")
    if REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return f"req_{secrets.token_hex(12)}"


def check_internal_access(request: Request, internal_token: str) -> None:
    """
    함수 이름: check_internal_access()
    기능: 브라우저 요청(Origin 헤더)을 거절하고 Authorization bearer 토큰을 상수 시간으로 비교한다.
    인자: request -> 현재 요청
        internal_token -> launcher가 기동마다 만든 내부 토큰
    반환값: 없음(실패 시 ServiceError)
    작성 날짜: 2026/11/04
    """
    if request.headers.get("origin") is not None:
        raise ServiceError(
            ErrorCode.ORIGIN_REJECTED, "브라우저는 내부 서비스를 호출할 수 없습니다."
        )

    authorization = request.headers.get("authorization", "")
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        presented.encode(), internal_token.encode()
    ):
        raise ServiceError(ErrorCode.UNAUTHENTICATED, "내부 서비스 인증에 실패했습니다.")


def install_middleware(app: FastAPI, internal_token: str) -> None:
    """
    함수 이름: install_middleware()
    기능: 모든 요청(404 포함)에 request_id와 내부 인증을 적용하는 미들웨어를 등록한다.
    인자: app -> FastAPI 앱
        internal_token -> 내부 서비스 토큰
    반환값: 없음
    작성 날짜: 2026/11/04
    """

    @app.middleware("http")
    async def guard_request(request: Request, call_next: RequestHandler) -> Response:
        """
        함수 이름: guard_request()
        기능: request_id를 정하고 인증에 실패하면 ErrorResponse를 바로 돌려준다.
        인자: request -> 현재 요청
            call_next -> 다음 처리기
        반환값: 응답(X-Request-Id 헤더 포함)
        작성 날짜: 2026/11/04
        """
        request_id = resolve_request_id(request)
        request.state.request_id = request_id
        try:
            check_internal_access(request, internal_token)
        except ServiceError as error:
            response: Response = build_error_response(error, request_id)
        else:
            response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
