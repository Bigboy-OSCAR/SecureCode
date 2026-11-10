"""Context Selector 실행(4.8): 순수 정책 함수와 resolver 읽기를 순서대로 엮는다.

각 후보는 정렬 순서대로 한 번만 평가한다: 선별 → 읽기 계획 → 상한 안 읽기 → 실계수로 포함 판정.
남은 예산은 이미 넣은 fragment의 실제 계수와 봉투 계수로만 줄어든다.
"""

import json
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.context.models import (
    Candidate,
    Fragment,
    Material,
    Omission,
    Selection,
    SelectorLimits,
    Span,
)
from securecode_context.context.policy import classify, order_candidates, plan_read, screen

# resolver 오류 → 후보 누락 이유(정책 6절). 여기 없는 오류는 요청 전체 오류로 올린다.
_REASONS = {
    ErrorCode.FORBIDDEN: "unauthorized",
    ErrorCode.SOURCE_CHANGED: "stale",
    ErrorCode.EXPIRED: "stale",
    ErrorCode.INDEX_NOT_READY: "stale",
    ErrorCode.NOT_FOUND: "no_match",
    ErrorCode.INVALID_POINTER: "no_match",
    ErrorCode.INVALID_SELECTOR: "no_match",
    ErrorCode.BUDGET_EXCEEDED: "over_budget",
}


class MaterialReader(Protocol):
    """
    클래스 이름: MaterialReader
    기능: 후보 종류별 resolver 묶음. 읽기는 항상 구간·토큰 상한 안에서만 한다.
    작성 날짜: 2026/11/10
    """

    def envelope_tokens(self, candidate: Candidate) -> int:
        """
        함수 이름: envelope_tokens()
        기능: 이 후보 fragment를 감쌀 context block 봉투(빈 본문)의 토큰 수.
        인자: candidate -> 후보
        반환값: 토큰 수
        작성 날짜: 2026/11/10
        """
        ...

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: span 구간을 max_tokens 안에서 앞에서부터 읽고 실제로 센다.
        인자: candidate -> 후보, span -> 읽을 구간, max_tokens -> 토큰 상한
        반환값: Material(complete는 span 끝까지 읽었는지)
        작성 날짜: 2026/11/10
        """
        ...


def reason_for(error: ServiceError) -> str | None:
    """
    함수 이름: reason_for()
    기능: resolver 오류를 후보 누락 이유로 바꾼다. 계수기·서비스 장애는 None(요청 오류)이다.
    인자: error -> resolver가 던진 오류
    반환값: 누락 이유 또는 None
    작성 날짜: 2026/11/10
    """
    return _REASONS.get(error.code)


def content_json_bytes(content: str) -> int:
    """
    함수 이름: content_json_bytes()
    기능: 응답 JSON에 들어갈 본문 문자열의 바이트 수(escape 포함)를 센다.
    인자: content -> fragment 본문
    반환값: 바이트 수
    작성 날짜: 2026/11/10
    """
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8"))


def select(
    candidates: list[Candidate],
    history: list[Span],
    budget_tokens: int,
    limits: SelectorLimits,
    reader: MaterialReader,
) -> Selection:
    """
    함수 이름: select()
    기능: 후보를 정렬하고 하나씩 선별·읽기·포함 판정해 Selection을 만든다.
    인자: candidates -> 해석한 후보, history -> 이력 구간, budget_tokens -> 봉투 전 검색 자료 예산,
        limits -> 상한, reader -> resolver 묶음
    반환값: Selection
    작성 날짜: 2026/11/10
    """
    selection = Selection(order=order_candidates(candidates, limits))
    for candidate in selection.order:
        result = _evaluate(candidate, history, budget_tokens, limits, reader, selection)
        if isinstance(result, Omission):
            selection.omissions.append(result)
            continue
        size = content_json_bytes(result.material.content)
        if selection.content_json_bytes + size > limits.max_content_json_bytes:
            selection.omissions.append(Omission(candidate, "over_budget"))
            continue
        selection.content_json_bytes += size
        selection.fragments.append(result)
        selection.used_tokens += result.material.token_count
        selection.envelope_tokens += result.envelope_tokens
        selection.count_modes.add(result.material.count_mode)
    return selection


def _evaluate(
    candidate: Candidate,
    history: list[Span],
    budget_tokens: int,
    limits: SelectorLimits,
    reader: MaterialReader,
    selection: Selection,
) -> Fragment | Omission:
    """
    함수 이름: _evaluate()
    기능: 후보 하나를 정책 순서(상태→이력→중복→크기→예산→읽기)로 평가한다.
    인자: candidate -> 후보, history -> 이력 구간, budget_tokens -> 예산, limits -> 상한,
        reader -> resolver, selection -> 지금까지의 결과
    반환값: Fragment 또는 Omission
    작성 날짜: 2026/11/10
    """
    screened = screen(candidate, history, selection.fragments)
    if isinstance(screened, Omission):
        return screened
    candidate = screened
    try:
        envelope = reader.envelope_tokens(candidate)
        remaining = budget_tokens - selection.used_tokens - selection.envelope_tokens - envelope
        plan = plan_read(candidate, remaining, limits)
        if isinstance(plan, Omission):
            return plan
        material = reader.read(candidate, plan.span, plan.max_tokens)
    except ServiceError as error:
        reason = reason_for(error)
        if reason is None:
            raise
        return Omission(candidate, reason)
    verdict = classify(candidate, plan, material, limits)
    if isinstance(verdict, Omission):
        return verdict
    return Fragment(candidate, material, verdict, envelope)
