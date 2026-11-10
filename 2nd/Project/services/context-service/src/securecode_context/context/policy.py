"""Context Selector 순수 정책 함수(4.8). I/O 없이 정렬·선별·읽기 계획·포함 판정만 한다.

정책: docs/architecture/CONTEXT_SELECTOR.md 4~6절. 같은 입력이면 항상 같은 결과를 낸다.
"""

from dataclasses import dataclass, replace

from securecode_context.context.models import (
    Candidate,
    Fragment,
    Inclusion,
    Material,
    Omission,
    SelectorLimits,
    Span,
)

GROUP_RANK = {"explicit": 0, "current_task": 1, "r0": 2}
# R0 자동 후보 관련도 하한(3.6 live에서 0.01대 무관 후보가 들어간 것을 막는다). 같은 검색 응답 안에서만 비교한다.
R0_MIN_SCORE = 0.05
R0_RELATIVE_CUTOFF = 0.25
RUN_CREATE_ERRORS = {
    "over_budget": "BUDGET_EXCEEDED",
    "large_fragment": "BUDGET_EXCEEDED",
    "stale": "SOURCE_CHANGED",
    "unauthorized": "FORBIDDEN",
    "no_match": "NOT_FOUND",
}


@dataclass(frozen=True)
class ReadPlan:
    """
    클래스 이름: ReadPlan
    기능: 후보 하나를 읽을 구간과 토큰 상한. size_capped면 fragment 상한으로 이미 줄인 구간이다.
    작성 날짜: 2026/11/10
    """

    span: Span
    max_tokens: int
    size_capped: bool


def relevant_r0(scores: list[float]) -> list[bool]:
    """
    함수 이름: relevant_r0()
    기능: 한 R0 검색 응답의 점수 중 자동 후보로 쓸 것을 고른다. 점수가 0.05 이상이고 1위 점수의
        25% 이상인 후보만 남긴다(점수는 그 응답 안에서만 비교, 정책 4.1절).
    인자: scores -> 응답 순서의 TF-IDF 점수
    반환값: 같은 순서의 사용 여부
    작성 날짜: 2026/11/10
    """
    top = max(scores, default=0.0)
    floor = max(R0_MIN_SCORE, top * R0_RELATIVE_CUTOFF)
    return [score >= floor for score in scores]


def order_key(candidate: Candidate) -> tuple[object, ...]:
    """
    함수 이름: order_key()
    기능: 그룹 순서(explicit > current_task > r0)와 그룹 안 결정적 키를 만든다.
        explicit은 요청 위치, current_task는 최신 순번, r0는 점수 내림차순이고 동점은 candidate_id다.
    인자: candidate -> 후보
    반환값: 정렬 키
    작성 날짜: 2026/11/10
    """
    inner: tuple[object, ...]
    if candidate.origin == "r0":
        inner = (-candidate.score, candidate.candidate_id)
    else:
        inner = (candidate.rank, candidate.candidate_id)
    return (GROUP_RANK[candidate.origin], *inner)


def order_candidates(candidates: list[Candidate], limits: SelectorLimits) -> list[Candidate]:
    """
    함수 이름: order_candidates()
    기능: origin별 상한까지만 남기고 전체를 평가 순서로 정렬한다. 입력 순서는 결과에 영향이 없다.
    인자: candidates -> 해석한 후보, limits -> 상한
    반환값: 평가 순서의 후보 목록
    작성 날짜: 2026/11/10
    """
    ordered: list[Candidate] = []
    for origin, limit in limits.max_candidates.items():
        group = [candidate for candidate in candidates if candidate.origin == origin]
        ordered += sorted(group, key=order_key)[:limit]
    return sorted(ordered, key=order_key)


def skip_history_prefix(candidate: Candidate, history: list[Span]) -> Candidate:
    """
    함수 이름: skip_history_prefix()
    기능: 나눌 수 있는 자동 후보의 시작이 이력 구간 안이면 그 구간 끝으로 옮긴다(여러 turn에서 같은
        앞부분을 다시 넣지 않고 이어서 넣는다). 나눌 수 없는 후보는 그대로 둔다.
    인자: candidate -> 후보, history -> 이력 구간
    반환값: 시작을 옮긴 후보(옮길 것이 없으면 그대로)
    작성 날짜: 2026/11/10
    """
    span = candidate.span
    if span is None or not candidate.splittable:
        return candidate
    start = span.start
    moved = True
    while moved and start < span.end:
        moved = False
        for held in history:
            if held.object_key == span.object_key and held.start <= start < held.end:
                start, moved = held.end, True
    if start == span.start:
        return candidate
    return replace(candidate, span=Span(span.object_key, min(start, span.end), span.end))


