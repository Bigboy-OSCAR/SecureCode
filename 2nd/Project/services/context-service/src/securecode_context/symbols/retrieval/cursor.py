"""검색 페이지 cursor를 revision·검색어·위치에 묶어 발급하고 검사한다."""

import base64
import hashlib
import json

from securecode_context.common.errors import ErrorCode, ServiceError


def _query_digest(query: str) -> str:
    """
    함수 이름: _query_digest()
    기능: 원문 검색어를 cursor에 넣지 않도록 짧은 해시로 바꾼다.
    인자: query -> 검색어
    반환값: 16자리 16진수
    작성 날짜: 2026/11/05
    """
    return hashlib.sha256(query.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]


def encode_cursor(index_revision: int, query: str, offset: int) -> str:
    """
    함수 이름: encode_cursor()
    기능: 다음 페이지 위치를 URL 안전 base64 cursor로 만든다.
    인자: index_revision -> revision, query -> 검색어, offset -> 다음 시작 위치
    반환값: OpaqueCursor 문자열
    작성 날짜: 2026/11/05
    """
    payload = json.dumps({"r": index_revision, "q": _query_digest(query), "o": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, index_revision: int, query: str) -> int:
    """
    함수 이름: decode_cursor()
    기능: cursor가 같은 검색어에서 나왔는지 확인하고, revision이 다르면 SOURCE_CHANGED로 거부한다.
    인자: cursor -> 클라이언트가 돌려준 값, index_revision -> 현재 revision, query -> 검색어
    반환값: 시작 위치
    작성 날짜: 2026/11/05
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        revision, digest, offset = payload["r"], payload["q"], payload["o"]
    except (ValueError, KeyError, TypeError) as error:
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "cursor가 올바르지 않습니다.") from error
    if not isinstance(offset, int) or offset < 0 or digest != _query_digest(query):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "cursor가 올바르지 않습니다.")
    if revision != index_revision:
        raise ServiceError(
            ErrorCode.SOURCE_CHANGED,
            "색인이 새 버전으로 바뀌었습니다. 다시 검색하세요.",
            {"reason": "index_revision_superseded", "index_revision": index_revision},
        )
    return offset
