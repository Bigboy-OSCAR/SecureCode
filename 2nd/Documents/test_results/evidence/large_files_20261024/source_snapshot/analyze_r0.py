"""Combine fresh R0 results with preserved A/B results; keep session caveat explicit."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean, median
import sys
sys.dont_write_bytecode = True
import experiment_r0 as exp
import analyze_v2 as stats
from output_diagnostics import order_only_failure


def metrics(rows):
    m = stats.metrics(rows)
    m.update({
        "mean_selected_sources": mean(r["unique_source_count"] for r in rows),
        "mean_cross_file_sources": mean(r["cross_file_source_count"] for r in rows),
        "cross_file_query_fraction": mean(r["cross_file_source_count"] > 0 for r in rows),
        "mean_source_files": mean(len(r["source_files"]) for r in rows),
        "selector_accuracy": None, "mean_select_seconds": 0, "mean_expansion_seconds": 0,
        "mean_retrieval_seconds": mean(r["retrieval_seconds"] for r in rows),
        "mean_packing_seconds": mean(r["packing_seconds"] for r in rows),
        "mean_answer_seconds": mean(r["query_seconds"] - r["pre_answer_seconds"] for r in rows),
        "queries_with_rejected_fragments": sum(bool(r["rejected"]) for r in rows),
        "repeats_accuracy": [mean(r["correct"] for r in rows if r["repeat"] == i) for i in range(3)],
    })
    for field, dest in [("category", "by_category"), ("project", "by_project")]:
        for label, item in m[dest].items():
            questions = defaultdict(list)
            for r in rows:
                if r[field] == label:
                    questions[r["task_id"]].append(r)
            item["mean_query_seconds"] = mean(median(r["query_seconds"] for r in g) for g in questions.values())
            item["question_equivalent_correct"] = sum(mean(r["correct"] for r in g) for g in questions.values())
    return m


def analyze(out):
    exp.validate_frozen(out)
    fresh = exp.audited.rows(out / "results.jsonl")
    old = exp.audited.rows(exp.ab.DEFAULT_OUT / "results.jsonl")
    records = old + fresh
    assert len(fresh) == 288 and len(old) == 576
    assert [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in fresh] == exp.read(out / "schedule.json")
    baseline = exp.read(exp.ab.DEFAULT_OUT / "summary.json")
    result = {"status": "COMPLETE", "created_at_utc": exp.audited.now(), "arms": ["A", "B", "R0"],
              "unique_questions": 96, "repeats": 3, "fresh_R0_answers": 288, "preserved_AB_answers": 576,
              "comparison_design": "Same fixed questions and environment, separate R0 session; latency differences descriptive, no control of session effects",
              "by_population": {}, "inputs": {str(p): exp.original.sha(p) for p in [
                  out / "results.jsonl", out / "protocol.json", out / "environment.json",
                  exp.ab.DEFAULT_OUT / "results.jsonl", exp.ab.DEFAULT_OUT / "summary.json"]}}
    for pop in ["all96", "original48", "additional48"]:
        group = records if pop == "all96" else [r for r in records if r["split"] == pop]
        oldpop = baseline["by_population"][pop]
        comparisons = {"B-A": oldpop["comparison_B_minus_A"],
                       **{f"R0-{b}": stats.comparison(group, "R0", b) for b in ["A", "B"]}}
        previous = 0
        for i, key in enumerate(sorted(["R0-A", "R0-B"], key=lambda k: comparisons[k]["unadjusted_project_signflip_p"])):
            previous = max(previous, min(1, (2-i) * comparisons[key]["unadjusted_project_signflip_p"]))
            comparisons[key]["holm_p_two_new_quality_contrasts"] = previous
            comparisons[key]["latency_interpretation"] = "Separate sessions: conditional intervals do not include session drift; not a causal speed estimate"
        result["by_population"][pop] = {
            "questions": oldpop["questions"],
            "metrics": {**oldpop["metrics"], "R0": metrics([r for r in group if r["arm"] == "R0"])},
            "comparisons": comparisons,
        }
    questions = defaultdict(lambda: defaultdict(list))
    for r in records:
        questions[r["task_id"]][r["arm"]].append(r)
    result["questions"] = []
    for tid, arms in sorted(questions.items()):
        a = arms["A"][0]
        entry = {k: a[k] for k in ["task_id", "project", "category", "split", "question", "expected"]}
        entry["arms"] = {}
        for arm, group in arms.items():
            first = next(r for r in group if r["repeat"] == 0)
            entry["arms"][arm] = {"score": mean(r["correct"] for r in group),
                "seconds": median(r["query_seconds"] for r in group), "answer": first["parsed_answer"],
                "context_tokens": first["context_tokens"], "source_files": first["source_files"],
                "sources": sorted({u for item in first["chosen"] for u in item["source_uris"]}),
                "order_only": order_only_failure(first), "failure": first["failure"]}
        result["questions"].append(entry)
    result["measurement_notes"] = [
        "All 96 fixed questions were repeated three times per arm; independent units are questions nested in six projects.",
        "A/B metrics and their original paired comparison are preserved exactly.",
        "R0 uses raw original code plus prebuilt dependency bundles; it is neither full-file grep nor RAPTOR summaries.",
        "Source coverage is a diagnostic against required_uris; retrieval never receives targets or gold answers.",
        "R0 cross-file count is relative to task target file; A/B counts are relative to actual selected file, so not a fully identical auxiliary measure.",
        "No adjustment changes the primary exact-match score; order-tolerant scoring is supplementary.",
    ]
    exp.original.dump(out / "summary.json", result)
    print(json.dumps({pop: {"R0": {k: data["metrics"]["R0"][k] for k in [
        "correct", "accuracy", "mean_query_seconds", "mean_context_tokens", "unstable_questions"]},
        "comparisons": data["comparisons"]} for pop, data in result["by_population"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    analyze(p.parse_args().out)
