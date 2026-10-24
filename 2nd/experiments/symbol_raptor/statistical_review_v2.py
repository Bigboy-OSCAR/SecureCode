"""Independent NumPy recomputation of v2 statistics; never calls a model.

This script does not import the experiment or analysis implementations. It reads
their saved inputs/outputs, independently grades answer text, and writes only
statistical_review_v2.json. Run after the benchmark has stopped.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

import numpy as np

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[2] / "Documents/test_results/evidence"
ARMS = ["A", "RH", "C"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def typed_equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(typed_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(typed_equal(x, y) for x, y in zip(a, b))
    return a == b


def grade(row, task, asset):
    call = row["answer_call"]
    actual = None
    if not call["ok"]:
        correct, failure = False, "execution_or_limit"
    else:
        text = call["answer"].strip()
        if text.startswith("```") and text.endswith("```"):
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S | re.I)
            if fenced:
                text = fenced.group(1)
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            correct, failure = False, "invalid_json"
        else:
            if type(parsed) is not dict or list(parsed.keys()) != ["answer"]:
                actual = parsed
                correct, failure = False, "invalid_schema"
            else:
                actual = parsed["answer"]
                correct = typed_equal(actual, task["expected"])
                failure = None if correct else "abstained" if actual is None else "wrong_answer"
    selector = row["selector"]
    if selector:
        found = re.search(r"memory://symbol/[A-Za-z0-9_./-]+::[A-Za-z0-9_.]+",
                          selector["answer"]) if selector["ok"] else None
        uid = found.group(0) if found else None
        valid = uid in asset["nodes"] and uid in {s["uri"] for s in asset["index"]["symbols"]}
        if not valid:
            correct, failure = False, "selector_invalid"
    order_only = (
        not correct and failure == "wrong_answer" and call["ok"]
        and (not selector or selector["ok"])
        and type(actual) is list and type(task["expected"]) is list
        and all(type(x) is str for x in actual + task["expected"])
        and len(actual) == len(set(actual))
        and len(task["expected"]) == len(set(task["expected"]))
        and set(actual) == set(task["expected"])
    )
    return bool(correct), actual, failure, bool(order_only)


def stage(row, key):
    return sum(c["timings"].get(key, 0) / 1000
               for c in [row["selector"], row["answer_call"]] if c)


def fmean(values):
    return float(np.mean(values))


def per_question(records):
    grouped = {}
    for tid in sorted({r["task_id"] for r in records}):
        selected = [r for r in records if r["task_id"] == tid]
        grouped[tid] = {
            "project": selected[0]["project"],
            "score": fmean([r["correct"] for r in selected]),
            "seconds": float(np.median([r["query_seconds"] for r in selected])),
        }
    return grouped


def arm_metrics(records, order_diagnostics):
    questions = per_question(records)
    request_times = np.array([r["query_seconds"] for r in records])
    question_times = np.array([q["seconds"] for q in questions.values()])
    correct = sum(r["correct"] for r in records)
    order_only = sum(order_diagnostics[(r["task_id"], r["repeat"], r["arm"])] for r in records)
    metrics = {
        "correct": correct, "total": len(records), "accuracy": correct / len(records),
        "unique_questions": len(questions), "order_only_count": order_only,
        "order_tolerant_accuracy": (correct + order_only) / len(records),
        "mean_query_seconds": fmean(question_times),
        "request_mean_seconds": fmean(request_times),
        "request_p50_seconds": float(np.median(request_times)),
        "request_p95_seconds": float(np.percentile(request_times, 95, method="linear")),
        "question_median_p95_seconds": float(np.percentile(question_times, 95, method="linear")),
        "unstable_questions": sum(0 < q["score"] < 1 for q in questions.values()),
        "different_output_questions": sum(
            len({json.dumps(r["parsed_answer"], sort_keys=True)
                 for r in records if r["task_id"] == tid}) > 1 for tid in questions),
        "failure_counts": dict(Counter(r["failure"] for r in records if r["failure"])),
    }
    for source, target in [
        ("context_tokens", "mean_context_tokens"),
        ("selected_context_tokens", "mean_selected_context_tokens"),
        ("input_tokens", "mean_input_tokens"), ("output_tokens", "mean_output_tokens"),
        ("tokenize_seconds", "mean_tokenize_seconds"),
        ("compaction_seconds", "mean_compaction_seconds"),
        ("raw_evidence_recall", "raw_evidence_recall"),
        ("all_raw_evidence", "all_raw_evidence"),
    ]:
        metrics[target] = fmean([r[source] for r in records])
    metrics["mean_prefill_seconds"] = fmean([stage(r, "prompt_ms") for r in records])
    metrics["mean_decode_seconds"] = fmean([stage(r, "predicted_ms") for r in records])
    metrics["mean_other_seconds"] = fmean([
        r["query_seconds"] - stage(r, "prompt_ms") - stage(r, "predicted_ms")
        for r in records])
    for field, output in [("category", "by_category"), ("project", "by_project")]:
        metrics[output] = {}
        for value in sorted({r[field] for r in records}):
            subset = [r for r in records if r[field] == value]
            metrics[output][value] = {
                "correct": sum(r["correct"] for r in subset), "total": len(subset),
                "accuracy": fmean([r["correct"] for r in subset]),
                "unique_questions": len({r["task_id"] for r in subset}),
            }
    assert abs(sum(metrics[k] for k in [
        "mean_prefill_seconds", "mean_decode_seconds", "mean_other_seconds"
    ]) - metrics["request_mean_seconds"]) < 1e-10
    return metrics


def contrast(records, higher, base):
    q = {
        arm: per_question([r for r in records if r["arm"] == arm])
        for arm in [higher, base]
    }
    tids = sorted(q[higher])
    assert tids == sorted(q[base])
    projects = sorted({v["project"] for v in q[higher].values()})
    assert len(projects) == 6
    score_delta = np.array([q[higher][t]["score"] - q[base][t]["score"] for t in tids])
    times = {a: np.array([q[a][t]["seconds"] for t in tids]) for a in q}
    membership = np.array([q[higher][t]["project"] for t in tids])
    assert all(np.count_nonzero(membership == p) == 8 for p in projects)
    cluster_scores = np.array([score_delta[membership == p].mean() for p in projects])
    cluster_times = {
        a: np.array([times[a][membership == p].mean() for p in projects]) for a in q
    }
    # Full ordered index tensor enumerates 6^6 cluster draws, independently of
    # the production Python-loop implementation.
    indices = np.indices((6,) * 6, dtype=np.int8).reshape(6, -1).T
    accuracy_draws = cluster_scores[indices].mean(axis=1) * 100
    h_draws = cluster_times[higher][indices].mean(axis=1)
    b_draws = cluster_times[base][indices].mean(axis=1)
    signs = np.array(list(itertools.product([-1, 1], repeat=6)), dtype=np.int8)
    flips = np.abs(signs @ cluster_scores / 6)
    h_time, b_time = times[higher].mean(), times[base].mean()
    both = np.array([q[higher][t]["score"] == q[base][t]["score"] == 1 for t in tids])
    ci = lambda data: [float(v) for v in np.quantile(data, [.025, .975], method="linear")]
    return {
        "higher": higher, "base": base, "delta_pp": float(score_delta.mean() * 100),
        "ci95_pp": ci(accuracy_draws),
        "win": int(np.count_nonzero(score_delta > 0)),
        "loss": int(np.count_nonzero(score_delta < 0)),
        "tie": int(np.count_nonzero(score_delta == 0)),
        "latency_delta_seconds": float(h_time - b_time),
        "latency_ci95_seconds": ci(h_draws - b_draws),
        "latency_ratio": float(h_time / b_time),
        "latency_reduction_pct": float(100 * (1 - h_time / b_time)),
        "latency_reduction_ci95_pct": ci(100 * (1 - h_draws / b_draws)),
        "both_success_n": int(np.count_nonzero(both)),
        "both_success_latency_ratio": float(times[higher][both].mean() / times[base][both].mean())
        if both.any() else None,
        "project_deltas_pp": {p: float(v * 100) for p, v in zip(projects, cluster_scores)},
        "unadjusted_project_signflip_p": float(np.mean(flips >= abs(score_delta.mean()) - 1e-12)),
        "bootstrap_resamples": len(indices), "cluster_count": len(projects),
    }


def split_review(base, out, split, repeats, assets):
    records = rows(out / f"results_{split}.jsonl")
    tasks = read(out / "holdout/eval_tasks.json" if split == "new" else base / "dataset/eval_tasks.json")
    taskmap = {t["id"]: t for t in tasks}
    keys = [(r["task_id"], r["repeat"], r["arm"]) for r in records]
    expected = set(itertools.product(taskmap, range(repeats), ARMS))
    assert len(keys) == len(set(keys)) and set(keys) == expected
    order_diagnostics = {}
    for r in records:
        task = taskmap[r["task_id"]]
        assert typed_equal(r["expected"], task["expected"])
        assert r["project"] == task["project"] and r["category"] == task["category"]
        correct, actual, failure, order_only = grade(r, task, assets[r["project"]])
        assert correct == r["correct"] and typed_equal(actual, r["parsed_answer"])
        assert failure == r["failure"], (r["task_id"], failure, r["failure"])
        order_diagnostics[(r["task_id"], r["repeat"], r["arm"])] = order_only
    comparisons = {f"{a}-{b}": contrast(records, a, b)
                   for a, b in [("C", "RH"), ("C", "A"), ("RH", "A")]}
    names = ["C-A", "C-RH"]
    pvalues = np.array([comparisons[n]["unadjusted_project_signflip_p"] for n in names])
    order = np.argsort(pvalues, kind="stable")
    adjusted = np.minimum(1, np.maximum.accumulate(pvalues[order] * np.array([2, 1])))
    for i, value in zip(order, adjusted):
        comparisons[names[int(i)]]["holm_p_two_quality_comparisons"] = float(value)
    return {
        "rows": len(records), "unique_questions": len(tasks),
        "projects": len({t["project"] for t in tasks}), "repeats": repeats,
        "metrics_by_arm": {
            a: arm_metrics([r for r in records if r["arm"] == a], order_diagnostics)
            for a in ARMS},
        "comparisons": comparisons,
    }, records


def compare_tree(expected, reported, prefix=""):
    mismatches, checked = [], 0
    if isinstance(expected, dict):
        for key, value in expected.items():
            if key not in reported:
                mismatches.append({"path": f"{prefix}/{key}", "problem": "missing"})
                continue
            found, count = compare_tree(value, reported[key], f"{prefix}/{key}")
            mismatches.extend(found)
            checked += count
    elif isinstance(expected, list):
        if len(expected) != len(reported):
            mismatches.append({"path": prefix, "expected": expected, "reported": reported})
        else:
            for i, (a, b) in enumerate(zip(expected, reported)):
                found, count = compare_tree(a, b, f"{prefix}/{i}")
                mismatches.extend(found)
                checked += count
    else:
        checked = 1
        equal = bool(np.isclose(expected, reported, rtol=1e-10, atol=1e-10)) \
            if isinstance(expected, (int, float)) and isinstance(reported, (int, float)) \
            else expected == reported
        if not equal:
            mismatches.append({"path": prefix, "expected": expected, "reported": reported})
    return mismatches, checked


def timing_review(records, calls):
    dt = datetime.fromisoformat
    sorted_rows = sorted(records, key=lambda r: dt(r["started_at_utc"]))
    overlaps = []
    gaps = []
    for a, b in zip(sorted_rows, sorted_rows[1:]):
        gap = (dt(b["started_at_utc"]) - dt(a["ended_at_utc"])).total_seconds()
        gaps.append(gap)
        if gap < 0:
            overlaps.append([a["split"], a["task_id"], a["arm"],
                             b["split"], b["task_id"], b["arm"], gap])
    sorted_calls = sorted(calls, key=lambda c: dt(c["started_at_utc"]))
    call_overlaps = [
        [a["call_id"], b["call_id"]]
        for a, b in zip(sorted_calls, sorted_calls[1:])
        if dt(a["ended_at_utc"]) > dt(b["started_at_utc"])
    ]
    mismatches = [
        abs((dt(r["ended_at_utc"]) - dt(r["started_at_utc"])).total_seconds()
            - r["query_seconds"]) for r in records
    ]
    nesting = []
    for r in records:
        start, end = dt(r["started_at_utc"]), dt(r["ended_at_utc"])
        for c in [r["selector"], r["answer_call"]]:
            if c and not start <= dt(c["started_at_utc"]) <= dt(c["ended_at_utc"]) <= end:
                nesting.append(c["call_id"])
    assert not overlaps and not call_overlaps and not nesting
    assert max(mismatches) < .05
    return {
        "query_rows_including_development": len(records), "model_calls_including_warmups": len(calls),
        "query_overlap_count": len(overlaps), "model_call_overlap_count": len(call_overlaps),
        "model_calls_outside_parent_query": nesting,
        "minimum_interquery_gap_seconds": min(gaps),
        "maximum_query_UTC_minus_perf_clock_discrepancy_seconds": max(mismatches),
        "query_overlap_details": overlaps,
        "scope": "Recorded UTC intervals are local provenance; comparisons do not certify unrelated OS/GPU load.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--out", type=Path, default=BASE / "revision_v2")
    args = parser.parse_args()
    base, out = args.base.resolve(), args.out.resolve()
    assets = {p.stem: read(p) for p in (base / "assets").glob("*.json")}
    splits, all_rows = {}, []
    for split, repeats in [("new", 3), ("old", 1)]:
        splits[split], records = split_review(base, out, split, repeats, assets)
        all_rows.extend(records)
    all_rows.extend(rows(out / "results_dev.jsonl"))
    timing = timing_review(all_rows, rows(out / "model_calls.jsonl"))
    source_paths = [
        out / "results_new.jsonl", out / "results_old.jsonl", out / "results_dev.jsonl",
        out / "model_calls.jsonl", out / "holdout/eval_tasks.json",
        base / "dataset/eval_tasks.json", Path(__file__),
    ]
    summary_path = out / "summary_v2.json"
    result = {
        "status": "RAW_RECOMPUTED_WAITING_FOR_SUMMARY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation": {
            "imports_experiment_or_analysis_code": False, "model_calls": 0,
            "numpy_version": np.__version__, "python_version": sys.version,
            "strict_grading": "Reparse saved answer text; recursive exact JSON type/key/list-order equality; independently validate selector URI.",
            "bootstrap": "NumPy 6-dimensional index tensor enumerates all 46,656 ordered six-project cluster samples.",
            "accuracy": "Mean three-repeat binary score per question, then equal-weight eight-question project means.",
            "latency": "Median three measured times per question, then arithmetic mean across 48 questions.",
            "request_p95": "NumPy percentile on all individual requests; linear interpolation.",
            "signflip": "All 64 signed project-level mean score deltas; two-sided absolute statistic.",
            "adjustment": "Holm stepdown for C-A and C-RH quality comparisons only.",
        },
        "by_split": splits, "timing_validation": timing,
        "interpretation_limits": [
            "Six already known synthetic projects; questions and projects are not independent repository validation.",
            "Strict primary score includes requested output order; order-only scoring is a secondary diagnostic.",
            "Quality intervals/sign flips are exploratory; nonsignificance is not accuracy equivalence or noninferiority.",
            "Latency intervals reflect six-project task mix variation, not independent hardware-session uncertainty.",
            "Request stage means sum to request mean time, not mean of per-question median time.",
        ],
        "source_sha256": {str(p.relative_to(base)) if p.is_relative_to(base) else str(p): sha(p)
                          for p in source_paths},
    }
    if summary_path.exists():
        reported = read(summary_path)
        discrepancies, count = compare_tree(splits, reported["by_split"], "by_split")
        result["comparison_to_analysis"] = {
            "checked_scalar_values": count, "mismatches": discrepancies,
            "summary_sha256": sha(summary_path),
            "analysis_code_sha256": sha(Path(__file__).with_name("analyze_v2.py")),
        }
        result["status"] = "PASS" if not discrepancies else "FAIL"
    destination = out / "statistical_review_v2.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "comparison": result.get("comparison_to_analysis"),
        "new_C_RH": splits["new"]["comparisons"]["C-RH"],
        "new_C_A": splits["new"]["comparisons"]["C-A"],
        "timing": timing,
    }, ensure_ascii=False, indent=2))
    if result["status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
