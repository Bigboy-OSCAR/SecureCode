"""Source Pointer URI·작업 공간 ID·목록 cursor 형식 검사."""

import base64
import binascii
import json
import re
from dataclasses import dataclass

from securecode_context.common.errors import ErrorCode, ServiceError

_WORKSPACE = re.compile(r"ws_[A-Za-z0-9-]{8,64}")
_SOURCE_URI = re.compile(
    r"securecode://source/(?P<workspace>ws_[A-Za-z0-9-]{8,64})/"
    r"(?P<source>[A-Za-z0-9_-]{1,64})\?v=(?P<revision>[1-9][0-9]{0,9})"
)


@dataclass(frozen=True)
class SourceUri:
    """
    클래스 이름: SourceUri
    기능: 형식을 검사한 Source Pointer URI의 구성 요소. 형식만으로 권한이 생기지는 않는다.
    작성 날짜: 2026/11/10
    """

    workspace_id: str
    source_id: str
    revision: int


def check_workspace_id(workspace_id: str) -> None:
    """
    함수 이름: check_workspace_id()
    기능: 호출자 workspace ID가 계약 WorkspaceId 형식인지 확인한다.
    인자: workspace_id -> 인증된 요청의 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if not _WORKSPACE.fullmatch(workspace_id):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "작업 공간 ID 형식이 올바르지 않습니다.")


def parse_source_uri(pointer: str, workspace_id: str) -> SourceUri:
    """
    함수 이름: parse_source_uri()
    기능: 형식 → 호출자 workspace 범위 순서로 검사한다(POINTERS.md 1절 순서).
    인자: pointer -> Source Pointer URI, workspace_id -> 호출자 작업 공간
    반환값: SourceUri
    작성 날짜: 2026/11/10
    """
    check_workspace_id(workspace_id)
    match = _SOURCE_URI.fullmatch(pointer)
    if match is None:
        raise ServiceError(ErrorCode.INVALID_POINTER, "Source Pointer 형식이 올바르지 않습니다.")
    if match["workspace"] != workspace_id:
        raise ServiceError(ErrorCode.FORBIDDEN, "다른 작업 공간의 포인터입니다.")
    return SourceUri(match["workspace"], match["source"], int(match["revision"]))


def encode_cursor(workspace_id: str, after: str) -> str:
    """
    함수 이름: encode_cursor()
    기능: 목록 다음 위치를 workspace 범위에 묶은 불투명 cursor로 만든다.
    인자: workspace_id -> 범위, after -> 마지막 source_id
    반환값: base64url cursor
    작성 날짜: 2026/11/10
    """
    raw = json.dumps({"w": workspace_id, "a": after}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, workspace_id: str) -> str:
    """
    함수 이름: decode_cursor()
    기능: cursor를 풀고 같은 workspace에서 발급한 것인지 확인한다.
    인자: cursor -> 요청 cursor 또는 None, workspace_id -> 호출 범위
    반환값: 이어서 읽을 기준 source_id(처음이면 빈 문자열)
    작성 날짜: 2026/11/10
    """
    if cursor is None:
        return ""
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (binascii.Error, ValueError) as error:
        raise ServiceError(ErrorCode.INVALID_POINTER, "cursor가 올바르지 않습니다.") from error
    if (
        not isinstance(data, dict)
        or data.get("w") != workspace_id
        or not isinstance(data.get("a"), str)
    ):
        raise ServiceError(ErrorCode.INVALID_POINTER, "cursor가 올바르지 않습니다.")
    return str(data["a"])
