"""검색 공용 규칙: 한글을 보존하는 검색어 형태와, 결과를 bytes/tokens 상한 안으로 줄이는 규칙."""

import unicodedata

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.limits import MAX_QUERY_CHARS, MAX_SEARCH_LIMIT
from securecode_context.pointers.text.caps import check_caps, count_tokens
from securecode_context.pointers.text.models import SearchMatch

MAX_TOKEN_ROUNDS = 8


def check_search(query: str, limit: int, max_bytes: int, max_tokens: int) -> None:
    """
    함수 이름: check_search()
    기능: 검색어 길이·결과 수·상한을 확인한다.
    인자: query -> 검색어, limit -> 최대 일치 수, max_bytes/max_tokens -> 상한
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    check_caps(max_bytes, max_tokens)
    if not 1 <= len(query) <= MAX_QUERY_CHARS or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED,
            "검색어 또는 limit이 범위를 벗어났습니다.",
            {"reason": "query_range"},
        )


def query_patterns(query: str) -> list[bytes]:
    """
    함수 이름: query_patterns()
    기능: 검색어의 NFC·NFD UTF-8 형태를 만든다. 문자를 지우거나 대소문자를 바꾸지 않는다.
    인자: query -> 검색어
    반환값: 서로 다른 바이트 패턴 목록
    작성 날짜: 2026/11/10
    """
    forms = [unicodedata.normalize("NFC", query), unicodedata.normalize("NFD", query)]
    return list(dict.fromkeys(form.encode("utf-8") for form in forms))


def fit_matches(
    matches: list[SearchMatch],
    resume: tuple[int, int] | None,
    caps: tuple[int, int],
    counter: TokenCounter,
) -> tuple[list[SearchMatch], tuple[int, int] | None, int, str]:
    """
    함수 이름: fit_matches()
    기능: 미리보기 합계를 bytes·tokens 상한 안으로 줄인다. 뺀 첫 일치에서 다음 검색을 잇는다.
    인자: matches -> 찾은 일치, resume -> scan이 준 다음 위치, caps -> (max_bytes, max_tokens),
        counter -> TokenCounter
    반환값: 남긴 일치, 다음 위치(오프셋, 줄), 토큰 수, count_mode
    작성 날짜: 2026/11/10
    """
    max_bytes, max_tokens = caps
    used = 0
    keep = 0
    for match in matches:
        used += len(match.content.encode("utf-8")) + 1
        if used > max_bytes:
            break
        keep += 1
    tokens, mode = 0, "exact"
    for _ in range(MAX_TOKEN_ROUNDS):
        tokens, mode = count_tokens(counter, "\n".join(m.content for m in matches[:keep]))
        if tokens <= max_tokens:
            break
        keep = min(keep - 1, int(keep * max_tokens / tokens))
    else:
        keep = 0
    if keep == 0 and matches:
        raise ServiceError(
            ErrorCode.BUDGET_EXCEEDED, "상한이 너무 작습니다.", {"reason": "cap_too_small"}
        )
    if keep < len(matches):
        dropped = matches[keep]
        return matches[:keep], (dropped.byte_offset, dropped.line), tokens, mode
    return matches, resume, tokens, mode
