"""한 revision의 TF-IDF 벡터와 후보 메타데이터를 서버 메모리에 준비한다."""

from collections.abc import Mapping
from dataclasses import dataclass

from ..graph import RawCandidate, SourceNode
from ..public_ids import candidate_id
from .candidates import CandidateInfo, describe_candidate
from .tfidf import TfidfRetriever


@dataclass(frozen=True)
class PreparedRetrieval:
    """
    클래스 이름: PreparedRetrieval
    기능: revision 번호, 준비된 벡터, 내부·공개 후보 ID 색인을 묶는다. 모델로 보내지 않는다.
    작성 날짜: 2026/11/05
    """

    index_revision: int
    retriever: TfidfRetriever
    infos: dict[str, CandidateInfo]
    raw_by_public_id: dict[str, str]


def prepare_retrieval(
    index_revision: int, nodes: Mapping[str, SourceNode], raw: list[RawCandidate]
) -> PreparedRetrieval:
    """
    함수 이름: prepare_retrieval()
    기능: 모든 R0 후보(atomic과 깊이 3 bundle)의 벡터와 깊이·경계 정보를 만든다.
    인자: index_revision -> revision, nodes -> 그래프, raw -> 후보
    반환값: PreparedRetrieval
    작성 날짜: 2026/11/05
    """
    retriever = TfidfRetriever({candidate["id"]: candidate["text"] for candidate in raw})
    infos = {candidate["id"]: describe_candidate(nodes, candidate) for candidate in raw}
    public = {candidate_id(raw_id): raw_id for raw_id in infos}
    if len(public) != len(infos):
        raise ValueError("candidate id collision")
    return PreparedRetrieval(index_revision, retriever, infos, public)
