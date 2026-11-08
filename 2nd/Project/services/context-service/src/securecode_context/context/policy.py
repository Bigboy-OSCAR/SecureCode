STRICT_BUDGET_CAP = 32768
"""Context Selector 정책 알고리즘 구현.

작성일: 2026-11-07
"""

from typing import Any, Dict, List
from securecode_context.context.budget import ContextBudgetCalculator
from securecode_context.context.models import ContextCandidate, ContextPlan, OmittedCandidate


class ContextSelectorPolicy:
    """결정적 맥락 선별 정책 Engine."""

    def __init__(self, calculator: ContextBudgetCalculator):
        self.calculator = calculator

    def select(
        self,
        candidates: List[ContextCandidate],
        available_tokens: int
    ) -> ContextPlan:
        if available_tokens <= 0:
            omitted = [
                OmittedCandidate(
                    candidate_id=c.candidate_id,
                    reason_code="BUDGET_EXCEEDED",
                    message=f"Available budget is non-positive: {available_tokens}"
                )
                for c in candidates
            ]
            return ContextPlan(
                selected=[], fragments=[], omitted=omitted,
                used_tokens=0, remaining_tokens=available_tokens, count_mode="estimated"
            )

        # 1. 우선순위 정렬: 명시적 선택(explicit) > Score 내림차순 > Candidate ID 사전순
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (not c.explicit, -c.score, c.candidate_id)
        )

        selected: List[ContextCandidate] = []
        fragments: List[Dict[str, Any]] = []
        omitted: List[OmittedCandidate] = []
        seen_keys = set()

        current_used = 0
        for c in sorted_candidates:
            # 중복 검사 (Key: kind + uri/symbol_id)
            dedup_key = f"{c.ref.kind}:{c.ref.uri or c.ref.symbol_id}"
            if dedup_key in seen_keys:
                omitted.append(OmittedCandidate(
                    candidate_id=c.candidate_id,
                    reason_code="DUPLICATE",
                    message=f"Duplicate candidate reference: {dedup_key}"
                ))
                continue

            if current_used + c.estimated_tokens <= available_tokens:
                selected.append(c)
                seen_keys.add(dedup_key)
                current_used += c.estimated_tokens
                fragments.append({
                    "candidate_id": c.candidate_id,
                    "kind": c.ref.kind,
                    "content": c.payload.get("content", "")
                })
            else:
                omitted.append(OmittedCandidate(
                    candidate_id=c.candidate_id,
                    reason_code="BUDGET_EXCEEDED",
                    message=f"Token size ({c.estimated_tokens}) exceeds remaining budget ({available_tokens - current_used})"
                ))

        return ContextPlan(
            selected=selected,
            fragments=fragments,
            omitted=omitted,
            used_tokens=current_used,
            remaining_tokens=available_tokens - current_used,
            count_mode="estimated"
        )


class ModelRequestGate:
    def __init__(self, policy):
        self.policy = policy

    def check(self, candidate_refs, available_tokens):
        return self.policy.select(candidate_refs, available_tokens)
