"""Task 4.8 Context Selector 및 Model Gate 단위 테스트.

작성일: 2026-11-07
"""

import pytest
from securecode_context.context.budget import ContextBudgetCalculator
from securecode_context.context.models import ContextCandidate, ContextCandidateRef
from securecode_context.context.policy import ContextSelectorPolicy


def test_context_selector_priority_and_deduplication():
    calc = ContextBudgetCalculator(model_limit=10000, reserved_output=1000, safety_margin=500)
    policy = ContextSelectorPolicy(calc)

    candidates = [
        ContextCandidate(
            candidate_id="c1",
            ref=ContextCandidateRef(kind="source", uri="securecode://source/ws1/f1"),
            score=0.5,
            explicit=False,
            estimated_tokens=2000,
            payload={"content": "c1 content"}
        ),
        ContextCandidate(
            candidate_id="c2_dup",
            ref=ContextCandidateRef(kind="source", uri="securecode://source/ws1/f1"),
            score=0.9,
            explicit=False,
            estimated_tokens=2000,
            payload={"content": "dup content"}
        ),
        ContextCandidate(
            candidate_id="c3_explicit",
            ref=ContextCandidateRef(kind="source", uri="securecode://source/ws1/f2"),
            score=0.1,
            explicit=True,
            estimated_tokens=3000,
            payload={"content": "explicit content"}
        )
    ]

    plan = policy.select(candidates, available_tokens=6000)

    # 1. Explicit 명시 선택(c3_explicit)이 가장 먼저 선택되어야 함
    assert plan.selected[0].candidate_id == "c3_explicit"
    # 2. 중복 candidates 중 1개는 DUPLICATE 사유로 제외되어야 함
    omitted_reasons = [o.reason_code for o in plan.omitted]
    assert "DUPLICATE" in omitted_reasons
    assert plan.used_tokens == 5000


def test_context_selector_negative_budget():
    calc = ContextBudgetCalculator()
    policy = ContextSelectorPolicy(calc)

    candidates = [
        ContextCandidate(
            candidate_id="c1",
            ref=ContextCandidateRef(kind="source", uri="securecode://source/ws1/f1"),
            score=0.9,
            explicit=False,
            estimated_tokens=1000
        )
    ]

    plan = policy.select(candidates, available_tokens=-100)
    assert len(plan.selected) == 0
    assert plan.omitted[0].reason_code == "BUDGET_EXCEEDED"
