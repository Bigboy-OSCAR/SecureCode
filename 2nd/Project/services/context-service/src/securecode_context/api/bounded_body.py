"""상한이 있는 JSON 본문 읽기. 큰 내부 요청(gate 계수·context.select)이 메모리를 넘지 않게 한다."""

from fastapi import Request

from securecode_context.common.errors import ErrorCode, ServiceError


async def read_bounded_json(request: Request, max_bytes: int) -> bytes:
    """
    함수 이름: read_bounded_json()
    기능: JSON 미디어 형식을 확인하고 본문을 max_bytes까지만 읽는다.
    인자: request -> 인증된 요청, max_bytes -> 본문 상한
    반환값: 본문 바이트
    작성 날짜: 2026/11/10
    """
    media_type = (
        request.headers.get("content-type", "application/json").split(";", 1)[0].strip().lower()
    )
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "JSON 본문이 필요합니다.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > max_bytes:
            raise ServiceError(
                ErrorCode.PAYLOAD_TOO_LARGE, "요청 본문이 너무 큽니다.", {"max_bytes": max_bytes}
            )
        data.extend(chunk)
    return bytes(data)
