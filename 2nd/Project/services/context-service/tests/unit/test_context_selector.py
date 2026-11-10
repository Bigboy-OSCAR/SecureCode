"""4.8 제품 선택 함수를 4.7 손계산 시나리오(selector-scenarios.json S1~S10)로 회귀 시험한다.

resolver는 시나리오 규칙(토큰 = 바이트)을 따르는 시험 reader로 바꾸고, 정렬·선별·크기·예산·포함 판정은
제품 코드(context.policy, context.selector)를 그대로 쓴다.
"""

import json
import random
from typing import Any

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.context.budget import CostInput, count_costs, minimum_margin
from securecode_context.context.models import Candidate, Material, SelectorLimits, Span
from securecode_context.context.policy import relevant_r0, run_create_error
from securecode_context.context.selector import select
from support.helpers import CONTRACTS_ROOT, FixedTokenCounter

SCENARIOS = json.loads((CONTRACTS_ROOT / "context" / "selector-scenarios.json").read_text("utf-8"))
POLICY = SCENARIOS["policy"]
LIMITS = SelectorLimits(
    fragment_cap_bytes=POLICY["fragment_cap_tokens"],
    min_partial_tokens=POLICY["min_partial_tokens"],
    max_candidates=dict(POLICY["max_candidates"]),
)


class ScenarioReader:
    """
    클래스 이름: ScenarioReader
    기능: [fixture] 시나리오 대상을 'x' 바이트로 보고 토큰 = 바이트로 읽는다. 봉투는 0토큰이다.
    작성 날짜: 2026/11/10
    """

    def __init__(self) -> None:
        """
        함수 이름: __init__()
        기능: 읽기 기록을 비운다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.reads: list[tuple[str, int, int, int]] = []

    def envelope_tokens(self, candidate: Candidate) -> int:
        """
        함수 이름: envelope_tokens()
        기능: 시나리오는 봉투 비용이 없다.
        인자: candidate -> 후보
        반환값: 0
        작성 날짜: 2026/11/10
        """
        return 0

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 구간 앞에서부터 max_tokens 바이트까지 읽는다.
        인자: candidate -> 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        self.reads.append((candidate.candidate_id, span.start, span.end, max_tokens))
        size = min(span.end - span.start, max_tokens)
        got = Span(span.object_key, span.start, span.start + size)
        return Material("x" * size, size, "provider_estimate", got, {}, got.end == span.end)


def to_candidate(row: dict[str, Any]) -> Candidate:
    """
    함수 이름: to_candidate()
    기능: 시나리오 후보를 해석된 Candidate로 바꾼다. 심볼은 같은 파일 Source와 같은 대상이다.
    인자: row -> 시나리오 후보
    반환값: Candidate
    작성 날짜: 2026/11/10
    """
    obj = SCENARIOS["objects"][row["object"]]
    key = (
        ("runtime", obj["id"], obj["sha"])
        if obj["kind"] == "runtime"
        else ("file", obj["path"], obj["sha"])
    )
    rank = row.get("position", row.get("recency", 0))
    return Candidate(
        row["candidate_id"], row["origin"], row["kind"], {}, row["score"], rank,
        row["tokens"], row.get("status", "ok"), Span(key, *row["range"]),
    )  # fmt: skip


def history_spans(scenario: dict[str, Any]) -> list[Span]:
    """
    함수 이름: history_spans()
    기능: 시나리오 history_refs를 대상 구간으로 바꾼다.
    인자: scenario -> 시나리오
    반환값: 구간 목록
    작성 날짜: 2026/11/10
    """
    spans = []
    for ref in scenario.get("history_refs", []):
        obj = SCENARIOS["objects"][ref["object"]]
        key = (
            ("runtime", obj["id"], obj["sha"])
            if obj["kind"] == "runtime"
            else ("file", obj["path"], obj["sha"])
        )
        spans.append(Span(key, *ref["range"]))
    return spans


def budget_of(scenario: dict[str, Any]) -> int:
    """
    함수 이름: budget_of()
    기능: 시나리오 비용으로 정책 3.1 식의 예산을 계산한다.
    인자: scenario -> 시나리오
    반환값: 예산(음수 가능)
    작성 날짜: 2026/11/10
    """
    costs = {**SCENARIOS["base_costs"], **scenario.get("costs", {})}
    limit = costs.pop("model_context_limit")
    return int(limit - sum(costs.values()))


def run(scenario: dict[str, Any], shuffle_seed: int | None = None) -> dict[str, Any]:
    """
    함수 이름: run()
    기능: 제품 select()로 시나리오를 돌려 compact 결과를 만든다.
    인자: scenario -> 시나리오, shuffle_seed -> 후보 입력 순서를 섞을 seed
    반환값: 기대값과 같은 모양의 사전
    작성 날짜: 2026/11/10
    """
    budget = budget_of(scenario)
    if budget < 0:
        return {"error": "BUDGET_EXCEEDED"}
    candidates = [to_candidate(row) for row in scenario["candidates"]]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(candidates)
    result = select(candidates, history_spans(scenario), budget, LIMITS, ScenarioReader())
    compact: dict[str, Any] = {
        "budget_tokens": budget,
        "order": [candidate.candidate_id for candidate in result.order],
        "fragments": [
            {
                "candidate_id": fragment.candidate.candidate_id,
                "token_count": fragment.material.token_count,
                "inclusion": fragment.inclusion,
                "range": [fragment.material.span.start, fragment.material.span.end],
            }
            for fragment in result.fragments
        ],
        "omitted": [
            {"candidate_id": o.candidate.candidate_id, "reason": o.reason}
            | ({"duplicate_of": o.duplicate_of} if o.duplicate_of else {})
            for o in result.omissions
        ],
        "used_tokens": result.used_tokens,
    }
    error = run_create_error(result.order, result.omissions)
    if error is not None:
        compact["run_create_error"] = error
    return compact


@pytest.mark.parametrize("scenario", SCENARIOS["scenarios"], ids=lambda s: s["id"])
def test_product_selector_matches_hand_computed_scenario(scenario: dict[str, Any]) -> None:
    """
    함수 이름: test_product_selector_matches_hand_computed_scenario()
    기능: 제품 선택 결과가 손계산 기대값(순서·fragment·누락·사용량·run 오류)과 같은지 본다.
    인자: scenario -> 시나리오
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    assert run(scenario) == scenario["expected"]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_selection_is_deterministic_for_any_input_order(seed: int) -> None:
    """
    함수 이름: test_selection_is_deterministic_for_any_input_order()
    기능: 후보 입력 순서를 섞어도 모든 시나리오 결과가 같다.
    인자: seed -> 섞기 seed
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    for scenario in SCENARIOS["scenarios"]:
        assert run(scenario, seed) == run(scenario)


def test_reads_never_exceed_remaining_budget_or_fragment_cap() -> None:
    """
    함수 이름: test_reads_never_exceed_remaining_budget_or_fragment_cap()
    기능: 모든 읽기 요청이 fragment 상한 구간과 남은 예산 안에서만 일어나는지 본다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    for scenario in SCENARIOS["scenarios"]:
        budget = budget_of(scenario)
        if budget < 0:
            continue
        reader = ScenarioReader()
        select([to_candidate(r) for r in scenario["candidates"]], [], budget, LIMITS, reader)
        for _cid, start, end, max_tokens in reader.reads:
            assert end - start <= LIMITS.fragment_cap_bytes
            assert 1 <= max_tokens <= budget


