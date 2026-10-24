"""Derive all report numbers from immutable per-call and per-question records."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import itertools
import json
import math
from pathlib import Path
from statistics import mean, median
import argparse


def quantile(values, p):
    values = sorted(values)
    index = (len(values) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def time_break_even(setup_difference, query_saving):
    """Queries needed to recover RH's extra setup, at the measured query mix."""
    return math.ceil(max(0, setup_difference) / query_saving) if query_saving > 0 else None


def per_question(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["task_id"]].append(row)
    return {
        task: {
            "score": mean(r["correct"] for r in records),
            "seconds": median(r["query_seconds"] for r in records),
            "project": records[0]["project"], "category": records[0]["category"],
        } for task, records in groups.items()
    }


def metrics(rows):
    result = {}
    for arm in sorted({r["arm"] for r in rows}):
        group = [r for r in rows if r["arm"] == arm]
        questions = per_question(group)
        times = [q["seconds"] for q in questions.values()]
        cats, projects = {}, {}
        for field, output in [("category", cats), ("project", projects)]:
            for value in sorted({r[field] for r in group}):
                selected = [r for r in group if r[field] == value]
                output[value] = {
                    "accuracy": mean(r["correct"] for r in selected),
                    "correct": sum(r["correct"] for r in selected), "total": len(selected),
                    "unique_questions": len({r["task_id"] for r in selected}),
                }
        result[arm] = {
            "accuracy": mean(r["correct"] for r in group),
            "correct": sum(r["correct"] for r in group), "total": len(group),
            "unique_questions": len(questions),
            "repeats_accuracy": [
                mean(r["correct"] for r in group if r["repeat"] == repeat)
                for repeat in sorted({r["repeat"] for r in group})
            ],
            "unstable_questions": sum(0 < q["score"] < 1 for q in questions.values()),
            "mean_input_tokens": mean(r["input_tokens"] for r in group),
            "mean_output_tokens": mean(r["output_tokens"] for r in group),
            "mean_context_tokens": mean(r["context_tokens"] for r in group),
            "mean_query_seconds": mean(times),
            "median_query_seconds": median(times), "p95_query_seconds": quantile(times, .95),
            "raw_evidence_recall": mean(r["raw_evidence_recall"] for r in group),
            "all_raw_evidence": mean(r["all_raw_evidence"] for r in group),
            "failure_counts": dict(Counter(r["failure"] for r in group if r["failure"])),
            "by_category": cats, "by_project": projects,
            "level_use": {
                str(level): mean(any(c["level"] == level for c in r["chosen"]) for r in group)
                for level in range(4)
            },
            "selection_accuracy": mean(r["selection_correct"] for r in group) if arm in ("A", "B") else None,
        }
    return result


def compare(rows, higher, base):
    h = per_question([r for r in rows if r["arm"] == higher])
    b = per_question([r for r in rows if r["arm"] == base])
    shared = sorted(set(h) & set(b))
    if not shared:
        return None
    projects = sorted({h[t]["project"] for t in shared})
    project_deltas = [
        mean(h[t]["score"] - b[t]["score"] for t in shared if h[t]["project"] == project)
        for project in projects
    ]
    # Cluster bootstrap over all ordered draws of six projects. No random Monte Carlo error.
    bootstrap = [
        mean(project_deltas[i] for i in sample)
        for sample in itertools.product(range(len(projects)), repeat=len(projects))
    ]
    delta = mean(h[t]["score"] - b[t]["score"] for t in shared)
    flips = [
        abs(mean(sign * value for sign, value in zip(signs, project_deltas)))
        for signs in itertools.product([-1, 1], repeat=len(projects))
    ]
    p = sum(v >= abs(delta) - 1e-12 for v in flips) / len(flips)
    base_accuracy = mean(b[t]["score"] for t in shared)
    both = [t for t in shared if h[t]["score"] == 1 and b[t]["score"] == 1]
    h_time, b_time = mean(h[t]["seconds"] for t in shared), mean(b[t]["seconds"] for t in shared)
    h_input = mean(r["input_tokens"] for r in rows if r["arm"] == higher)
    b_input = mean(r["input_tokens"] for r in rows if r["arm"] == base)
    return {
        "higher": higher, "base": base, "delta_pp": 100 * delta,
        "ci95_pp": [100*quantile(bootstrap, .025), 100*quantile(bootstrap, .975)],
        "project_deltas_pp": dict(zip(projects, [100*d for d in project_deltas])),
        "win": sum(h[t]["score"] > b[t]["score"] for t in shared),
        "loss": sum(h[t]["score"] < b[t]["score"] for t in shared),
        "tie": sum(h[t]["score"] == b[t]["score"] for t in shared),
        "p_value": p,
        "relative_accuracy_change_pct": 100*delta/base_accuracy if base_accuracy else None,
        "error_reduction_pct": 100*delta/(1-base_accuracy) if base_accuracy < 1 else None,
        "mean_latency_delta_seconds": mean(h[t]["seconds"] - b[t]["seconds"] for t in shared),
        "query_time_reduction_pct": 100*(1-h_time/b_time),
        "input_token_change_pct": 100*(h_input/b_input-1),
        "both_success_n": len(both),
        "both_success_latency_ratio": (
            mean(h[t]["seconds"] for t in both) / mean(b[t]["seconds"] for t in both)
        ) if both else None,
        "bootstrap_resamples": len(bootstrap), "cluster_count": len(projects),
    }


