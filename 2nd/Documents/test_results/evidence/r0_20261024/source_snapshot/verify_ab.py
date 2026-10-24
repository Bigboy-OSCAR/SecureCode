"""Offline review: independent grading/statistics plus context reconstruction."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import itertools
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import experiment_ab as exp
import audit_v2 as token_audit


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def grade(row, task):
    call = row["answer_call"]
    actual = None
    if not call["ok"]:
        correct, failure = False, "execution_or_limit"
    else:
        text = call["answer"].strip()
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S)
        if match:
            text = match[1]
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            correct, failure = False, "invalid_json"
        else:
            if type(obj) is not dict or set(obj) != {"answer"}:
                actual, correct, failure = obj, False, "invalid_schema"
            else:
                actual = obj["answer"]
                correct = equal(actual, task["expected"])
                failure = None if correct else "abstained" if actual is None else "wrong_answer"
    if not row["selection_valid"]:
        correct, failure = False, "selector_invalid"
    return correct, actual, failure


def avg(values):
    values = list(values)
    return sum(values) / len(values)


def quantile(values, probability):
    values = sorted(values)
    p = probability * (len(values) - 1)
    lo = int(p)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (p - lo)


def independent_stats(group):
    by_arm = {}
    for arm in ["A", "B"]:
        rs = [r for r in group if r["arm"] == arm]
        q = defaultdict(list)
        for r in rs:
            q[r["task_id"]].append(r)
        by_arm[arm] = {
            tid: {"score": avg(r["correct"] for r in selected),
                  "time": quantile([r["query_seconds"] for r in selected], .5),
                  "project": selected[0]["project"]} for tid, selected in q.items()}
    projects = sorted({r["project"] for r in group})
    groups = []
    for project in projects:
        tids = [t for t, q in by_arm["A"].items() if q["project"] == project]
        groups.append({"delta": avg(by_arm["B"][t]["score"] - by_arm["A"][t]["score"] for t in tids),
                       "a": avg(by_arm["A"][t]["time"] for t in tids),
                       "b": avg(by_arm["B"][t]["time"] for t in tids)})
    draws = {"quality": [], "time": [], "reduction": []}
    for selected in itertools.product(groups, repeat=len(groups)):
        a, b = avg(x["a"] for x in selected), avg(x["b"] for x in selected)
        draws["quality"].append(100 * avg(x["delta"] for x in selected))
        draws["time"].append(b - a)
        draws["reduction"].append(100 * (1 - b / a))
    a = avg(q["time"] for q in by_arm["A"].values())
    b = avg(q["time"] for q in by_arm["B"].values())
    delta = avg(x["delta"] for x in groups)
    flips = [abs(avg(sign * g["delta"] for sign, g in zip(signs, groups)))
             for signs in itertools.product([-1, 1], repeat=len(groups))]
    comparison = {
        "delta_pp": delta * 100,
        "ci95_pp": [quantile(draws["quality"], p) for p in [.025, .975]],
        "latency_delta_seconds": b - a,
        "latency_ci95_seconds": [quantile(draws["time"], p) for p in [.025, .975]],
        "latency_ratio": b / a, "latency_reduction_pct": 100 * (1 - b / a),
        "latency_reduction_ci95_pct": [quantile(draws["reduction"], p) for p in [.025, .975]],
        "win": sum(by_arm["B"][t]["score"] > by_arm["A"][t]["score"] for t in by_arm["A"]),
        "loss": sum(by_arm["B"][t]["score"] < by_arm["A"][t]["score"] for t in by_arm["A"]),
        "tie": sum(by_arm["B"][t]["score"] == by_arm["A"][t]["score"] for t in by_arm["A"]),
        "unadjusted_project_signflip_p": sum(v >= abs(delta) - 1e-12 for v in flips) / len(flips),
    }
    metrics = {}
    for arm in ["A", "B"]:
        rs = [r for r in group if r["arm"] == arm]
        metrics[arm] = {
            "correct": sum(r["correct"] for r in rs), "total": len(rs),
            "accuracy": avg(r["correct"] for r in rs),
            "mean_query_seconds": avg(q["time"] for q in by_arm[arm].values()),
            "request_mean_seconds": avg(r["query_seconds"] for r in rs),
            "request_p50_seconds": quantile([r["query_seconds"] for r in rs], .5),
            "request_p95_seconds": quantile([r["query_seconds"] for r in rs], .95),
            "mean_context_tokens": avg(r["context_tokens"] for r in rs),
            "mean_input_tokens": avg(r["input_tokens"] for r in rs),
            "raw_evidence_recall": avg(r["raw_evidence_recall"] for r in rs),
            "all_raw_evidence": avg(r["all_raw_evidence"] for r in rs),
            "cross_file_query_fraction": avg(r["cross_file_source_count"] > 0 for r in rs),
            "mean_select_seconds": avg(r["select_seconds"] for r in rs),
            "mean_expansion_seconds": avg(r["expansion_seconds"] for r in rs),
            "mean_packing_seconds": avg(r["packing_seconds"] for r in rs),
            "mean_answer_seconds": avg(r["query_seconds"]-r["pre_answer_seconds"] for r in rs),
            "mean_prefill_seconds": avg(sum(r[k]["timings"].get("prompt_ms", 0)/1000 for k in ["selector", "answer_call"]) for r in rs),
            "mean_decode_seconds": avg(sum(r[k]["timings"].get("predicted_ms", 0)/1000 for k in ["selector", "answer_call"]) for r in rs),
            "queries_with_rejected_fragments": sum(bool(r["rejected"]) for r in rs),
            "order_tolerant_accuracy": avg(r["correct"] or (r["failure"] == "wrong_answer" and
                type(r["parsed_answer"]) is list and type(r["expected"]) is list and
                all(type(v) is str for v in r["parsed_answer"] + r["expected"]) and
                len(r["parsed_answer"]) == len(set(r["parsed_answer"])) and
                len(r["expected"]) == len(set(r["expected"])) and
                set(r["parsed_answer"]) == set(r["expected"])) for r in rs),
        }
        for field, destination in [("category", "by_category"), ("project", "by_project")]:
            metrics[arm][destination] = {}
            for label in sorted({r[field] for r in rs}):
                subset = [r for r in rs if r[field] == label]
                tids = {r["task_id"] for r in subset}
                metrics[arm][destination][label] = {
                    "correct": sum(r["correct"] for r in subset), "total": len(subset),
                    "accuracy": avg(r["correct"] for r in subset), "unique_questions": len(tids),
                    "question_equivalent_correct": sum(by_arm[arm][tid]["score"] for tid in tids),
                    "mean_query_seconds": avg(by_arm[arm][tid]["time"] for tid in tids)}
    return {"metrics": metrics, "comparison_B_minus_A": comparison}


def verify(out):
    checks = []
    def check(name, condition, detail=None):
        if not condition:
            raise AssertionError((name, detail))
        checks.append({"check": name, "passed": True, "detail": detail})
    exp.validate_frozen(out)
    check("frozen_source_code_tasks_and_gold", True)
    tasks = {t["id"]: t for t in exp.read(out / "tasks.json") + exp.read(out / "dev_tasks.json")}
    records, dev = rows(out / "results.jsonl"), rows(out / "results_dev.jsonl")
    plan = exp.read(out / "schedule.json")
    check("complete_ordered_576_evaluation_records", len(records) == 576 and
          [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in records] == plan)
    check("development_records_separate", len(dev) == 16)
    check("96_unique_questions_six_projects", len({r["task_id"] for r in records}) == 96 and
          len({r["project"] for r in records}) == 6)
    check("equal_orders_per_project_repeat", all(
        Counter(r["arm"] for i, r in enumerate(records) if i % 2 == 0 and r["project"] == p and r["repeat"] == rep)
        == {"A": 8, "B": 8} for p in {r["project"] for r in records} for rep in range(3)))
    calls = rows(out / "model_calls.jsonl")
    call_map = {c["call_id"]: c for c in calls}
    check("unique_model_call_ids", len(call_map) == len(calls))
    check("no_shared_selectors_or_answers", len({r[k]["call_id"] for r in records + dev
                                                   for k in ["selector", "answer_call"]}) == 1184)
    check("exact_call_logs", all(r[k] == call_map[r[k]["call_id"]] for r in records + dev for k in ["selector", "answer_call"]))
    check("no_transport_errors", all("error" not in c for c in calls))
    check("model_prompt_cache_disabled", all(c["request"]["cache_prompt"] is False and c["timings"].get("cache_n") == 0 for c in calls))
    check("fixed_generation_parameters", all(c["request"]["temperature"] == 0 and c["request"]["seed"] == 1 and
          c["input_tokens"] + c["max_output_tokens"] <= 8192 for c in calls))
    check("call_time_nonoverlap", all(datetime.fromisoformat(a["ended_at_utc"]) <= datetime.fromisoformat(b["started_at_utc"])
                                     for a, b in zip(calls, calls[1:])))
    check("query_time_nonoverlap", all(datetime.fromisoformat(a["ended_at_utc"]) <= datetime.fromisoformat(b["started_at_utc"])
                                      for a, b in zip(records, records[1:])))
    check("physical_query_time_matches_utc", all(abs((datetime.fromisoformat(r["ended_at_utc"]) -
          datetime.fromisoformat(r["started_at_utc"])).total_seconds() - r["query_seconds"]) < .02 for r in records + dev))
    check("independent_typed_grading", all((lambda g: g[0] == r["correct"] and equal(g[1], r["parsed_answer"]) and
          g[2] == r["failure"])(grade(r, tasks[r["task_id"]])) for r in records + dev))
    check("gold_matches_frozen_tasks", all(equal(r["expected"], tasks[r["task_id"]]["expected"]) for r in records + dev))
    check("gold_executed_before_measurement", exp.read(out / "gold_recheck.json")["questions"] == 96 and
          exp.read(out / "gold_recheck.json")["status"] == "PASS")
    assets = exp.read(out / "assets.json")
    strings, ordered_cache = set(), {}
    for r in records + dev:
        t, asset = tasks[r["task_id"]], assets[r["project"]]
        outline = exp.original._candidate_symbol_outline(asset["index"], t["question"], 24)
        assert r["selector"]["prompt"] == exp.original._selector_prompt(t["question"], outline)
        assert r["answer_call"]["prompt"] == exp.original.answer_prompt(t["question"], r["context"])
        for call in [r["selector"], r["answer_call"]]:
            assert call["request"]["prompt"] == exp.original._chat_wrap(call["prompt"])
            strings.add(call["request"]["prompt"])
        key = (r["task_id"], r["repeat"], r["arm"])
        ordered, selected, valid = (exp.audited.baseline_ordered(asset, out / "projects" / r["project"], t, r["selector"])
                                   if r["arm"] == "A" else exp.b_ordered(asset, t, r["selector"]))
        assert selected == r["selected_uri"] and valid == r["selection_valid"]
        ordered_cache[key] = ordered
        chosen = {x["id"] for x in r["chosen"]}
        context, raw = "", set()
        for _, item in ordered:
            if set(item["source_uris"]) <= raw:
                continue
            candidate = context + ("\n\n" if context else "") + item["text"]
            strings.add(candidate)
            if item["id"] in chosen:
                context = candidate
                raw.update(item["source_uris"])
        assert context == r["context"]
        strings.add(context)
        required = set(t["required_uris"])
        assert r["all_raw_evidence"] == (required <= raw)
        assert math.isclose(r["raw_evidence_recall"], len(raw & required) / len(required))
        assert r["unique_source_count"] == len(raw)
        assert r["source_files"] == sorted({asset["nodes"][u]["path"] for u in raw})
        primary_path = asset["nodes"][selected]["path"] if valid else None
        assert r["cross_file_source_count"] == sum(asset["nodes"][u]["path"] != primary_path for u in raw)
    check("exact_prompts_selected_uris_and_reconstructed_contexts", True)
    check("reference_source_coverage_recomputed", True)
    cached_path = out / "offline_token_counts.json"
    text_list = sorted(strings)
    if cached_path.exists():
        cached = exp.read(cached_path)
        assert cached["strings_sha256"] == exp.audited.digest(text_list)
        counts, tokenizer = cached["counts"], cached["tokenizer"]
    else:
        counts, tokenizer = token_audit.tokenize_many(text_list, exp.original.MODEL)
        exp.original.dump(cached_path, {"strings_sha256": exp.audited.digest(text_list), "counts": counts, "tokenizer": tokenizer})
    class CounterClient:
        def tokens(self, text):
            return counts[text]
    for r in records + dev:
        key = (r["task_id"], r["repeat"], r["arm"])
        context, total, chosen, rejected = exp.original.pack(CounterClient(), ordered_cache[key], 1024)
        assert context == r["context"] and total == r["context_tokens"] <= 1024
        assert chosen == r["chosen"] and rejected == r["rejected"]
        assert all(counts[c["request"]["prompt"]] == c["input_tokens"] for c in [r["selector"], r["answer_call"]])
    check("offline_tokenization_and_packing", True, {"distinct_strings": len(strings), "tokenizer": tokenizer})
    summary = exp.read(out / "summary.json")
    checked = 0
    def compare(actual, expected):
        nonlocal checked
        if isinstance(actual, dict):
            for k, value in actual.items():
                compare(value, expected[k])
        elif isinstance(actual, list):
            assert len(actual) == len(expected)
            for x, y in zip(actual, expected):
                compare(x, y)
        else:
            assert math.isclose(actual, expected, abs_tol=1e-9, rel_tol=1e-9), (actual, expected)
            checked += 1
    for population in ["all96", "original48", "additional48"]:
        group = records if population == "all96" else [r for r in records if r["split"] == population]
        compare(independent_stats(group), summary["by_population"][population])
    check("independent_primary_statistics", True, {"numeric_values_checked": checked})
    exp.original.dump(out / "verification.json", {"status": "PASS", "checked_at_utc": exp.audited.now(),
                      "checks": checks, "count": len(checks), "records": len(records),
                      "calls": len(calls), "generation_limit_calls": sum(not c["ok"] for c in calls),
                      "source_hashes": {p.name: exp.original.sha(p) for p in [Path(__file__), out / "summary.json", out / "results.jsonl"]},
                      "limits": ["Local consistency and reproducibility review, not external certification.",
                                 "Context reconstruction reuses the implementation; answer grading and reported primary statistics are independently implemented."]})
    print(json.dumps({"status": "PASS", "checks": len(checks), "records": len(records), "numeric_values_checked": checked}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    verify(parser.parse_args().out)
