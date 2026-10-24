"""A/B results: full paired population plus separately reported question sets."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import mean, median
import sys

sys.dont_write_bytecode = True
import analyze_v2 as statistics
import experiment_ab as exp
from output_diagnostics import order_only_failure


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def metrics(rows):
    m = statistics.metrics(rows)
    m.update({
        "mean_selected_sources": mean(r["unique_source_count"] for r in rows),
        "mean_cross_file_sources": mean(r["cross_file_source_count"] for r in rows),
        "cross_file_query_fraction": mean(r["cross_file_source_count"] > 0 for r in rows),
        "mean_source_files": mean(len(r["source_files"]) for r in rows),
        "selector_accuracy": mean(r["selection_correct"] for r in rows),
        "mean_select_seconds": mean(r["select_seconds"] for r in rows),
        "mean_expansion_seconds": mean(r["expansion_seconds"] for r in rows),
        "mean_packing_seconds": mean(r["packing_seconds"] for r in rows),
        "mean_answer_seconds": mean(r["query_seconds"] - r["pre_answer_seconds"] for r in rows),
        "queries_with_rejected_fragments": sum(bool(r["rejected"]) for r in rows),
        "repeats_accuracy": [mean(r["correct"] for r in rows if r["repeat"] == i) for i in range(3)],
    })
    for field, dest in [("category", "by_category"), ("project", "by_project")]:
        for label, item in m[dest].items():
            group = [r for r in rows if r[field] == label]
            by_question = defaultdict(list)
            for r in group:
                by_question[r["task_id"]].append(r)
            item["mean_query_seconds"] = mean(median(r["query_seconds"] for r in g) for g in by_question.values())
            item["question_equivalent_correct"] = sum(mean(r["correct"] for r in g) for g in by_question.values())
    return m


def comparison_diagnostics(rows):
    pairs = defaultdict(dict)
    for r in rows:
        pairs[(r["task_id"], r["repeat"])][r["arm"]] = r
    assert all(set(p) == {"A", "B"} for p in pairs.values())
    questions = {}
    for (tid, _), pair in pairs.items():
        if tid not in questions:
            questions[tid] = {"task_id": tid, "project": pair["A"]["project"], "category": pair["A"]["category"],
                              "split": pair["A"]["split"], "question": pair["A"]["question"],
                              "expected": pair["A"]["expected"]}
    for tid, q in questions.items():
        for arm in ["A", "B"]:
            group = [r for r in rows if r["task_id"] == tid and r["arm"] == arm]
            first = next(r for r in group if r["repeat"] == 0)
            q[arm] = {"score": mean(r["correct"] for r in group),
                      "seconds": median(r["query_seconds"] for r in group),
                      "context_tokens": mean(r["context_tokens"] for r in group),
                      "answer": first["parsed_answer"], "selected_uri": first["selected_uri"],
                      "sources": sorted({u for x in first["chosen"] for u in x["source_uris"]}),
                      "source_files": first["source_files"], "order_only": order_only_failure(first),
                      "failure": first["failure"]}
        q["delta_score"] = q["B"]["score"] - q["A"]["score"]
    selector_matches = sum(p["A"]["selected_uri"] == p["B"]["selected_uri"] for p in pairs.values())
    return {
        "query_pairs": len(pairs), "same_selector_pairs": selector_matches,
        "selector_agreement": selector_matches / len(pairs),
        "both_correct": sum(q["A"]["score"] == q["B"]["score"] == 1 for q in questions.values()),
        "both_wrong": sum(q["A"]["score"] == q["B"]["score"] == 0 for q in questions.values()),
        "B_wins": [q["task_id"] for q in questions.values() if q["delta_score"] > 0],
        "A_wins": [q["task_id"] for q in questions.values() if q["delta_score"] < 0],
        "questions": sorted(questions.values(), key=lambda q: q["task_id"]),
    }


def analyze(out):
    exp.validate_frozen(out)
    records = read_rows(out / "results.jsonl")
    plan = exp.read(out / "schedule.json")
    assert [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in records] == plan
    assert len(records) == 576
    result = {"status": "COMPLETE", "created_at_utc": exp.audited.now(), "arms": ["A", "B"],
              "questions": 96, "projects": 6, "repeats": 3, "evaluation_answers": len(records),
              "by_population": {}, "inputs": {
                  name: exp.original.sha(out / name) for name in ["results.jsonl", "tasks.json", "protocol.json", "environment.json"]}}
    for name in ["all96", "original48", "additional48"]:
        group = records if name == "all96" else [r for r in records if r["split"] == name]
        result["by_population"][name] = {
            "questions": len({r["task_id"] for r in group}),
            "metrics": {arm: metrics([r for r in group if r["arm"] == arm]) for arm in ["A", "B"]},
            "comparison_B_minus_A": statistics.comparison(group, "B", "A"),
            "paired": comparison_diagnostics(group),
        }
    order = defaultdict(lambda: defaultdict(list))
    for i in range(0, len(records), 2):
        for position, row in enumerate(records[i:i+2]):
            order[row["arm"]][str(position + 1)].append(row["query_seconds"])
    result["order_diagnostics"] = {arm: {pos: {"n": len(values), "mean_seconds": mean(values)}
                                         for pos, values in positions.items()} for arm, positions in order.items()}
    result["measurement_notes"] = [
        "All96 is prespecified; original48 and additional48 are secondary breakdowns, not independent validations.",
        "Repeated requests contribute stability and timing evidence, not 576 independent questions.",
        "Source reference recall is a conservative inclusion metric, not factual sufficiency or answer accuracy.",
        "A and B use different formatting/import presentation as well as different dependency traversal.",
        "Input tokens include actual independently executed selector and answer calls for both arms.",
        "Intervals reflect six known project clusters in one hardware session, not external generalization.",
    ]
    exp.original.dump(out / "summary.json", result)
    print(json.dumps({name: {"metrics": {a: {k: m[k] for k in ["accuracy", "mean_query_seconds", "mean_context_tokens", "unstable_questions"]}
                                           for a, m in r["metrics"].items()}, "difference": r["comparison_B_minus_A"]}
                      for name, r in result["by_population"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    analyze(parser.parse_args().out)