def analyze(out):
    rows = read_rows(out / "results_eval_main.jsonl")
    if not rows:
        raise ValueError("No evaluation data")
    task_rows = json.loads((out / "dataset/eval_tasks.json").read_text())
    tasks = {t["id"]: t for t in task_rows}
    expected_keys = {(t["id"], a, repeat) for t in task_rows for a in ["A", "B", "R0", "RF", "RH"] for repeat in range(3)}
    actual_keys = [(r["task_id"], r["arm"], r["repeat"]) for r in rows]
    if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != expected_keys:
        raise ValueError(f"Incomplete/duplicate evaluation: rows={len(actual_keys)}, expected={len(expected_keys)}")
    stats = metrics(rows)
    comparisons = {
        f"{h}-{b}": compare(rows, h, b)
        for h, b in [("RH", "A"), ("B", "A"), ("RH", "R0"), ("RF", "R0"), ("RH", "RF")]
    }
    # Two planned key comparisons; adjusted p prevents treating a search across arms as one test.
    planned = sorted(["RH-A", "RH-R0"], key=lambda key: comparisons[key]["p_value"])
    running_max = 0
    for rank, key in enumerate(planned):
        running_max = max(running_max, min(1, comparisons[key]["p_value"] * (2-rank)))
        comparisons[key]["holm_adjusted_p_two_planned"] = running_max
    assets = {p.stem: json.loads(p.read_text()) for p in (out / "assets").glob("eval_*.json")}
    build_projects = {}
    for project, asset in assets.items():
        path = out / "assets" / f"{project}.json"
        build_projects[project] = {
            "seconds": asset["build_seconds"], "input_tokens": asset["build_input_tokens"],
            "output_tokens": asset["build_output_tokens"], "model_seconds": asset["build_model_seconds"],
            "summary_count": len(asset["summaries"]), "source_node_count": len(asset["nodes"]),
            "retrieval_raw_candidates": len(asset["raw"]), "storage_bytes": path.stat().st_size,
            "summary_text_bytes": sum(len(s["text"].encode()) for s in asset["summaries"]),
        }
    build = {
        "projects": build_projects,
        "seconds": sum(p["seconds"] for p in build_projects.values()),
        "input_tokens": sum(p["input_tokens"] for p in build_projects.values()),
        "output_tokens": sum(p["output_tokens"] for p in build_projects.values()),
        "mean_project_seconds": mean(p["seconds"] for p in build_projects.values()),
        "mean_project_input_tokens": mean(p["input_tokens"] for p in build_projects.values()),
        "mean_project_output_tokens": mean(p["output_tokens"] for p in build_projects.values()),
        "summary_count": sum(p["summary_count"] for p in build_projects.values()),
        "summary_text_bytes": sum(p["summary_text_bytes"] for p in build_projects.values()),
    }
    calls = read_rows(out / "model_calls.jsonl")
    stage_costs = defaultdict(lambda: {"seconds": 0., "input_tokens": 0, "output_tokens": 0, "calls": 0})
    for call in calls:
        if call["purpose"].startswith("build") and call["meta"].get("project", "").startswith("eval_"):
            cost = stage_costs[call["purpose"]]
            cost["seconds"] += call["wall_seconds"]
            cost["input_tokens"] += call["input_tokens"]
            cost["output_tokens"] += call["output_tokens"] or 0
            cost["calls"] += 1
    build["by_stage"] = dict(stage_costs)
    preprocessing_path = out / "preprocessing_costs.json"
    preprocessing = json.loads(preprocessing_path.read_text()) if preprocessing_path.exists() else []
    build["mean_symbol_index_seconds"] = mean(p["symbol_index_seconds"] for p in preprocessing) if preprocessing else None
    build["mean_raw_index_seconds"] = mean(p["graph_raw_retrieval_index_seconds"] for p in preprocessing) if preprocessing else None
    a, rh = stats["A"], stats["RH"]
    savings = a["mean_query_seconds"] - rh["mean_query_seconds"]
    token_savings = a["mean_input_tokens"] - rh["mean_input_tokens"]
    a_setup = build["mean_symbol_index_seconds"] or 0
    r0_setup = build["mean_raw_index_seconds"] or 0
    build["extra_setup_seconds_per_project_vs_A"] = build["mean_project_seconds"] - a_setup
    build["extra_setup_seconds_per_project_vs_R0"] = build["mean_project_seconds"] - r0_setup
    build["time_break_even_questions_per_project_vs_A"] = time_break_even(
        build["extra_setup_seconds_per_project_vs_A"], savings
    )
    build["input_token_break_even_questions_per_project_vs_A"] = (
        math.ceil(build["mean_project_input_tokens"]/token_savings) if token_savings > 0 else None
    )
    savings_r0 = stats["R0"]["mean_query_seconds"] - rh["mean_query_seconds"]
    build["time_break_even_questions_per_project_vs_R0"] = time_break_even(
        build["extra_setup_seconds_per_project_vs_R0"], savings_r0
    )
    build["break_even_basis"] = (
        "Per average project: ceil(max(0, RH setup minus comparator setup) / "
        "(comparator query seconds minus RH query seconds)); only when query saving is positive. "
        "Setup and query costs use the same units as cost_scenarios. "
        "Extrapolates the measured equal-project question mix; not a six-project total."
    )
    scenarios = []
    for n in [1, 10, 100]:
        scenarios.append({
            "questions_per_project": n, "A_seconds": a_setup + n*a["mean_query_seconds"],
            "RH_seconds": build["mean_project_seconds"] + n*rh["mean_query_seconds"],
            "A_input_tokens": n*a["mean_input_tokens"],
            "RH_input_tokens": build["mean_project_input_tokens"] + n*rh["mean_input_tokens"],
            "A_output_tokens": n*a["mean_output_tokens"],
            "RH_output_tokens": build["mean_project_output_tokens"] + n*rh["mean_output_tokens"],
        })
    sensitivity = read_rows(out / "results_eval_budget512.jsonl")
    sensitivity_expected = {(t["id"], arm, 0) for t in task_rows for arm in ["R0", "RH"]}
    sensitivity_actual = [(r["task_id"], r["arm"], r["repeat"]) for r in sensitivity]
    if len(sensitivity_actual) != len(set(sensitivity_actual)) or set(sensitivity_actual) != sensitivity_expected:
        raise ValueError("Incomplete/duplicate 512-token sensitivity run")
    sensitivity_analysis = {
        "budget": 512, "repeats": 1, "total_rows": len(sensitivity),
        "metrics_by_arm": metrics(sensitivity),
        "comparison_RH_R0": compare(sensitivity, "RH", "R0"),
    }
    if len(sensitivity) != len(tasks)*2:
        raise ValueError("Incomplete 512-token sensitivity run")
    per_arm = {arm: per_question([r for r in rows if r["arm"] == arm]) for arm in stats}
    cases = []
    # Explain gains and regressions, favour summary-specific contrasts and diverse categories.
    candidates = []
    for tid, task in tasks.items():
        scores = {arm: per_arm[arm][tid]["score"] for arm in per_arm}
        if scores["RH"] != scores["R0"]:
            priority = 0 if scores["RH"] < scores["R0"] else 1
        elif scores["RH"] != scores["A"]:
            priority = 2
        elif scores["RH"] < 1:
            priority = 3
        else:
            continue
        candidates.append((priority, tid))
    for priority, tid in sorted(candidates)[:10]:
        task = tasks[tid]
        sample = {r["arm"]: r for r in rows if r["task_id"] == tid and r["repeat"] == 0}
        cases.append({
            "task_id": tid, "project": task["project"], "category": task["category"],
            "question": task["question"], "expected": task["expected"],
            "answers": {arm: r["parsed_answer"] for arm, r in sample.items()},
            "scores": {arm: per_arm[arm][tid]["score"] for arm in per_arm},
            "selected_nodes": {arm: [c["id"] for c in r["chosen"]] for arm, r in sample.items()},
            "contexts": {arm: r["context"] for arm, r in sample.items()},
        })
    budget_violations = [r["task_id"] for r in rows + sensitivity if r["context_tokens"] > r["budget"]]
    measured_calls = {r["answer_call"]["call_id"]: r["answer_call"] for r in rows + sensitivity}
    for r in rows:
        if r.get("selector"):
            measured_calls[r["selector"]["call_id"]] = r["selector"]
    cache_used = [c["call_id"] for c in measured_calls.values() if c.get("timings", {}).get("cache_n", 0) != 0]
    integrity = {
        "main_rows": len(rows), "main_unique_questions": len(tasks), "main_projects": len(assets),
        "sensitivity_rows": len(sensitivity), "budget_violations": budget_violations,
        "nonzero_prompt_cache_calls": cache_used,
        "physical_main_and_sensitivity_model_calls": len(measured_calls),
        "logical_main_model_calls": sum(1+bool(r["selector"]) for r in rows),
        "execution_failures": sum(not r["answer_call"]["ok"] for r in rows),
    }
    summary = {
        "date": "2026-10-20", "metrics_by_arm": stats, "comparisons": comparisons,
        "build": build, "cost_scenarios": scenarios, "sensitivity": sensitivity_analysis,
        "failure_cases": cases, "integrity": integrity,
        "caveats": [
            "6 small synthetic Python projects; distinct core algorithms but a shared policy/rules/service layout and distractor modules.",
            "48 unique English questions, 3 repeated deterministic runs. Repeats are not independent samples.",
            "RAPTOR-inspired code adaptation: dependency/file grouping and sparse TF-IDF, not original SBERT/UMAP/GMM.",
            "Existing A selection/bundle functions reused; common JSON answer prompt and equal context cap added.",
            "Conservative reference lists are not minimal required evidence, and summary lineage does not prove fact preservation.",
            "No production repositories, Korean-query evaluation, code patching, stale-summary update test, or scale-up test.",
            "Cluster intervals with only six projects are exploratory; model/algorithm choices are not universal.",
            "Prebuilt corpus routing is known; finding the correct project among many repositories is not tested.",
            "Online time includes local tokenizer/HTTP and retrieval; shared selector full cost attributed to A and B.",
            "Cost scenarios are extrapolations from measured average per-project setup and per-query time, not new N-query runs.",
        ],
    }
    (out / "analysis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    fields = ["task_id", "project", "category", "arm", "repeat", "budget", "correct",
              "failure", "input_tokens", "output_tokens", "context_tokens", "query_seconds",
              "raw_evidence_recall", "all_raw_evidence"]
    with (out / "per_question_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows + sensitivity)
    print(json.dumps({
        "accuracy": {a: s["accuracy"] for a, s in stats.items()},
        "comparisons": comparisons, "build": {k: v for k, v in build.items() if k != "projects"},
        "integrity": integrity,
    }, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "Documents/test_results/evidence")
    args = parser.parse_args()
    analyze(args.out)
