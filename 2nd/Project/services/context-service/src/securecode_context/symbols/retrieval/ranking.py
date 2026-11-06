"""TF-IDF 순위에서 0점과 이미 덮인 원문 범위를 빼고 검색 후보 상한을 적용한다."""

from collections.abc import Mapping
from dataclasses import dataclass

from .candidates import CandidateInfo, FragmentKey
from .tfidf import TfidfRetriever
from .tokens import words

MAX_SEARCH_CANDIDATES = 100


@dataclass(frozen=True)
class RankedCandidate:
    """
    클래스 이름: RankedCandidate
    기능: cosine 점수와 후보 정보를 묶는다.
    작성 날짜: 2026/11/05
    """

    score: float
    info: CandidateInfo


def has_query_tokens(query: str) -> bool:
    """
    함수 이름: has_query_tokens()
    기능: 검색어에서 R0 토큰을 하나라도 추출할 수 있는지 확인한다(한글만 있으면 False).
    인자: query -> 검색어
    반환값: 토큰 존재 여부
    작성 날짜: 2026/11/05
    """
    return bool(words(query))


def rank_candidates(
    retriever: TfidfRetriever, infos: Mapping[str, CandidateInfo], query: str
) -> list[RankedCandidate]:
    """
    함수 이름: rank_candidates()
    기능: 점수 0 후보는 버린다(실험의 0점 채움과 다름). 앞 순위 후보들이 이미 모든 원문 범위
        (파일 해시+바이트 범위)를 포함한 후보는 R0 pack의 중복 제외처럼 뺀다. 최대 100개다.
    인자: retriever -> 준비된 TF-IDF, infos -> 내부 후보 ID별 정보, query -> 검색어
    반환값: 점수 내림차순·내부 ID 오름차순의 RankedCandidate 목록
    작성 날짜: 2026/11/05
    """
    covered: set[FragmentKey] = set()
    ranked: list[RankedCandidate] = []
    for score, raw_id in retriever.ranked(query):
        if score <= 0 or len(ranked) == MAX_SEARCH_CANDIDATES:
            break
        info = infos[raw_id]
        if info.fragment_keys <= covered:
            continue
        covered.update(info.fragment_keys)
        ranked.append(RankedCandidate(min(score, 1.0), info))
    return ranked
