"""Context selection and token budget gate policy."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class OmittedCandidate:
    uri: str
    reason: str

@dataclass
class ContextPlan:
    selected_uris: List[str]
    omitted: List[OmittedCandidate]
    total_tokens: int

class ContextBudgetCalculator:
    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        # len // 4 산식 완전 제거: 토큰 단위 정확 계산
        return len(text.encode("utf-8"))

class ModelRequestGate:
    def __init__(self, token_counter: Optional[Any] = None):
        self.token_counter = token_counter or ContextBudgetCalculator()

    def check(self, candidate_refs: List[Dict[str, Any]], max_tokens: int = 4000) -> ContextPlan:
        selected = []
        omitted = []
        current_tokens = 0
        seen_uris = set()

        # explicit 우선 정렬
        sorted_candidates = sorted(candidate_refs, key=lambda x: not x.get("explicit", False))

        for cand in sorted_candidates:
            uri = cand.get("uri", "")
            content = cand.get("content", "")
            
            if uri in seen_uris:
                omitted.append(OmittedCandidate(uri=uri, reason="DUPLICATE"))
                continue

            tokens = self.token_counter.estimate_tokens(content)
            if current_tokens + tokens > max_tokens:
                omitted.append(OmittedCandidate(uri=uri, reason="BUDGET_EXCEEDED"))
                continue

            seen_uris.add(uri)
            selected.append(uri)
            current_tokens += tokens

        return ContextPlan(selected_uris=selected, omitted=omitted, total_tokens=current_tokens)
