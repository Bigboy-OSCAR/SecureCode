"""내부 memory:// 심볼·후보 ID를 계약의 sym_/cand_ 형식으로 바꾼다. 내부 경로는 노출하지 않는다."""

import hashlib


def _digest(value: str) -> str:
    """
    함수 이름: _digest()
    기능: 내부 ID를 고정 길이 16진수로 줄인다.
    인자: value -> 내부 ID
    반환값: 40자리 16진수
    작성 날짜: 2026/11/05
    """
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()[:40]


def symbol_id(internal_uri: str) -> str:
    """
    함수 이름: symbol_id()
    기능: 같은 심볼 URI에 항상 같은 SymbolId를 준다. revision 유효성은 별도로 검사한다.
    인자: internal_uri -> memory://symbol/... URI
    반환값: sym_ 접두사 ID
    작성 날짜: 2026/11/05
    """
    return "sym_" + _digest(internal_uri)


def candidate_id(raw_id: str) -> str:
    """
    함수 이름: candidate_id()
    기능: 같은 내부 후보 ID(atomic: 접두사 포함)에 항상 같은 CandidateId를 준다.
    인자: raw_id -> R0 후보 ID
    반환값: cand_ 접두사 ID
    작성 날짜: 2026/11/05
    """
    return "cand_" + _digest(raw_id)
