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
    def __init__(self, model_limit: int = 10000, reserved_output: int = 1000, safety_margin: int = 500):
        self.model_limit = model_limit
        self.reserved_output = reserved_output
        self.safety_margin = safety_margin

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(text.encode("utf-8"))

class ModelRequestGate:
    def __init__(self, token_counter: Optional[Any] = None):
        self.token_counter = token_counter or ContextBudgetCalculator()

    def check(self, candidate_refs: List[Any], max_tokens: int = 4000) -> ContextPlan:
        selected = []
        omitted = []
        current_tokens = 0
        seen_uris = set()

        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        sorted_candidates = sorted(candidate_refs, key=lambda x: not get_val(x, "explicit", False))

        for cand in sorted_candidates:
            ref = get_val(cand, "ref", cand)
            uri = get_val(ref, "uri", get_val(cand, "uri", ""))
            
            payload = get_val(cand, "payload", {})
            content = get_val(payload, "content", get_val(cand, "content", ""))

            est_tokens = get_val(cand, "estimated_tokens", None)
            if est_tokens is None:
                est_tokens = self.token_counter.estimate_tokens(content)

            if uri in seen_uris:
                omitted.append(OmittedCandidate(uri=uri, reason="DUPLICATE"))
                continue

            if current_tokens + est_tokens > max_tokens:
                omitted.append(OmittedCandidate(uri=uri, reason="BUDGET_EXCEEDED"))
                continue

            seen_uris.add(uri)
            selected.append(uri)
            current_tokens += est_tokens

        return ContextPlan(selected_uris=selected, omitted=omitted, total_tokens=current_tokens)

class ContextSelectorPolicy:
    def __init__(self, token_counter: Optional[Any] = None):
        self.gate = ModelRequestGate(token_counter)

    def select(self, candidate_refs: List[Any], available_tokens: int = 4000, max_tokens: Optional[int] = None) -> ContextPlan:
        limit = max_tokens if max_tokens is not None else available_tokens
        return self.gate.check(candidate_refs, limit)
