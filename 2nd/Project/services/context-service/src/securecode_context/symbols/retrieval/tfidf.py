"""R0 원문 후보의 TF-IDF 벡터와 cosine 순위. 벡터는 서버 메모리에만 둔다."""

import math
from collections import Counter
from collections.abc import Mapping

from .tokens import words

type SparseVector = dict[str, float]


class TfidfRetriever:
    """
    클래스 이름: TfidfRetriever
    기능: IDF=ln((N+1)/(df+1))+1, TF=1+ln(count), L2 정규화로 후보 벡터를 미리 만들고
        질문과의 cosine으로 순위를 매긴다. 동점은 내부 후보 ID 문자열 순서로 고정한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, texts: Mapping[str, str]) -> None:
        """
        함수 이름: __init__()
        기능: 모든 후보의 문서 빈도를 세고 후보 벡터를 한 번에 준비한다.
        인자: texts -> 내부 후보 ID별 원문 텍스트
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        document_frequency: Counter[str] = Counter()
        for text in texts.values():
            document_frequency.update(set(words(text)))
        size = len(texts)
        self.idf = {
            word: math.log((1 + size) / (1 + count)) + 1
            for word, count in document_frequency.items()
        }
        self.unseen_idf = math.log(1 + size) + 1
        self.vectors = {item_id: self.vector(text) for item_id, text in texts.items()}

    @property
    def vocabulary_size(self) -> int:
        """
        함수 이름: vocabulary_size()
        기능: 준비된 어휘 수를 돌려준다.
        인자: 없음
        반환값: IDF 항목 수
        작성 날짜: 2026/11/05
        """
        return len(self.idf)

    def vector(self, text: str) -> SparseVector:
        """
        함수 이름: vector()
        기능: 텍스트를 L2 정규화한 TF-IDF 희소 벡터로 바꾼다. 처음 보는 단어는 unseen IDF를 쓴다.
        인자: text -> 질문 또는 후보 원문
        반환값: 단어별 가중치
        작성 날짜: 2026/11/05
        """
        counts = Counter(words(text))
        weights = {
            word: (1 + math.log(count)) * self.idf.get(word, self.unseen_idf)
            for word, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in weights.values())) or 1
        return {word: value / norm for word, value in weights.items()}

    def ranked(self, query: str) -> list[tuple[float, str]]:
        """
        함수 이름: ranked()
        기능: 모든 후보의 cosine 점수를 (-점수, 후보 ID) 순으로 정렬한다.
        인자: query -> 검색어
        반환값: (점수, 내부 후보 ID) 목록. 점수 0 후보도 포함한다.
        작성 날짜: 2026/11/05
        """
        query_vector = self.vector(query)
        scored = [
            (sum(weight * vector.get(word, 0) for word, weight in query_vector.items()), item_id)
            for item_id, vector in self.vectors.items()
        ]
        return sorted(scored, key=lambda pair: (-pair[0], pair[1]))
