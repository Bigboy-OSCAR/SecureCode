"""이어 읽기 cursor 공용 형식. 범위(scope)·내용 버전(version)·요청 해시에 묶는다(POINTERS.md 5절).

다른 범위·요청이면 INVALID_POINTER, 같은 대상이지만 내용 버전이 다르면 SOURCE_CHANGED다.
"""

import base64
import binascii
import hashlib
import json

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.text.models import CursorState


def request_digest(operation: str, request_shape: object) -> str:
    """
    함수 이름: request_digest()
    기능: cursor를 만든 요청(연산·selector·검색어)의 짧은 해시를 만든다.
    인자: operation -> read/search, request_shape -> JSON으로 표현 가능한 요청 내용
    반환값: 16자리 hex
    작성 날짜: 2026/11/10
    """
    text = json.dumps([operation, request_shape], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def encode_state(scope: list[str], version: list[object], digest: str, state: CursorState) -> str:
    """
    함수 이름: encode_state()
    기능: 범위·버전·요청 해시와 다음 위치를 불투명 cursor로 만든다.
    인자: scope -> 범위 식별자, version -> 내용 버전, digest -> 요청 해시, state -> 다음 위치
    반환값: base64url cursor(512자 이하)
    작성 날짜: 2026/11/10
    """
    payload = {
        "s": scope,
        "v": version,
        "q": digest,
        "o": state.offset,
        "e": state.end,
        "l": state.line,
        "j": state.in_json,
        "c": state.clipped,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_state(
    cursor: str, scope: list[str], version: list[object], digest: str, byte_size: int
) -> CursorState:
    """
    함수 이름: decode_state()
    기능: cursor를 풀고 범위·요청·버전·위치를 확인한다.
    인자: cursor -> 요청 cursor, scope/version/digest -> 현재 요청 값, byte_size -> 원본 크기
    반환값: CursorState
    작성 날짜: 2026/11/10
    """
    invalid = ServiceError(ErrorCode.INVALID_POINTER, "cursor가 이 요청에 속하지 않습니다.")
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (binascii.Error, ValueError) as error:
        raise invalid from error
    if not isinstance(data, dict) or (data.get("s"), data.get("q")) != (scope, digest):
        raise invalid
    if data.get("v") != version:
        raise ServiceError(ErrorCode.SOURCE_CHANGED, "cursor를 만든 뒤 원본이 바뀌었습니다.")
    values = [data.get("o"), data.get("e"), data.get("l")]
    numbers = [value for value in values if type(value) is int and value >= 0]
    if len(numbers) != 3:
        raise invalid
    offset, end, line = numbers
    in_json = data.get("j") is True
    if offset > end or line < 1 or (not in_json and end > byte_size):
        raise invalid
    return CursorState(offset, end, line, in_json, data.get("c") is True)