def screen(
    candidate: Candidate, history: list[Span], retained: list[Fragment]
) -> Candidate | Omission:
    """
    함수 이름: screen()
    기능: 해석 상태 → 이력 중복 → 후보 중복 순서로 읽기 전에 뺄 후보를 고른다.
    인자: candidate -> 후보, history -> 이력에 원문이 실린 구간, retained -> 이미 넣은 fragment
    반환값: 누락이면 Omission, 계속 평가하면 (이력 앞부분을 건너뛴) 후보
    작성 날짜: 2026/11/10
    """
    if candidate.status != "ok":
        return Omission(candidate, candidate.status)
    if candidate.span is None:
        return Omission(candidate, "no_match")
    candidate = skip_history_prefix(candidate, history)
    span = candidate.span
    assert span is not None
    if span.start >= span.end or any(held.contains(span) for held in history):
        return Omission(candidate, "in_history")
    holder = next((kept for kept in retained if kept.material.span.contains(span)), None)
    if holder is not None:
        return Omission(candidate, "duplicate", holder.candidate.candidate_id)
    return candidate


def plan_read(candidate: Candidate, remaining: int, limits: SelectorLimits) -> ReadPlan | Omission:
    """
    함수 이름: plan_read()
    기능: 크기 상한과 남은 예산으로 읽기 계획을 세운다. 나눌 수 없는 대형 후보는 large_fragment,
        남은 예산이 없으면 over_budget이다.
    인자: candidate -> screen을 통과한 후보, remaining -> 봉투를 뺀 남은 토큰, limits -> 상한
    반환값: ReadPlan 또는 Omission
    작성 날짜: 2026/11/10
    """
    span = candidate.span
    assert span is not None
    size_capped = span.end - span.start > limits.fragment_cap_bytes
    if size_capped and not candidate.splittable:
        return Omission(candidate, "large_fragment")
    if remaining < 1:
        return Omission(candidate, "over_budget")
    end = span.start + limits.fragment_cap_bytes if size_capped else span.end
    return ReadPlan(Span(span.object_key, span.start, end), remaining, size_capped)


def classify(
    candidate: Candidate,
    plan: ReadPlan,
    material: Material,
    limits: SelectorLimits,
) -> Inclusion | Omission:
    """
    함수 이름: classify()
    기능: 실제로 읽은 결과로 포함 정도를 정한다. 토큰 상한에 걸려 잘린 경우 나눌 수 없거나
        남은 예산이 최소 부분 크기보다 작으면 over_budget이다.
    인자: candidate -> 후보, plan -> 읽기 계획, material -> 읽은 결과, limits -> 상한
    반환값: Inclusion 또는 Omission
    작성 날짜: 2026/11/10
    """
    if material.token_count > plan.max_tokens or material.token_count < 0:
        return Omission(candidate, "over_budget")
    if material.complete:
        return "partial_size" if plan.size_capped else "full"
    if not candidate.splittable or plan.max_tokens < limits.min_partial_tokens:
        return Omission(candidate, "over_budget")
    if material.span.end <= material.span.start:
        return Omission(candidate, "over_budget")
    return "partial_budget"


def run_create_error(order: list[Candidate], omissions: list[Omission]) -> str | None:
    """
    함수 이름: run_create_error()
    기능: 처리 순서상 첫 명시 누락으로 run 생성 오류를 정한다. in_history·duplicate는 오류가 아니다.
    인자: order -> 평가 순서, omissions -> 누락 목록
    반환값: ErrorCode 문자열 또는 None
    작성 날짜: 2026/11/10
    """
    by_id = {omission.candidate.candidate_id: omission for omission in omissions}
    for candidate in order:
        omission = by_id.get(candidate.candidate_id)
        if candidate.origin != "explicit" or omission is None:
            continue
        if omission.reason in RUN_CREATE_ERRORS:
            return RUN_CREATE_ERRORS[omission.reason]
    return None
