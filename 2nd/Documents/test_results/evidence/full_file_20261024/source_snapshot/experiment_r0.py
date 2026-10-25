"""Frozen R0 replication on the same 96 questions and three repeats as AB-1.0."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import experiment_ab as ab

original, audited = ab.original, ab.audited
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = original.DEFAULT_OUT / "r0_20261024"
REPORT = original.DEFAULT_OUT.parent / "03_현재색인_A와_파일간확장_B_재실험_비교보고서.md"
CONFIG = {
    "version": "R0-1.0", "arms": ["R0"], "repeats": 3,
    "evidence_cap": 1024, "answer_max_tokens": 128,
    "temperature": 0, "seed": 1, "model_context": 8192, "prompt_cache": False,
    "R0": "Unchanged original raw_items, Retriever and pack: TF-IDF cosine over raw atomic and depth-three dependency bundles; no selector or summaries",
    "schedule": "Reuse AB-1.0 task-repeat block order, one R0 query per block",
    "timing": "Query ranking through answer and call-log write; prebuilt source graph, raw candidates and document vectors excluded; per-query token memoization cleared",
    "primary_population": "Same fixed 96 questions, six known synthetic Python projects; 48+48 breakdowns",
    "primary_quality": "Exact JSON answer value, type, and requested list order",
    "primary_latency": "Across-question mean of within-question median of three measured query times",
    "comparison": "Use preserved AB-1.0 results; R0 measured in a separate session on same model/server configuration; timing differences are descriptive and confounded with session conditions",
    "inference": "Paired six-project cluster bootstrap; repeated runs are not independent questions; two new quality contrasts R0-A and R0-B Holm-adjusted for exploratory sign-flip tests",
    "no_tuning": "No accuracy-based changes to retrieval, prompts, tasks, budgets, model, or examples",
    "cross_file_metric": "Count included source symbols outside task target file, post-retrieval diagnostic only; target never supplied to retrieval",
}


def read(path):
    return json.loads(Path(path).read_text())


def prepare(out):
    assert not (out / "protocol.json").exists(), "Choose a fresh output directory"
    ab.validate_frozen(ab.DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)
    source_inputs = {}
    for name in ["tasks.json", "dev_tasks.json", "gold_operations.json", "results.jsonl",
                 "summary.json", "verification.json", "protocol.json", "environment.json", "schedule.json"]:
        source = ab.DEFAULT_OUT / name
        source_inputs[str(source)] = original.sha(source)
        if name in ["tasks.json", "dev_tasks.json", "gold_operations.json"]:
            shutil.copy2(source, out / name)
    shutil.copytree(ab.DEFAULT_OUT / "projects", out / "projects", dirs_exist_ok=True)
    tasks, dev = read(out / "tasks.json"), read(out / "dev_tasks.json")
    old_assets = read(ab.DEFAULT_OUT / "assets.json")
    assets, preparation = {}, {}
    for project in sorted({t["project"] for t in tasks + dev}):
        root = out / "projects" / project
        for p in root.glob("*.py"):
            source_inputs[str(ab.DEFAULT_OUT / "projects" / project / p.name)] = original.sha(p)
        start = time.perf_counter()
        nodes = original.source_nodes(root)
        graph_time = time.perf_counter() - start
        assert nodes == old_assets[project]["nodes"]
        start = time.perf_counter()
        raw = original.raw_items(nodes)
        raw_time = time.perf_counter() - start
        legacy = read(original.DEFAULT_OUT / "assets" / f"{project}.json")
        assert raw == legacy["raw"], project
        assets[project] = {"nodes": nodes, "raw": raw}
        preparation[project] = {"graph_seconds": graph_time, "raw_candidate_seconds": raw_time,
                                "raw_candidates": len(raw), "scope": "Single warm-filesystem preparation, descriptive only"}
    plan = [{**e, "arm": "R0"} for e in read(ab.DEFAULT_OUT / "schedule.json") if e["arm"] == "A"]
    assert len(plan) == 288
    original.dump(out / "assets.json", assets)
    original.dump(out / "schedule.json", plan)
    original.dump(out / "preparation.json", preparation)
    original.dump(out / "gold_recheck.json", ab.verify_gold(out, tasks, read(out / "gold_operations.json")))
    history = out / "history"
    history.mkdir(exist_ok=True)
    shutil.copy2(REPORT, history / "report_before_R0.md")
    snapshots = out / "source_snapshot"
    snapshots.mkdir(exist_ok=True)
    inputs = list(dict.fromkeys([Path(__file__), *ab.inputs()]))
    for p in inputs:
        shutil.copy2(p, snapshots / p.name)
    original.dump(out / "protocol.json", {
        **CONFIG, "frozen_at_utc": audited.now(), "ab_evidence": str(ab.DEFAULT_OUT),
        "code_hashes": {str(p): original.sha(p) for p in inputs}, "source_input_hashes": source_inputs,
        "frozen_files": {str(p.relative_to(out)): original.sha(p) for p in sorted(out.rglob("*")) if p.is_file()},
    })
    print(json.dumps({"status": "PREPARED", "questions": 96, "planned_answers": 288,
                      "gold_rechecked": 96, "output": str(out)}, ensure_ascii=False), flush=True)


def validate_frozen(out):
    protocol = read(out / "protocol.json")
    assert all(protocol[k] == v for k, v in CONFIG.items())
    for group, root in [("code_hashes", None), ("source_input_hashes", None), ("frozen_files", out)]:
        for name, expected in protocol[group].items():
            assert original.sha(root / name if root else name) == expected, name


def run(out, url, dev=False):
    validate_frozen(out)
    client = audited.AuditedClient(out, url)
    environment = audited.runtime_environment(client)
    assert environment["fingerprint"] == read(ab.DEFAULT_OUT / "environment.json")["fingerprint"], "Environment differs from A/B"
    environment_path = out / "environment.json"
    if environment_path.exists():
        assert read(environment_path)["fingerprint"] == environment["fingerprint"]
    else:
        original.dump(environment_path, environment)
    tasks = read(out / ("dev_tasks.json" if dev else "tasks.json"))
    task_map = {t["id"]: t for t in tasks}
    assets = read(out / "assets.json")
    retrievers, vector_times = {}, {}
    for project, asset in assets.items():
        start = time.perf_counter()
        retriever = original.Retriever(asset["raw"])
        retriever.ranked("", asset["raw"])
        vector_times[project] = time.perf_counter() - start
        retrievers[project] = retriever
    plan = ([{"task_id": t["id"], "repeat": 0, "arm": "R0"} for t in tasks]
            if dev else read(out / "schedule.json"))
    result_path = out / ("results_dev.jsonl" if dev else "results.jsonl")
    prior = audited.rows(result_path)
    assert [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in prior] == plan[:len(prior)]
    session_id = audited.digest([audited.now(), dev])[:20]
    original.dump(out / f"session_{session_id}.json", {"started_at_utc": audited.now(), "dev": dev,
                  "resume_after_rows": len(prior), "environment": environment, "document_vector_build_seconds": vector_times})
    client.reset_query()
    assert client.complete('Return only {"answer":0}.', "warmup", 32, {"session_id": session_id})["ok"]
    for i, entry in enumerate(plan):
        if i < len(prior):
            continue
        task = task_map[entry["task_id"]]
        asset = assets[task["project"]]
        client.reset_query()
        started, started_utc = time.perf_counter(), audited.now()
        ordered = retrievers[task["project"]].ranked(task["question"], asset["raw"])
        retrieval_seconds = time.perf_counter() - started
        packing = time.perf_counter()
        context, token_count, chosen, rejected = original.pack(client, ordered, CONFIG["evidence_cap"])
        packing_seconds = time.perf_counter() - packing
        assert token_count <= CONFIG["evidence_cap"]
        pre_answer_seconds = time.perf_counter() - started
        call = client.complete(original.answer_prompt(task["question"], context), "answer", 128,
                               {**entry, "dev": dev, "session_id": session_id})
        query_seconds, ended_utc = time.perf_counter() - started, audited.now()
        correct, parsed, failure = original.evaluate_answer(call, task["expected"])
        sources = {u for item in chosen for u in item["source_uris"]}
        required = set(task["required_uris"])
        target_path = asset["nodes"][task["target_uri"]]["path"]
        cross_sources = {u for u in sources if asset["nodes"][u]["path"] != target_path}
        row = {**entry, "session_id": session_id, "split": task.get("split", "development"),
               "project": task["project"], "category": task["category"], "question": task["question"],
               "expected": task["expected"], "correct": correct, "parsed_answer": parsed, "failure": failure,
               "selector": None, "selected_uri": None, "selection_valid": None, "selection_correct": None,
               "answer_call": call, "context": context, "context_tokens": token_count,
               "selected_context_tokens": token_count, "chosen": chosen, "rejected": rejected,
               "ranking": [{"id": item["id"], "score": score} for score, item in ordered],
               "query_seconds": query_seconds, "retrieval_seconds": retrieval_seconds,
               "select_seconds": 0, "expansion_seconds": 0, "packing_seconds": packing_seconds,
               "pre_answer_seconds": pre_answer_seconds, "started_at_utc": started_utc, "ended_at_utc": ended_utc,
               "tokenize_http_calls": client.token_http_count, "tokenize_seconds": client.token_seconds,
               "input_tokens": call["input_tokens"], "output_tokens": call["output_tokens"] or 0,
               "raw_evidence_recall": len(sources & required) / len(required) if required else 1,
               "all_raw_evidence": required <= sources, "unique_source_count": len(sources),
               "cross_file_source_count": len(cross_sources), "cross_file_reference_path": target_path,
               "source_files": sorted({asset["nodes"][u]["path"] for u in sources}), "compaction_seconds": 0}
        with result_path.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{'dev' if dev else 'eval'} {i+1}/{len(plan)} {entry['task_id']} R0 r{entry['repeat']} "
              f"correct={int(correct)} tokens={token_count} seconds={query_seconds:.3f}", flush=True)
    original.dump(out / f"completed_{'dev' if dev else 'eval'}.json", {"completed_at_utc": audited.now(),
                  "rows": len(plan), "results_sha256": original.sha(result_path), "session_id": session_id})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "dev", "run"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.out)
    else:
        run(args.out, args.url, args.phase == "dev")
