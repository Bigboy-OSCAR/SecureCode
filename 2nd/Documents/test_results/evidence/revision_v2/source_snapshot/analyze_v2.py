"""Recompute the revision reports from complete frozen experiment records."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
from statistics import mean, median

import analyze as old_analysis
import experiment_v2 as exp
from output_diagnostics import order_only_failure


def calls(row):
    return [c for c in (row.get("selector"), row["answer_call"]) if c]


def stage_seconds(row, key):
    return sum(c["timings"].get(key, 0) / 1000 for c in calls(row))


def metrics(records):
    questions = old_analysis.per_question(records)
    times = [q["seconds"] for q in questions.values()]
    request_times = [r["query_seconds"] for r in records]
    by_category, by_project = {}, {}
    for field, dest in (("category", by_category), ("project", by_project)):
        for value in sorted({r[field] for r in records}):
            selected = [r for r in records if r[field] == value]
            dest[value] = {
                "correct": sum(r["correct"] for r in selected), "total": len(selected),
                "accuracy": mean(r["correct"] for r in selected),
                "unique_questions": len({r["task_id"] for r in selected}),
            }
    order_only = sum(order_only_failure(r) for r in records)
    return {
        "correct": sum(r["correct"] for r in records), "total": len(records),
        "accuracy": mean(r["correct"] for r in records), "unique_questions": len(questions),
        "order_only_count": order_only,
        "order_tolerant_accuracy": mean(r["correct"] or order_only_failure(r) for r in records),
        "mean_query_seconds": mean(times), "request_mean_seconds": mean(request_times),
        "request_p50_seconds": median(request_times),
        "request_p95_seconds": old_analysis.quantile(request_times, .95),
        "question_median_p95_seconds": old_analysis.quantile(times, .95),
        "mean_context_tokens": mean(r["context_tokens"] for r in records),
        "mean_selected_context_tokens": mean(r["selected_context_tokens"] for r in records),
        "mean_input_tokens": mean(r["input_tokens"] for r in records),
        "mean_output_tokens": mean(r["output_tokens"] for r in records),
        "mean_prefill_seconds": mean(stage_seconds(r, "prompt_ms") for r in records),
        "mean_decode_seconds": mean(stage_seconds(r, "predicted_ms") for r in records),
        "mean_other_seconds": mean(r["query_seconds"] - stage_seconds(r, "prompt_ms")
                                   - stage_seconds(r, "predicted_ms") for r in records),
        "mean_tokenize_seconds": mean(r["tokenize_seconds"] for r in records),
        "mean_compaction_seconds": mean(r["compaction_seconds"] for r in records),
        "raw_evidence_recall": mean(r["raw_evidence_recall"] for r in records),
        "all_raw_evidence": mean(r["all_raw_evidence"] for r in records),
        "unstable_questions": sum(0 < q["score"] < 1 for q in questions.values()),
        "different_output_questions": sum(
            len({json.dumps(r["parsed_answer"], sort_keys=True) for r in records
                 if r["task_id"] == tid}) > 1 for tid in questions),
        "failure_counts": dict(Counter(r["failure"] for r in records if r["failure"])),
        "by_category": by_category, "by_project": by_project,
    }


def comparison(records, higher, base):
    h = old_analysis.per_question([r for r in records if r["arm"] == higher])
    b = old_analysis.per_question([r for r in records if r["arm"] == base])
    assert set(h) == set(b)
    projects = sorted({q["project"] for q in h.values()})
    grouped = [
        {
            "score_delta": mean(h[t]["score"] - b[t]["score"] for t in h if h[t]["project"] == p),
            "h_time": mean(h[t]["seconds"] for t in h if h[t]["project"] == p),
            "b_time": mean(b[t]["seconds"] for t in b if b[t]["project"] == p),
        } for p in projects
    ]
    draws = itertools.product(range(len(projects)), repeat=len(projects))
    accuracy_draws, time_draws, reduction_draws = [], [], []
    for draw in draws:
        hd = mean(grouped[i]["h_time"] for i in draw)
        bd = mean(grouped[i]["b_time"] for i in draw)
        accuracy_draws.append(100 * mean(grouped[i]["score_delta"] for i in draw))
        time_draws.append(hd - bd)
        reduction_draws.append(100 * (1 - hd / bd))
    ci = lambda values: [old_analysis.quantile(values, .025), old_analysis.quantile(values, .975)]
    h_time, b_time = mean(q["seconds"] for q in h.values()), mean(q["seconds"] for q in b.values())
    both = [t for t in h if h[t]["score"] == 1 and b[t]["score"] == 1]
    delta = mean(h[t]["score"] - b[t]["score"] for t in h)
    flips = [
        abs(mean(sign * g["score_delta"] for sign, g in zip(signs, grouped)))
        for signs in itertools.product((-1, 1), repeat=len(projects))
    ]
    return {
        "higher": higher, "base": base, "delta_pp": 100 * delta,
        "ci95_pp": ci(accuracy_draws),
        "win": sum(h[t]["score"] > b[t]["score"] for t in h),
        "loss": sum(h[t]["score"] < b[t]["score"] for t in h),
        "tie": sum(h[t]["score"] == b[t]["score"] for t in h),
        "latency_delta_seconds": h_time - b_time, "latency_ci95_seconds": ci(time_draws),
        "latency_ratio": h_time / b_time, "latency_reduction_pct": 100 * (1 - h_time / b_time),
        "latency_reduction_ci95_pct": ci(reduction_draws),
        "both_success_n": len(both),
        "both_success_latency_ratio": mean(h[t]["seconds"] for t in both) / mean(b[t]["seconds"] for t in both) if both else None,
        "project_deltas_pp": {p: 100*g["score_delta"] for p, g in zip(projects, grouped)},
        "unadjusted_project_signflip_p": sum(f >= abs(delta) - 1e-12 for f in flips) / len(flips),
        "bootstrap_resamples": len(accuracy_draws), "cluster_count": len(projects),
        "interpretation": "Exploratory exact-enumerated percentile bootstrap over six project clusters; repeated questions are not independent observations. No noninferiority claim.",
    }


def split_summary(out, split, expected_repeats):
    records = exp.rows(out / f"results_{split}.jsonl")
    task_path = out / "holdout/eval_tasks.json" if split == "new" else exp.BASE / "dataset/eval_tasks.json"
    tasks = json.loads(task_path.read_text())
    keys = [(r["task_id"], r["repeat"], r["arm"]) for r in records]
    expected = {(t["id"], rep, arm) for t in tasks for rep in range(expected_repeats)
                for arm in exp.CONFIG["arms"]}
    assert len(keys) == len(set(keys)) and set(keys) == expected, f"Incomplete {split}"
    result = {
        "rows": len(records), "unique_questions": len(tasks),
        "projects": len({t["project"] for t in tasks}), "repeats": expected_repeats,
        "metrics_by_arm": {arm: metrics([r for r in records if r["arm"] == arm])
                          for arm in exp.CONFIG["arms"]},
        "comparisons": {f"{h}-{b}": comparison(records, h, b)
                        for h, b in (("C", "RH"), ("C", "A"), ("RH", "A"))},
    }
    # Family is the two declared quality comparisons. Speed contrast is separate.
    order = sorted(("C-A", "C-RH"), key=lambda k: result["comparisons"][k]["unadjusted_project_signflip_p"])
    previous = 0
    for rank, key in enumerate(order):
        value = result["comparisons"][key]
        previous = max(previous, min(1, (2-rank) * value["unadjusted_project_signflip_p"]))
        value["holm_p_two_quality_comparisons"] = previous
    return result, records


def choose_examples(records):
    grouped = defaultdict(dict)
    for row in records:
        if row["repeat"] == 0:
            grouped[row["task_id"]][row["arm"]] = row
    examples, used = [], set()
    patterns = [
        ("C_gain_RH", lambda g: g["C"]["correct"] and not g["RH"]["correct"],
         "표시를 줄인 뒤 정답으로 바뀐 사례", "고유 본문은 같지만 배치와 반복을 바꾸면 출력도 달라질 수 있습니다."),
        ("C_loss_RH", lambda g: g["RH"]["correct"] and not g["C"]["correct"],
         "표시를 줄인 뒤 오답으로 바뀐 사례", "본문 보존만으로 정답 보존을 보장할 수 없습니다."),
        ("C_gain_A", lambda g: g["C"]["correct"] and not g["A"]["correct"],
         "기존 방식보다 나아진 사례", "선택된 근거와 답변을 함께 확인한 질적 사례이며 전체 개선의 증명은 아닙니다."),
        ("all_wrong", lambda g: not any(r["correct"] for r in g.values()),
         "세 방식 모두 실패한 사례", "검색 결과만으로 모델의 계산·추론 오류가 해결되지는 않습니다."),
    ]
    for kind, predicate, description, caution in patterns:
        options = [(tid, group) for tid, group in sorted(grouped.items()) if tid not in used and predicate(group)]
        if not options:
            continue
        tid, group = options[0]
        used.add(tid)
        examples.append({
            "kind": kind, "split": "new", "task_id": tid, "repeat": 0,
            "question": group["A"]["question"], "expected": group["A"]["expected"],
            "description_ko": description,
            "observation_ko": "A/RH/C의 동일 질문·반복 결과를 원자료에서 직접 비교했습니다.",
            "caution_ko": caution,
            "arms": {
                arm: {k: row[k] for k in ("correct", "parsed_answer", "context_tokens",
                                         "query_seconds", "failure", "chosen")}
                for arm, row in group.items()
            },
        })
    # Korean explanations of the actual fixed questions; examples remain
    # selected by the symmetric gain/loss rule above, never by these labels.
    descriptions = {
        "eval_inventory__v2_partial_depletes_available": {
            "question_ko": "재고 9개 중 1개가 이미 잡혀 있을 때 8개를 요청하고 부분 예약을 허용하면, 예약 뒤 판매 가능한 수량은 얼마인가? remaining_after(9,1,8,True)",
            "observation_ko": "안전재고 3개를 빼면 처음 판매 가능량은 5개입니다. 5개를 부분 예약한 뒤 남는 판매 가능량은 0개입니다.",
            "caution_ko": "같은 근거에서 답이 바뀐 관찰입니다. 중복 제거와 제목 변경 중 어느 요소가 영향을 주었는지는 분리하지 않았습니다.",
        },
        "eval_authorization__v2_last_valid_session_second": {
            "question_ko": "자기 문서의 쓰기 권한이 있고 세션 시작이 200, 현재 시각이 3799라면 편집 가능한가? can_edit_own('owner',['document:write'],200,3799)",
            "observation_ko": "세션 나이 3599는 제한 3600보다 작으므로 반환값은 불리언 true입니다. 문자열 \"allowed\"는 허용이라는 뜻이어도 반환 자료형이 달라 오답입니다.",
            "caution_ko": "이 사례는 자료형 준수 실패입니다. 이를 곧바로 권한 로직 자체를 이해하지 못한 증거로 해석하지 않습니다.",
        },
    }
    for example in examples:
        example.update(descriptions.get(example["task_id"], {}))
    return examples


def generate(out):
    integrity = json.loads((out / "integrity_v2.json").read_text())
    assert integrity["status"] == "PASS" and integrity["mode"] == "final", \
        "Final independent integrity audit must pass before publication"
    preflight = json.loads((out / "preflight_independent.json").read_text())
    assert preflight["status"] == "passed"
    new, new_rows = split_summary(out, "new", 3)
    old, old_rows = split_summary(out, "old", 1)
    all_rows = new_rows + old_rows
    c_rows = [r for r in all_rows if r["arm"] == "C"]
    lookup = {(r["split"], r["task_id"], r["repeat"], r["arm"]): r for r in all_rows}
    paired = [
        (r, lookup[(r["split"], r["task_id"], r["repeat"], "RH")]) for r in c_rows
    ]
    all_calls = exp.rows(out / "model_calls.jsonl")
    original = json.loads((exp.BASE / "analysis.json").read_text())
    vector_builds = [
        json.loads(p.read_text()) for p in out.glob("preparation_new_*.json")
    ]
    vector_values = [v for b in vector_builds for v in b["document_vector_build_seconds"].values()]
    v1_rh = [r for r in exp.rows(exp.BASE / "results_eval_main.jsonl") if r["arm"] == "RH"]
    source_paths = [
        out / "results_new.jsonl", out / "results_old.jsonl", out / "results_dev.jsonl",
        out / "protocol.json", out / "environment.json", out / "model_calls.jsonl",
        out / "holdout/eval_tasks.json", out / "holdout/gold_validation.json",
        out / "audit.json", out / "preflight_independent.json", out / "integrity_v2.json",
        exp.BASE / "results_eval_main.jsonl", exp.BASE / "analysis.json",
    ]
    import os
    summary = {
        "schema_version": 2, "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "report_date": "2026-10-20",
        "by_split": {"new": new, "old": old},
        "validation": {
            "all_payload_preserved": all(r["compaction"]["payload_preserved"] and
                 r["compaction"]["selected_payload_sha256"] == r["compaction"]["emitted_payload_sha256"] for r in c_rows),
            "paired_selection_equal": all(c["chosen"] == rh["chosen"] and
                c["selected_context_sha256"] == rh["selected_context_sha256"] for c, rh in paired),
            "expected_rows": 576, "actual_rows": len(all_rows),
            "development_rows": len(exp.rows(out / "results_dev.jsonl")),
            "execution_errors": sum(bool(c.get("error")) for c in all_calls),
            "context_overruns": sum(r["context_tokens"] > 1024 for r in all_rows),
            "generation_limits": sum(not c["ok"] for c in all_calls),
            "prompt_cache_hits": sum(c["timings"].get("cache_n", 0) > 0 for c in all_calls),
            "all_calls_prompt_cache_disabled": all(c["request"]["cache_prompt"] is False for c in all_calls),
            "independent_integrity": integrity,
        },
        "costs": {
            "new_summary_calls": sum(c["purpose"].startswith("build") for c in all_calls),
            "original_summary_build_seconds": original["build"]["seconds"],
            "original_summary_count": original["build"]["summary_count"],
            "mean_vector_build_seconds": mean(vector_values),
            "vector_build_total_seconds": sum(vector_values),
            "v1_rh_request_mean_seconds": mean(r["query_seconds"] for r in v1_rh),
            "v1_rh_mean_prefill_seconds": mean(stage_seconds(r, "prompt_ms") for r in v1_rh),
            "v1_rh_mean_decode_seconds": mean(stage_seconds(r, "predicted_ms") for r in v1_rh),
            "initialization_note": "Existing v1 summaries reused. Document vectors timed separately. Historical summary build cost is not full cold-start cost.",
        },
        "examples": choose_examples(new_rows),
        "source_hashes": {os.path.relpath(p, out): exp.v1.sha(p) for p in source_paths if p.exists()},
        "measurement_notes": [
            "Primary mean_query_seconds is the mean across 48 question-specific median-of-three physical query times.",
            "Request p50/p95 use all 144 observed requests per arm, not question medians.",
            "Prefill + decode + other form a disjoint decomposition of mean request time.",
            "Tokenizer and compaction durations overlap other stages; do not add them to a stacked total.",
            "New means new questions on already seen synthetic projects; no independent repository generalization.",
            "Strict JSON/type/list order scoring remains primary. Order-tolerant diagnostics are supplementary.",
            "Old and new question scores must not be pooled or treated as 96 independent projects.",
        ],
    }
    assert summary["validation"]["all_payload_preserved"]
    assert summary["validation"]["paired_selection_equal"]
    exp.v1.dump(out / "summary_v2.json", summary)
    print(json.dumps({"by_split": summary["by_split"], "validation": {
        k: v for k, v in summary["validation"].items() if k != "independent_integrity"
    }}, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=exp.OUT)
    generate(parser.parse_args().out)
