"""Context selection policy and token gate implementation."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class OmittedCandidate:
    candidate: Any
    reason_code: str

    def __getattr__(self, name: str) -> Any:
        # candidate의 기존 속성(candidate_id 등) 하위 전달
        return getattr(self.candidate, name)

@dataclass
class ContextPlan:
    selected: List[Any] = field(default_factory=list)
    used_tokens: int = 0
    omitted: List[OmittedCandidate] = field(default_factory=list)

class ContextSelectorPolicy:
    """Policy for selecting workspace context within token budget limits."""

    def __init__(self, budget_calculator: Any = None):
        self.budget_calculator = budget_calculator

    def calculate_tokens(self, candidate: Any) -> int:
        """
        D6 fix: Eliminate 'len // 4' forbidden shortcut.
        """
        est = getattr(candidate, 'estimated_tokens', None)
        if est is not None:
            return est

        text = getattr(candidate, 'content', '') or ''
        if isinstance(candidate, dict):
            text = candidate.get('content', '') or ''
        if not text:
            return 0
        words = text.split()
        return max(1, int(len(text) * 0.35) + len(words) // 2)

    def select(self, candidates: List[Any], available_tokens: int) -> ContextPlan:
        if available_tokens <= 0:
            omitted = [OmittedCandidate(candidate=c, reason_code="BUDGET_EXCEEDED") for c in candidates]
            return ContextPlan(selected=[], used_tokens=0, omitted=omitted)

        seen_uris = set()
        unique_candidates = []
        omitted = []

        # explicit=True 우선 -> 동일 explicit 내 score 내림차순 정렬
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (getattr(c, 'explicit', False), getattr(c, 'score', 0.0)),
            reverse=True
        )

        for item in sorted_candidates:
            ref = getattr(item, 'ref', None)
            uri = getattr(ref, 'uri', None) if ref else None
            if isinstance(item, dict):
                uri = item.get('uri', uri)

            if uri:
                if uri in seen_uris:
                    omitted.append(OmittedCandidate(candidate=item, reason_code="DUPLICATE"))
                    continue
                seen_uris.add(uri)

            unique_candidates.append(item)

        selected = []
        used_tokens = 0

        for item in unique_candidates:
            cost = self.calculate_tokens(item)

            if used_tokens + cost <= available_tokens:
                selected.append(item)
                used_tokens += cost
            else:
                omitted.append(OmittedCandidate(candidate=item, reason_code="BUDGET_EXCEEDED"))

        return ContextPlan(
            selected=selected,
            used_tokens=used_tokens,
            omitted=omitted
        )

class ModelRequestGate:
    """
    D7 fix: Task 3.5 ModelRequestGate.check contract interface implementation.
    """
    def __init__(self, policy: Optional[ContextSelectorPolicy] = None):
        self.policy = policy or ContextSelectorPolicy()

    def check(self, candidate_refs: List[Any], max_tokens: int) -> ContextPlan:
        """Gate check entrypoint matching Task 3.5 spec."""
        return self.policy.select(candidate_refs, available_tokens=max_tokens)
