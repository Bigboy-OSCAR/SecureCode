"""Context Selector 내부 모델(4.8). 정책은 docs/architecture/CONTEXT_SELECTOR.md 2.0을 따른다."""

from dataclasses import dataclass, field
from typing import Any, Literal

Origin = Literal["explicit", "current_task", "r0"]
Kind = Literal["symbol", "source", "runtime"]
Inclusion = Literal["full", "partial_budget", "partial_size"]
# 해석 단계(범위→버전→해석)의 결과. "ok"가 아니면 그 값이 누락 이유다.
Status = Literal["ok", "unauthorized", "stale", "no_match"]
Wire = dict[str, Any]

FRAGMENT_CAP_BYTES = 16 * 1024
MIN_PARTIAL_TOKENS = 256
MAX_CANDIDATES: dict[str, int] = {"explicit": 32, "current_task": 16, "r0": 16}
PLAN_ROWS = 64
# 응답 JSON 256 KiB(정책 9절) 중 fragment 본문(JSON 인코딩 기준)에 쓰는 몫. 나머지는 메타데이터다.
MAX_CONTENT_JSON_BYTES = 192 * 1024


@dataclass(frozen=True)
class Span:
    """
    클래스 이름: Span
    기능: 불변 대상 하나의 반열린 UTF-8 바이트 구간. 대상이 같고 구간이 포함될 때만 중복이다.
    작성 날짜: 2026/11/10
    """

    object_key: tuple[str, ...]
    start: int
    end: int

    def contains(self, other: Span) -> bool:
        """
        함수 이름: contains()
        기능: other가 같은 대상이고 이 구간 안에 있는지 판단한다(같은 구간 포함).
        인자: other -> 비교할 구간
        반환값: 포함하면 True
        작성 날짜: 2026/11/10
        """
        return (
            self.object_key == other.object_key
            and self.start <= other.start
            and other.end <= self.end
        )


@dataclass(frozen=True)
class SelectorLimits:
    """
    클래스 이름: SelectorLimits
    기능: fragment 상한·최소 부분 크기·origin별 후보 상한·응답 본문 상한(정책 9절 기본값).
    작성 날짜: 2026/11/10
    """

    fragment_cap_bytes: int = FRAGMENT_CAP_BYTES
    min_partial_tokens: int = MIN_PARTIAL_TOKENS
    max_candidates: dict[str, int] = field(default_factory=lambda: dict(MAX_CANDIDATES))
    max_content_json_bytes: int = MAX_CONTENT_JSON_BYTES


@dataclass(frozen=True)
class Candidate:
    """
    클래스 이름: Candidate
    기능: 해석까지 끝난 후보 하나. rank는 explicit 위치 또는 current_task 최신 순번이다.
        span은 해석에 성공한 후보의 대상 구간, handle은 resolver가 읽을 때 쓰는 값이다.
    작성 날짜: 2026/11/10
    """

    candidate_id: str
    origin: Origin
    kind: Kind
    ref: Wire
    score: float
    rank: int
    estimated_tokens: int
    status: Status = "ok"
    span: Span | None = None
    handle: Any = None
    # Whole symbol spans to include; history/retained symbols may be removed before reading.
    # Budget truncation never cuts a symbol or an outstanding dependency bundle.
    covered_spans: tuple[Span, ...] = ()

    @property
    def splittable(self) -> bool:
        """
        함수 이름: splittable()
        기능: 자동 Source·Runtime 포인터만 앞부분을 잘라 넣을 수 있다(정책 4.2절).
        인자: 없음
        반환값: 나눌 수 있으면 True
        작성 날짜: 2026/11/10
        """
        return self.origin != "explicit" and self.kind != "symbol"


@dataclass(frozen=True)
class Material:
    """
    클래스 이름: Material
    기능: resolver가 상한 안에서 실제로 읽은 원문과 계수, 실제 구간, 출처(AnswerCitation).
    작성 날짜: 2026/11/10
    """

    content: str
    token_count: int
    count_mode: str
    span: Span
    citation: Wire
    complete: bool


@dataclass(frozen=True)
class Fragment:
    """
    클래스 이름: Fragment
    기능: 계획에 넣은 후보와 읽은 원문, 포함 정도, 봉투 계수.
    작성 날짜: 2026/11/10
    """

    candidate: Candidate
    material: Material
    inclusion: Inclusion
    envelope_tokens: int = 0


@dataclass(frozen=True)
class Omission:
    """
    클래스 이름: Omission
    기능: 빠진 후보와 이유. duplicate면 남긴 후보 ID를 함께 둔다.
    작성 날짜: 2026/11/10
    """

    candidate: Candidate
    reason: str
    duplicate_of: str | None = None


@dataclass
class Selection:
    """
    클래스 이름: Selection
    기능: 선택 결과. order는 평가 순서, used_tokens는 fragment 계수 합, envelope_tokens는 봉투 합이다.
    작성 날짜: 2026/11/10
    """

    order: list[Candidate] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    omissions: list[Omission] = field(default_factory=list)
    used_tokens: int = 0
    envelope_tokens: int = 0
    content_json_bytes: int = 0
    count_modes: set[str] = field(default_factory=set)
