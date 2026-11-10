"""JSON Pointer(RFC 6901) 값 조회. 8 MiB 이하 파일만 전체를 읽어 파싱한다(부분 파싱이 아니다).

식·wildcard·재귀 탐색은 지원하지 않는다. 더 큰 JSON은 line/byte 범위로 읽는다.
"""

import json
import re

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers import limits
from securecode_context.pointers.text.io_meter import MeteredFile

_INDEX = re.compile(r"0|[1-9][0-9]*")


def _invalid(reason: str) -> ServiceError:
    """
    함수 이름: _invalid()
    기능: JSON 경로 오류를 만든다.
    인자: reason -> details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(
        ErrorCode.INVALID_SELECTOR, "JSON 경로를 찾을 수 없습니다.", {"reason": reason}
    )


def _tokens(path: str) -> list[str]:
    """
    함수 이름: _tokens()
    기능: "/a/b~1c" 형식을 참조 토큰 목록으로 푼다(~1 → /, ~0 → ~).
    인자: path -> JSON Pointer
    반환값: 토큰 목록
    작성 날짜: 2026/11/10
    """
    if not path.startswith("/") or re.search(r"~[^01]|~$", path):
        raise _invalid("invalid_json_pointer")
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def select_json(file: MeteredFile, byte_size: int, path: str) -> str:
    """
    함수 이름: select_json()
    기능: 상한 이하 JSON을 전체 파싱하고 경로 값을 UTF-8 JSON 문자열로 돌려준다.
        반환값은 원본 구간이 아닌 재직렬화 결과이므로 선택 범위(selection)를 만들 수 없다.
    인자: file -> 계측 핸들, byte_size -> 원본 크기, path -> JSON Pointer
    반환값: 값의 JSON 문자열
    작성 날짜: 2026/11/10
    """
    if byte_size > limits.MAX_JSON_PATH_BYTES:
        raise ServiceError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            "JSON 구조 조회는 8 MiB 이하만 지원합니다. 줄·바이트 범위로 읽으세요.",
            {"reason": "json_structured_limit", "limit": limits.MAX_JSON_PATH_BYTES},
        )
    file.seek(0)
    raw = file.read(byte_size + 1)
    if len(raw) != byte_size:
        raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 읽기 도중 바뀌었습니다.")
    try:
        value: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ServiceError(
            ErrorCode.PARSE_FAILED, "JSON을 해석할 수 없습니다.", {"reason": "invalid_json"}
        ) from error
    for token in _tokens(path):
        if isinstance(value, dict):
            if token not in value:
                raise _invalid("path_not_found")
            value = value[token]
        elif isinstance(value, list):
            if not _INDEX.fullmatch(token) or int(token) >= len(value):
                raise _invalid("index_out_of_range")
            value = value[int(token)]
        else:
            raise _invalid("path_not_found")
    return json.dumps(value, ensure_ascii=False)
