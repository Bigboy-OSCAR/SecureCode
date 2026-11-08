"""R0 실험의 words()와 같은 규칙으로 코드·질문을 검색 토큰으로 나눈다."""

import re

_CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
_WORD = re.compile(r"[a-z][a-z0-9_]*|\d+")


def words(text: str) -> list[str]:
    """
    함수 이름: words()
    기능: camelCase 경계를 띄우고 소문자로 바꾼 뒤 영문 식별자·숫자를 뽑는다. 밑줄 복합어는
        전체와 각 부분을 모두 남기고 한 글자 토큰은 버린다. 한글은 토큰이 되지 않는다(번역 없음).
    인자: text -> 질문 또는 후보 원문
    반환값: 등장 순서대로의 토큰 목록(중복 포함)
    작성 날짜: 2026/11/05
    """
    lowered = _CAMEL_BOUNDARY.sub(r"\1 \2", text).lower()
    tokens: list[str] = []
    for word in _WORD.findall(lowered):
        tokens.append(word)
        if "_" in word:
            tokens.extend(word.split("_"))
    return [token for token in tokens if len(token) > 1]
