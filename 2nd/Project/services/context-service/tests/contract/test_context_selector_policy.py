"""4.7 Context Selector 정책 시나리오 검증.

contracts/context/selector-scenarios.json의 손계산 기대값을 정책 문서(CONTEXT_SELECTOR.md)대로 다시 계산해 비교하고,
기대값으로 만든 ContextPreviewPlan이 계약 스키마와 산술·참조 불변식을 지키는지 확인한다.
여기 있는 선택 함수는 시험용 기준(oracle)이며 제품 구현은 4.8이다.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from support.helpers import CONTRACTS_ROOT, ContractCheck

SCENARIOS = json.loads((CONTRACTS_ROOT / "context" / "selector-scenarios.json").read_text("utf-8"))
PLAN_REF = "context/context.schema.json#/definitions/ContextPreviewPlan"
GROUP_RANK = {"explicit": 0, "current_task": 1, "r0": 2}
RUN_CREATE_ERRORS = {
    "over_budget": "BUDGET_EXCEEDED",
    "large_fragment": "BUDGET_EXCEEDED",
    "stale": "SOURCE_CHANGED",
    "unauthorized": "FORBIDDEN",
    "no_match": "NOT_FOUND",
}
Row = dict[str, Any]


def _costs(scenario: Row) -> Row:
    """
    함수 이름: _costs()
    기능: 기본 비용에 시나리오 덮어쓰기를 적용한다.
    인자: scenario -> 시나리오
    반환값: ContextBudgetCosts
    작성 날짜: 2026/11/10
    """
    return {**SCENARIOS["base_costs"], **scenario.get("costs", {})}


def _order_key(candidate: Row) -> tuple[Any, ...]:
    """
    함수 이름: _order_key()
    기능: 그룹(explicit > current_task > r0) 안의 결정적 순서 키를 만든다.
    인자: candidate -> 후보
    반환값: 정렬 키
    작성 날짜: 2026/11/10
    """
    origin = candidate["origin"]
    if origin == "explicit":
        inner: tuple[Any, ...] = (candidate["position"], candidate["candidate_id"])
    elif origin == "current_task":
        inner = (candidate["recency"], candidate["candidate_id"])
    else:
        inner = (-candidate["score"], candidate["candidate_id"])
    return (GROUP_RANK[origin], *inner)


def _contains(outer: list[int], inner: list[int]) -> bool:
    """
    함수 이름: _contains()
    기능: 반열린 바이트 구간 포함 여부를 판단한다.
    인자: outer/inner -> [start, end]
    반환값: inner가 outer 안이면 True
    작성 날짜: 2026/11/10
    """
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def select(scenario: Row) -> Row:
    """
    함수 이름: select()
    기능: 정책 문서 4~6절 순서대로 후보를 평가해 compact 결과를 만든다.
    인자: scenario -> 시나리오
    반환값: budget_tokens·order·fragments·omitted·used_tokens(또는 error)
    작성 날짜: 2026/11/10
    """
    policy = SCENARIOS["policy"]
    costs = _costs(scenario)
    budget = costs["model_context_limit"] - sum(
        v for k, v in costs.items() if k != "model_context_limit"
    )
    if budget < 0:
        return {"error": "BUDGET_EXCEEDED"}
    ordered: list[Row] = []
    for origin, limit in policy["max_candidates"].items():
        group = [c for c in scenario["candidates"] if c["origin"] == origin]
        ordered += sorted(group, key=_order_key)[:limit]
    ordered.sort(key=_order_key)
    history = scenario.get("history_refs", [])
    retained: list[Row] = []
    fragments: list[Row] = []
    omitted: list[Row] = []
    used = 0
    for candidate in ordered:
        cid, status = candidate["candidate_id"], candidate.get("status", "ok")
        splittable = candidate["origin"] != "explicit" and candidate["kind"] != "symbol"
        same = [r for r in retained if r["object"] == candidate["object"]]
        holder = next((r for r in same if _contains(r["range"], candidate["range"])), None)
        tokens, inclusion = candidate["tokens"], "full"
        if status != "ok":
            omitted.append({"candidate_id": cid, "reason": status})
            continue
        if any(
            h["object"] == candidate["object"] and _contains(h["range"], candidate["range"])
            for h in history
        ):
            omitted.append({"candidate_id": cid, "reason": "in_history"})
            continue
        if holder is not None:
            omitted.append(
                {"candidate_id": cid, "reason": "duplicate", "duplicate_of": holder["candidate_id"]}
            )
            continue
        if tokens > policy["fragment_cap_tokens"]:
            if not splittable:
                omitted.append({"candidate_id": cid, "reason": "large_fragment"})
                continue
            tokens, inclusion = policy["fragment_cap_tokens"], "partial_size"
        remaining = budget - used
        if tokens > remaining:
            if not splittable or remaining < policy["min_partial_tokens"]:
                omitted.append({"candidate_id": cid, "reason": "over_budget"})
                continue
            tokens, inclusion = remaining, "partial_budget"
        start, end = candidate["range"]
        span = [start, start + tokens] if inclusion != "full" else [start, end]
        fragments.append(
            {"candidate_id": cid, "token_count": tokens, "inclusion": inclusion, "range": span}
        )
        retained.append({**candidate, "range": span})
        used += tokens
    result: Row = {
        "budget_tokens": budget,
        "order": [c["candidate_id"] for c in ordered],
        "fragments": fragments,
        "omitted": omitted,
        "used_tokens": used,
    }
    explicit_ids = {c["candidate_id"] for c in ordered if c["origin"] == "explicit"}
    first = next((o for o in omitted if o["candidate_id"] in explicit_ids), None)
    if first is not None and first["reason"] in RUN_CREATE_ERRORS:
        result["run_create_error"] = RUN_CREATE_ERRORS[first["reason"]]
    return result


def _ref(candidate: Row, span: list[int] | None = None, with_selection: bool = False) -> Row:
    """
    함수 이름: _ref()
    기능: 후보의 계약 ContextRef를 만든다. selection은 확인된 바이트 구간이다.
    인자: candidate -> 후보, span -> selection 구간, with_selection -> selection 포함 여부
    반환값: ContextRef
    작성 날짜: 2026/11/10
    """
    obj = SCENARIOS["objects"][candidate["object"]]
    if candidate["kind"] == "symbol":
        return {"kind": "symbol", "candidate_id": candidate["candidate_id"], "index_revision": 3}
    workspace = "ws_99999999" if obj.get("foreign") else "ws_00000001"
    if obj["kind"] == "runtime":
        pointer, revision = f"securecode://runtime/{workspace}/ses_00000001/{obj['id']}?v=1", 1
    else:
        pointer, revision = (
            f"securecode://source/{workspace}/{obj['id']}?v={obj['revision']}",
            obj["revision"],
        )
    ref: Row = {"kind": obj["kind"], "pointer": pointer}
    if with_selection:
        start, end = span or candidate["range"]
        byte_range = {"type": "byte", "start": start, "end": end}
        ref["selection"] = {
            "revision": revision,
            "content_sha256": obj["sha"] * 32,
            "range": byte_range,
        }
    return ref


def _citation(candidate: Row, fragment: Row) -> Row:
    """
    함수 이름: _citation()
    기능: fragment의 AnswerCitation을 만든다(심볼은 위치, 포인터는 실제 구간 selection).
    인자: candidate -> 후보, fragment -> compact fragment
    반환값: AnswerCitation
    작성 날짜: 2026/11/10
    """
    if candidate["kind"] != "symbol":
        return {"ref": _ref(candidate, fragment["range"], True)}
    obj = SCENARIOS["objects"][candidate["object"]]
    location = {
        "symbol_id": "sym_" + candidate["candidate_id"].removeprefix("cand_"),
        "qualname": "run",
        "kind": "function",
        "relative_path": obj["path"],
        "start_line": candidate["lines"][0],
        "end_line": candidate["lines"][1],
        "content_sha256": obj["sha"] * 32,
    }
    return {"ref": _ref(candidate), "location": location}


def build_plan(scenario: Row) -> Row:
    """
    함수 이름: build_plan()
    기능: compact 기대값과 입력으로 계약 ContextPreviewPlan 전체를 만든다(본문은 토큰 수만큼의 'x').
    인자: scenario -> 시나리오
    반환값: ContextPreviewPlan
    작성 날짜: 2026/11/10
    """
    expected = scenario["expected"]
    by_id = {c["candidate_id"]: c for c in scenario["candidates"]}
    selected_ids = [f["candidate_id"] for f in expected["fragments"]]
    selected = [
        {
            "candidate_id": cid,
            "ref": _ref(by_id[cid], with_selection=by_id[cid]["origin"] == "explicit"),
            "score": by_id[cid]["score"],
            "explicit": by_id[cid]["origin"] == "explicit",
            "estimated_tokens": by_id[cid]["tokens"],
            "origin": by_id[cid]["origin"],
        }
        for cid in selected_ids
    ]
    fragments = [
        {
            "candidate_id": f["candidate_id"],
            "ref": _ref(
                by_id[f["candidate_id"]],
                with_selection=by_id[f["candidate_id"]]["origin"] == "explicit",
            ),
            "content": "x" * f["token_count"],
            "token_count": f["token_count"],
            "inclusion": f["inclusion"],
            "provenance": _citation(by_id[f["candidate_id"]], f),
        }
        for f in expected["fragments"]
    ]
    omitted = []
    for row in expected["omitted"]:
        candidate = by_id[row["candidate_id"]]
        item: Row = {
            "candidate_id": row["candidate_id"],
            "origin": candidate["origin"],
            "reason": row["reason"],
        }
        if candidate["origin"] == "explicit" or row["reason"] == "duplicate":
            item["ref"] = _ref(candidate, with_selection=True)
        if "duplicate_of" in row:
            item["duplicate_of"] = row["duplicate_of"]
        omitted.append(item)
    return {
        "schema_version": "1",
        "index_revision": 3,
        "preview_digest": "e" * 64,
        "omissions_truncated": False,
        "selected": selected,
        "fragments": fragments,
        "omitted": omitted,
        "budget": {
            "budget_tokens": expected["budget_tokens"],
            "used_tokens": expected["used_tokens"],
            "count_mode": "provider_estimate",
            "costs": _costs(scenario),
        },
    }


def plan_violations(plan: Row) -> list[str]:
    """
    함수 이름: plan_violations()
    기능: 스키마로 표현할 수 없는 CONTEXT.md 결과 4번 불변식을 검사한다.
    인자: plan -> ContextPreviewPlan
    반환값: 위반 설명 목록(비면 통과)
    작성 날짜: 2026/11/10
    """
    problems: list[str] = []
    costs, budget = plan["budget"]["costs"], plan["budget"]
    fixed = sum(v for k, v in costs.items() if k != "model_context_limit")
    if budget["budget_tokens"] != costs["model_context_limit"] - fixed:
        problems.append("budget_tokens != limit - costs")
    if budget["used_tokens"] != sum(f["token_count"] for f in plan["fragments"]):
        problems.append("used_tokens != sum(fragments)")
    if budget["used_tokens"] > budget["budget_tokens"]:
        problems.append("used_tokens > budget_tokens")
    selected = [c["candidate_id"] for c in plan["selected"]]
    if sorted(selected) != sorted(f["candidate_id"] for f in plan["fragments"]):
        problems.append("selected and fragments differ")
    omitted = [o["candidate_id"] for o in plan["omitted"]]
    if set(selected) & set(omitted) or len(set(omitted)) != len(omitted):
        problems.append("retained and omitted ids overlap or repeat")
    for row in plan["omitted"]:
        if row["reason"] == "duplicate" and row["duplicate_of"] not in selected:
            problems.append(f"{row['candidate_id']} duplicate_of is not retained")
    for fragment in plan["fragments"]:
        selection = fragment["provenance"]["ref"].get("selection")
        if selection:
            width = selection["range"]["end"] - selection["range"]["start"]
            if width != len(fragment["content"].encode()):
                problems.append(f"{fragment['candidate_id']} selection width != content bytes")
    return problems


@pytest.mark.parametrize("scenario", SCENARIOS["scenarios"], ids=lambda s: s["id"])
def test_policy_reproduces_hand_computed_result(scenario: Row) -> None:
    """
    함수 이름: test_policy_reproduces_hand_computed_result()
    기능: 정책대로 다시 계산한 결과가 손계산 기대값과 같은지 확인한다.
    인자: scenario -> 시나리오
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    expected = {k: v for k, v in scenario["expected"].items()}
    assert select(scenario) == expected


@pytest.mark.parametrize(
    "scenario",
    [s for s in SCENARIOS["scenarios"] if "error" not in s["expected"]],
    ids=lambda s: s["id"],
)
def test_expected_plan_matches_contract(scenario: Row, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_expected_plan_matches_contract()
    기능: 기대값으로 만든 계획이 ContextPreviewPlan 계약과 불변식을 지키는지 확인한다.
    인자: scenario -> 시나리오, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    plan = build_plan(scenario)
    assert contract_check(PLAN_REF, plan) == []
    assert plan_violations(plan) == []


@pytest.mark.parametrize(
    "path",
    sorted((CONTRACTS_ROOT / "fixtures" / "context").glob("preview-*.valid.json")),
    ids=lambda p: p.name,
)
def test_existing_plan_fixtures_keep_invariants(path: Path) -> None:
    """
    함수 이름: test_existing_plan_fixtures_keep_invariants()
    기능: 4.2 미리보기 fixture의 계획도 같은 불변식을 지키는지 확인한다.
    인자: path -> fixture 파일
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    data = json.loads(path.read_text("utf-8"))["data"]
    if data.get("operation") == "plan" and "result" in data:
        assert plan_violations(data["result"]) == []
