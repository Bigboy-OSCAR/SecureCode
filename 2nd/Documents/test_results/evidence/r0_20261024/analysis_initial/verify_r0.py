"""Offline R0 audit with independently implemented ranking, packing and statistics."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import experiment_r0 as exp
import audit_v2 as independent
import verify_ab as ab_check


def verify(out):
    checks = []
    def check(name, condition, detail=None):
        assert condition, (name, detail)
        checks.append({"check": name, "passed": True, "detail": detail})
    exp.validate_frozen(out)
    exp.ab.validate_frozen(exp.ab.DEFAULT_OUT)
    check("frozen_source_code_tasks_gold_and_AB_inputs", True)
    tasks = {t["id"]: t for t in exp.read(out / "tasks.json") + exp.read(out / "dev_tasks.json")}
    records, dev = exp.audited.rows(out / "results.jsonl"), exp.audited.rows(out / "results_dev.jsonl")
    old = exp.audited.rows(exp.ab.DEFAULT_OUT / "results.jsonl")
    check("complete_ordered_288_R0_answers", len(records) == 288 and
          [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in records] == exp.read(out / "schedule.json"))
    check("same_96_questions_three_repeats", Counter(r["task_id"] for r in records) == {t["id"]: 3 for t in exp.read(out / "tasks.json")} and
          exp.read(out / "tasks.json") == exp.read(exp.ab.DEFAULT_OUT / "tasks.json"))
    check("development_eight_answers_separate", len(dev) == 8 and not ({r["task_id"] for r in dev} & {r["task_id"] for r in records}))
    calls = exp.audited.rows(out / "model_calls.jsonl")
    call_map = {c["call_id"]: c for c in calls}
    check("one_real_answer_per_query_no_selector", len(call_map) == len(calls) == 298 and
          Counter(c["purpose"] for c in calls) == {"answer": 296, "warmup": 2} and
          len({r["answer_call"]["call_id"] for r in records+dev}) == 296 and
          all(r["selector"] is None for r in records+dev))
    check("exact_call_logs", all(r["answer_call"] == call_map[r["answer_call"]["call_id"]] for r in records+dev))
    check("same_model_binary_server_fingerprint", exp.read(out / "environment.json")["fingerprint"] ==
          exp.read(exp.ab.DEFAULT_OUT / "environment.json")["fingerprint"])
    check("no_transport_errors", all("error" not in c for c in calls))
    check("model_prompt_cache_disabled", all(c["request"]["cache_prompt"] is False and c["timings"].get("cache_n") == 0 for c in calls))
    check("fixed_generation_parameters", all(c["request"]["temperature"] == 0 and c["request"]["seed"] == 1 and
          c["input_tokens"] + c["max_output_tokens"] <= 8192 and
          c["request"]["n_predict"] == (32 if c["purpose"] == "warmup" else 128) for c in calls))
    check("call_time_nonoverlap", all(datetime.fromisoformat(a["ended_at_utc"]) <= datetime.fromisoformat(b["started_at_utc"])
          for a, b in zip(calls, calls[1:])))
    check("query_time_nonoverlap", all(datetime.fromisoformat(a["ended_at_utc"]) <= datetime.fromisoformat(b["started_at_utc"])
          for a, b in zip(records, records[1:])))
    check("physical_query_time_and_phases", all(abs((datetime.fromisoformat(r["ended_at_utc"]) -
          datetime.fromisoformat(r["started_at_utc"])).total_seconds() - r["query_seconds"]) < .02 and
          0 < r["retrieval_seconds"] + r["packing_seconds"] <= r["pre_answer_seconds"] < r["query_seconds"]
          for r in records+dev))
    check("independent_typed_grading", all((lambda g: g[0] == r["correct"] and ab_check.equal(g[1], r["parsed_answer"]) and
          g[2] == r["failure"])(ab_check.grade({**r, "selection_valid": True}, tasks[r["task_id"]])) for r in records+dev))
    check("gold_matches_frozen_tasks", all(ab_check.equal(r["expected"], tasks[r["task_id"]]["expected"]) for r in records+dev))
    check("all_96_gold_answers_reexecuted_before_measurement", exp.read(out / "gold_recheck.json")["questions"] == 96 and
          exp.read(out / "gold_recheck.json")["status"] == "PASS")
    assets = exp.read(out / "assets.json")
    for project, asset in assets.items():
        nodes = independent.source_graph(out / "projects" / project)
        assert nodes == asset["nodes"] and independent.raw_from_nodes(nodes) == asset["raw"]
    check("independent_graph_and_raw_candidate_reconstruction", True)
    strings, ranked_cache = set(), {}
    per_query_strings = {}
    for r in records+dev:
        t, asset = tasks[r["task_id"]], assets[r["project"]]
        if r["task_id"] not in ranked_cache:
            ranked_cache[r["task_id"]] = independent.rank(t["question"], asset["raw"], asset["raw"])
        ranked = ranked_cache[r["task_id"]]
        assert len(ranked) == len(r["ranking"])
        assert all(item["id"] == saved["id"] and math.isclose(score, saved["score"], abs_tol=1e-12)
                   for (score,item), saved in zip(ranked,r["ranking"]))
        call = r["answer_call"]
        assert call["prompt"] == independent.answer_prompt(t["question"], r["context"])
        assert call["request"]["prompt"] == independent.wrap(call["prompt"])
        query_strings = {call["request"]["prompt"]}
        selected = {x["id"] for x in r["chosen"]}
        context, sources = "", set()
        for _, item in ranked:
            if set(item["source_uris"]) <= sources:
                continue
            candidate = context + ("\n\n" if context else "") + item["text"]
            query_strings.add(candidate)
            if item["id"] in selected:
                context = candidate
                sources.update(item["source_uris"])
        assert context == r["context"]
        assert len(query_strings) == r["tokenize_http_calls"]
        per_query_strings[r["task_id"]] = query_strings
        strings.update(query_strings)
        strings.add(context)
        required = set(t["required_uris"])
        assert r["all_raw_evidence"] == (required <= sources)
        assert math.isclose(r["raw_evidence_recall"], len(sources & required)/len(required))
        assert r["unique_source_count"] == len(sources)
        assert r["source_files"] == sorted({asset["nodes"][u]["path"] for u in sources})
        target_path = asset["nodes"][t["target_uri"]]["path"]
        assert r["cross_file_reference_path"] == target_path
        assert r["cross_file_source_count"] == sum(asset["nodes"][u]["path"] != target_path for u in sources)
    check("independent_TFIDF_ranking_and_exact_prompts", True)
    check("source_coverage_and_per_query_token_calls", True)
    text_list = sorted(strings)
    cached_path = out / "offline_token_counts.json"
    if cached_path.exists():
        cache = exp.read(cached_path)
        assert cache["strings_sha256"] == exp.audited.digest(text_list)
        counts, tokenizer = cache["counts"], cache["tokenizer"]
    else:
        counts, tokenizer = independent.tokenize_many(text_list, exp.original.MODEL)
        exp.original.dump(cached_path, {"strings_sha256": exp.audited.digest(text_list), "counts": counts, "tokenizer": tokenizer})
    for r in records+dev:
        text, sources, chosen, rejected = "", set(), [], []
        for score,item in ranked_cache[r["task_id"]]:
            if set(item["source_uris"]) <= sources:
                continue
            candidate = text + ("\n\n" if text else "") + item["text"]
            if counts[candidate] <= 1024:
                chosen.append({"id": item["id"], "level": 0, "score": score, "source_uris": item["source_uris"]})
                text = candidate
                sources.update(item["source_uris"])
            else:
                rejected.append(item["id"])
        assert chosen == r["chosen"] and rejected == r["rejected"]
        assert text == r["context"] and counts[text] == r["context_tokens"] <= 1024
        c = r["answer_call"]
        assert counts[c["request"]["prompt"]] == c["input_tokens"] == r["input_tokens"]
        assert r["output_tokens"] == c["output_tokens"]
    check("independent_offline_tokenization_and_packing", True, {"distinct_strings": len(strings), "tokenizer": tokenizer})
    check("server_reported_token_counts", all(c["input_tokens"] == c["timings"].get("prompt_n") and
          c["output_tokens"] == c["timings"].get("predicted_n") for c in calls))
    summary = exp.read(out / "summary.json")
    old_summary = exp.read(exp.ab.DEFAULT_OUT / "summary.json")
    checked = 0
    def compare(actual, expected):
        nonlocal checked
        if isinstance(actual, dict):
            for k,v in actual.items():
                compare(v, expected[k])
        elif isinstance(actual, list):
            assert len(actual) == len(expected)
            for x,y in zip(actual,expected):
                compare(x,y)
        else:
            assert math.isclose(actual,expected,abs_tol=1e-9,rel_tol=1e-9), (actual,expected)
            checked += 1
    for pop in ["all96", "original48", "additional48"]:
        target = summary["by_population"][pop]
        assert all(target["metrics"][a] == old_summary["by_population"][pop]["metrics"][a] for a in ["A", "B"])
        assert target["comparisons"]["B-A"] == old_summary["by_population"][pop]["comparison_B_minus_A"]
        for base in ["A", "B"]:
            group = [r for r in old+records if r["arm"] in [base,"R0"] and (pop == "all96" or r["split"] == pop)]
            # The independent AB formulas accept two arm names. Rename only for calculation,
            # representing R0's absent selector by zero timing, not an invented model call.
            remapped = [{**r, "arm": "B" if r["arm"] == "R0" else "A",
                         "selector": r["selector"] or {"timings": {}}} for r in group]
            computed = ab_check.independent_stats(remapped)
            compare(computed["metrics"]["A"], target["metrics"][base])
            compare(computed["metrics"]["B"], target["metrics"]["R0"])
            compare(computed["comparison_B_minus_A"], target["comparisons"][f"R0-{base}"])
        ordered = sorted(["R0-A", "R0-B"], key=lambda k: target["comparisons"][k]["unadjusted_project_signflip_p"])
        previous = 0
        for i,key in enumerate(ordered):
            previous = max(previous,min(1,(2-i)*target["comparisons"][key]["unadjusted_project_signflip_p"]))
            compare(previous,target["comparisons"][key]["holm_p_two_new_quality_contrasts"])
    check("AB_statistics_preserved_exactly", True)
    check("independent_primary_statistics_and_new_contrasts", True, {"numeric_values_checked": checked})
    exp.original.dump(out / "verification.json", {"status": "PASS", "checked_at_utc": exp.audited.now(),
        "count": len(checks), "checks": checks, "records": len(records), "calls": len(calls),
        "generation_limit_calls": sum(not c["ok"] for c in calls),
        "source_hashes": {p.name: exp.original.sha(p) for p in [Path(__file__), out / "summary.json", out / "results.jsonl"]},
        "limits": ["Local verification, not independent external certification.",
                   "Code graph, TF-IDF ranking, packing, typed grading and primary statistics independently reconstructed; offline tokenizer uses same model vocabulary.",
                   "R0 measured in separate session; verification does not remove environmental confounding."]})
    print(json.dumps({"status": "PASS", "checks": len(checks), "records": len(records), "numeric_values_checked": checked}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    verify(p.parse_args().out)