def test_fixed_costs_are_counted_and_negative_budget_is_refused() -> None:
    """
    함수 이름: test_fixed_costs_are_counted_and_negative_budget_is_refused()
    기능: 고정 비용을 실제 계수기로 세고(한글 포함) 추정 모드 최소 마진을 적용하며,
        음수 예산은 BUDGET_EXCEEDED로 막는다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    counter = FixedTokenCounter()
    costs = CostInput(4000, 500, 0, 10, "시스템", '{"tools":[]}', "질문", ["가", "나다"])
    counted = count_costs(counter, costs)
    assert (counted.system_tokens, counted.prompt_tokens, counted.history_tokens) == (9, 6, 9)
    assert counted.safety_margin_tokens == minimum_margin(4000, exact=False) == 1024
    assert counted.base_budget() == 4000 - (9 + 12 + 6 + 9 + 10 + 500 + 1024)
    with pytest.raises(ServiceError) as caught:
        count_costs(counter, CostInput(1500, 500, 0, 0, "s", "", "q", []))
    assert caught.value.code == ErrorCode.BUDGET_EXCEEDED


def test_r0_automatic_candidates_need_relative_relevance() -> None:
    """
    함수 이름: test_r0_automatic_candidates_need_relative_relevance()
    기능: 1위보다 훨씬 낮은(25% 미만) 또는 0.05 미만 R0 점수는 자동 후보에서 뺀다(3.6 live 재현값).
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    assert relevant_r0([0.519, 0.2, 0.012, 0.008]) == [True, True, False, False]
    assert relevant_r0([0.04, 0.03]) == [False, False]
    assert relevant_r0([]) == []
