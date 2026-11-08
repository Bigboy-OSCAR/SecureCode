"""Context Selector 데이터 모델 및 DTO 정의.

작성일: 2026-11-07
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextCandidateRef:
    kind: str  # symbol, source, runtime
    uri: Optional[str] = None
    symbol_id: Optional[str] = None


@dataclass
class ContextCandidate:
    candidate_id: str
    ref: ContextCandidateRef
    score: float
    explicit: bool
    estimated_tokens: int
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OmittedCandidate:
    candidate_id: str
    reason_code: str  # BUDGET_EXCEEDED, FORBIDDEN, STALE, DUPLICATE
    message: str


@dataclass
class ContextPlan:
    selected: List[ContextCandidate]
    fragments: List[Dict[str, Any]]
    omitted: List[OmittedCandidate]
    used_tokens: int
    remaining_tokens: int
    count_mode: str  # estimated, exact
