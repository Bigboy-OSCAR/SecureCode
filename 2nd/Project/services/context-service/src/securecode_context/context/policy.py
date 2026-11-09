"""Context selection and token budget gate policy."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class OmittedCandidate:
    uri: str
    reason: str
    reason_code: str = ""

    def __post_init__(self):
        if not self.reason_code:
            self.reason_code = self.reason

@dataclass
class ContextPlan:
    selected_uris: List[str]
    omitted: List[OmittedCandidate]
    total_tokens: int
    selected: List[Any] = field(default_factory=list)

    @property
    def used_tokens(self) -> int:
        return self.total_tokens

class ContextBudgetCalculator:
    def __init__(self, model_limit: int = 10000, reserved_output: int = 1000, safety_margin: int = 500):
        self.model_limit = model_limit
        self.reserved_output = reserved_output
        self.safety_margin = safety_margin

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        # len/4 편법 산식 완전 제거 -> UTF-8 바이트 정률 산산식 사용
        return len(text.encode("utf-8"))

class ModelRequestGate:
    def __init__(self, token_counter: Optional[Any] = None):
        self.token_counter = token_counter or ContextBudgetCalculator()

    def check(self, candidate_refs: List[Any], max_tokens: int = 4000) -> ContextPlan:
        selected_objs = []
        selected_uris = []
        omitted = []
        current_tokens = 0
        seen_uris = set()

        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Explicit -> Score 내림차순 -> candidate_id/uri 오름차순 동점 정렬 (D7)
        sorted_candidates = sorted(
            candidate_refs,
            key=lambda x: (
                not get_val(x, "explicit", False),
                -float(get_val(x, "score", 0.0)),
                str(get_val(x, "candidate_id", get_val(get_val(x, "ref", x), "uri", "")))
            )
        )

        for cand in sorted_candidates:
            ref = get_val(cand, "ref", cand)
            uri = get_val(ref, "uri", get_val(cand, "uri", ""))
            
            payload = get_val(cand, "payload", {})
            content = get_val(payload, "content", get_val(cand, "content", ""))

            est_tokens = get_val(cand, "estimated_tokens", None)
            if est_tokens is None:
                est_tokens = self.token_counter.estimate_tokens(content)

            if uri in seen_uris:
                omitted.append(OmittedCandidate(uri=uri, reason="DUPLICATE", reason_code="DUPLICATE"))
                continue

            if current_tokens + est_tokens > max_tokens or max_tokens < 0:
                omitted.append(OmittedCandidate(uri=uri, reason="BUDGET_EXCEEDED", reason_code="BUDGET_EXCEEDED"))
                continue

            seen_uris.add(uri)
            selected_objs.append(cand)
            selected_uris.append(uri)
            current_tokens += est_tokens

        return ContextPlan(selected_uris=selected_uris, omitted=omitted, total_tokens=current_tokens, selected=selected_objs)

class ContextSelectorPolicy:
    def __init__(self, token_counter: Optional[Any] = None):
        self.gate = ModelRequestGate(token_counter)

    def select(self, candidate_refs: List[Any], available_tokens: int = 4000, max_tokens: Optional[int] = None) -> ContextPlan:
        limit = max_tokens if max_tokens is not None else available_tokens
        return self.gate.check(candidate_refs, limit)
