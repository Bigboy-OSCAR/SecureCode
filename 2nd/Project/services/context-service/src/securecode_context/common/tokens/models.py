"""tokens.count 결과 모델. contracts/common/token-count.schema.json의 TokenCountResult와 같다."""

from dataclasses import dataclass, replace
from enum import StrEnum

MAX_COUNT_TEXT_BYTES = 1024 * 1024


class CountMode(StrEnum):
    """
    클래스 이름: CountMode
    기능: 토큰 수의 신뢰 수준. 3.1 모델에는 공개 로컬 tokenizer가 없어 exact를 쓰지 않는다.
    작성 날짜: 2026/11/04
    """

    EXACT = "exact"
    PROVIDER_ESTIMATE = "provider_estimate"
    PROVIDER_REPORTED = "provider_reported"


@dataclass(frozen=True)
class TokenCount:
    """
    클래스 이름: TokenCount
    기능: 본문 하나의 토큰 수와 계수 방식·모델·UTF-8 크기를 담는다.
    작성 날짜: 2026/11/04
    """

    token_count: int
    count_mode: CountMode
    provider_id: str
    model_id: str
    method: str
    framing: str
    text_bytes: int
    cached: bool = False

    def as_cached(self) -> TokenCount:
        """
        함수 이름: as_cached()
        기능: 캐시에서 돌려줄 때 cached 표시만 바꾼 복사본을 만든다.
        인자: 없음
        반환값: cached=True인 TokenCount
        작성 날짜: 2026/11/04
        """
        return replace(self, cached=True)

    def to_wire(self) -> dict[str, object]:
        """
        함수 이름: to_wire()
        기능: 계약 TokenCountResult JSON 사전으로 바꾼다.
        인자: 없음
        반환값: schema_version을 포함한 snake_case 사전
        작성 날짜: 2026/11/04
        """
        return {
            "schema_version": "1",
            "token_count": self.token_count,
            "count_mode": self.count_mode.value,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "method": self.method,
            "framing": self.framing,
            "text_bytes": self.text_bytes,
            "cached": self.cached,
        }
