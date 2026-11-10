"""Selection을 계약 ContextPreviewPlan으로 바꾼다(4.8). 계획 행은 각각 64개까지다."""

import hashlib
import json

from securecode_context.context.budget import CountedCosts, plan_count_mode
from securecode_context.context.models import PLAN_ROWS, Candidate, Omission, Selection, Wire
from securecode_context.context.pointer_resolvers import PointerTarget, selection_wire


def _confirmed_ref(candidate: Candidate) -> Wire:
    """
    함수 이름: _confirmed_ref()
    기능: 누락 행에 넣을 ExplicitContextRef. 포인터는 해석한 대상 구간 selection을 붙인다.
    인자: candidate -> 후보
    반환값: ContextRef 사전
    작성 날짜: 2026/11/10
    """
    if candidate.kind == "symbol" or "selection" in candidate.ref:
        return dict(candidate.ref)
    target = candidate.handle
    assert isinstance(target, PointerTarget) and candidate.span is not None
    ref: Wire = {"kind": candidate.kind, "pointer": candidate.ref["pointer"]}
    ref["selection"] = selection_wire(target, candidate.span.start, candidate.span.end)
    return ref


def _omission_row(omission: Omission) -> Wire:
    """
    함수 이름: _omission_row()
    기능: 누락 한 행. 명시 선택과 duplicate는 확인된 ref를 함께 넣는다.
    인자: omission -> 누락
    반환값: ContextPreviewOmission 사전
    작성 날짜: 2026/11/10
    """
    candidate = omission.candidate
    row: Wire = {
        "candidate_id": candidate.candidate_id,
        "origin": candidate.origin,
        "reason": omission.reason,
    }
    if candidate.origin == "explicit":
        row["ref"] = dict(candidate.ref)
    elif omission.reason == "duplicate":
        row["ref"] = _confirmed_ref(candidate)
    if omission.duplicate_of is not None:
        row["duplicate_of"] = omission.duplicate_of
    return row


def _candidate_row(candidate: Candidate) -> Wire:
    """
    함수 이름: _candidate_row()
    기능: 선택한 후보 한 행(ContextPreviewCandidate).
    인자: candidate -> 후보
    반환값: 사전
    작성 날짜: 2026/11/10
    """
    return {
        "candidate_id": candidate.candidate_id,
        "ref": dict(candidate.ref),
        "score": candidate.score,
        "explicit": candidate.origin == "explicit",
        "estimated_tokens": candidate.estimated_tokens,
        "origin": candidate.origin,
    }


def plan_wire(selection: Selection, costs: CountedCosts, index_revision: int) -> Wire:
    """
    함수 이름: plan_wire()
    기능: ContextPreviewPlan을 만들고 digest를 붙인다. budget_tokens는 봉투를 뺀 값이라 used 이상이다.
    인자: selection -> 선택 결과, costs -> 센 고정 비용, index_revision -> 요청 revision
    반환값: ContextPreviewPlan 사전
    작성 날짜: 2026/11/10
    """
    fragments = selection.fragments[:PLAN_ROWS]
    omissions = selection.omissions
    budget_tokens = costs.base_budget() - selection.envelope_tokens
    plan: Wire = {
        "schema_version": "1",
        "index_revision": index_revision,
        "omissions_truncated": len(omissions) > PLAN_ROWS,
        "selected": [_candidate_row(fragment.candidate) for fragment in fragments],
        "fragments": [
            {
                "candidate_id": fragment.candidate.candidate_id,
                "ref": dict(fragment.candidate.ref),
                "content": fragment.material.content,
                "token_count": fragment.material.token_count,
                "inclusion": fragment.inclusion,
                "provenance": fragment.material.citation,
            }
            for fragment in fragments
        ],
        "omitted": [_omission_row(omission) for omission in omissions[:PLAN_ROWS]],
        "budget": {
            "budget_tokens": budget_tokens,
            "used_tokens": selection.used_tokens,
            "count_mode": plan_count_mode(set(costs.count_modes) | selection.count_modes),
            "costs": costs.to_wire(selection.envelope_tokens),
        },
    }
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    plan["preview_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return plan
