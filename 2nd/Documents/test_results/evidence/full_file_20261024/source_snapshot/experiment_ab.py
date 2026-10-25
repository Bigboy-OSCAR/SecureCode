"""Fresh A/B measurement; existing reports and experiment inputs are read-only."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import shutil
import sys
import time

sys.dont_write_bytecode = True
import experiment as original
import experiment_v2 as audited
import preflight_v2 as gold_audit

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = original.DEFAULT_OUT / "ab_20261024"
CONFIG = {
    "version": "AB-1.0", "arms": ["A", "B"], "repeats": 3,
    "evidence_cap": 1024, "selector_candidates": 24,
    "selector_max_tokens": 96, "answer_max_tokens": 128,
    "temperature": 0, "seed": 1, "order_seed": 20261024,
    "model_context": 8192, "prompt_cache": False,
    "selector_policy": "Independent real selector call for every A and B query; no shared inference",
    "A": "Unchanged native same-file expansion, dependency_depth=1 (two rounds), max_symbols=8",
    "B": "Unchanged original baseline_cross_file_members: two rounds, max_functions=8; imports and original headers retained",
    "timing": "Physical query wall time from outline construction through answer and small call-log write; preparation, model loading, grading and result-row write excluded",
    "schedule": "For each repeat and project: 8 A-first and 8 B-first pairs; all 96 task-pair blocks shuffled",
    "primary_population": "All fixed 96 questions on six known synthetic projects; original and additional 48-question sets also reported separately",
    "primary_quality": "Exact JSON answer value, type, and requested list order",
    "primary_latency": "Across-question mean of within-question median of three measured query times",
    "inference": "Paired six-project cluster bootstrap, all 6^6 resamples; exploratory sign-flip test; no independent repository generalization",
    "selection_bias_note": "All questions and projects existed before this rerun; this is replication, not an unseen holdout",
    "no_tuning": "No accuracy-based changes to retrieval, prompts, questions, budgets or model",
}


def read(path):
    return json.loads(Path(path).read_text())


def inputs():
    return [Path(__file__), Path(original.__file__), Path(audited.__file__),
            Path(gold_audit.__file__),
            original.REPO / "1st/symbol_test/symbol_bench/indexer.py",
            original.REPO / "1st/symbol_test/symbol_bench/run_benchmark.py"]


def make_plan(tasks):
    rng = random.Random(CONFIG["order_seed"])
    plan = []
    for repeat in range(CONFIG["repeats"]):
        blocks = []
        for project in sorted({t["project"] for t in tasks}):
            selected = sorted((t for t in tasks if t["project"] == project), key=lambda t: t["id"])
            assert len(selected) == 16
            rng.shuffle(selected)
            orders = [("A", "B")] * 8 + [("B", "A")] * 8
            rng.shuffle(orders)
            blocks.extend((t, order) for t, order in zip(selected, orders))
        rng.shuffle(blocks)
        for task, order in blocks:
            plan.extend({"task_id": task["id"], "repeat": repeat, "arm": arm} for arm in order)
    return plan


def verify_gold(out, tasks, gold):
    records = []
    for task in tasks:
        root = out / "projects" / task["project"]
        g = gold[task["id"]]
        if g["kind"] == "execution":
            actual = gold_audit.execution(root, [g["call"]])[0]
        elif g["kind"] == "impact":
            before = gold_audit.execution(root, g["probes"])
            after = gold_audit.execution(root, g["probes"], g["override"])
            assert gold_audit.exact_equal(before, g["before"])
            assert gold_audit.exact_equal(after, g["after"])
            actual = sorted(c["function"] for c, a, b in zip(g["probes"], before, after)
                            if not gold_audit.exact_equal(a, b))
        else:
            assert g["kind"] == "architecture"
            graph, _ = gold_audit.independent_graph(root)
            start = (g["module"], g["function"])
            actual = (gold_audit.reachable_names(graph, start) if g.get("mode") == "transitive"
                      else sorted(n for _, n in graph[start]))
        assert gold_audit.exact_equal(actual, task["expected"]), task["id"]
        assert gold_audit.exact_equal(actual, g["expected"]), task["id"]
        records.append({"task_id": task["id"], "kind": g["kind"], "actual": actual, "passed": True})
    return {"status": "PASS", "verified_at_utc": audited.now(), "questions": len(records), "records": records}


def prepare(out):
    if (out / "protocol.json").exists():
        raise RuntimeError("Frozen output already exists; run it or choose a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    tasks, gold, source_inputs = [], {}, {}
    datasets = [("original48", original.DEFAULT_OUT / "dataset"),
                ("additional48", original.DEFAULT_OUT / "revision_v2/holdout")]
    for split, directory in datasets:
        task_path, gold_path = directory / "eval_tasks.json", directory / "gold_validation.json"
        source_inputs[str(task_path)] = original.sha(task_path)
        source_inputs[str(gold_path)] = original.sha(gold_path)
        subset = read(task_path)
        assert len(subset) == 48
        tasks.extend({**t, "split": split} for t in subset)
        gold.update({g["id"]: g for g in read(gold_path) if g["id"] in {t["id"] for t in subset}})
    assert len(tasks) == len({t["id"] for t in tasks}) == 96
    assert len({(t["project"], t["question"]) for t in tasks}) == 96
    dev = read(original.DEFAULT_OUT / "dataset/dev_tasks.json")
    assets, preparation = {}, {}
    for project in sorted({t["project"] for t in tasks + dev}):
        source_root = original.DEFAULT_OUT / "dataset/projects" / project
        root = out / "projects" / project
        root.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_root.glob("*.py")):
            shutil.copy2(source, root / source.name)
            source_inputs[str(source)] = original.sha(source)
        start = time.perf_counter()
        index = original.build_index(root)
        index_seconds = time.perf_counter() - start
        start = time.perf_counter()
        nodes = original.source_nodes(root)
        graph_seconds = time.perf_counter() - start
        old_asset = read(original.DEFAULT_OUT / "assets" / f"{project}.json")
        assert {k: v for k, v in index.items() if k != "root"} == {
            k: v for k, v in old_asset["index"].items() if k != "root"}, project
        assert nodes == old_asset["nodes"], project
        assets[project] = {"index": index, "nodes": nodes}
        preparation[project] = {"index_seconds": index_seconds, "cross_file_graph_seconds": graph_seconds,
                                "scope": "One warm-filesystem preparation; descriptive, not a cold-start benchmark"}
    original.dump(out / "tasks.json", tasks)
    original.dump(out / "dev_tasks.json", dev)
    original.dump(out / "gold_operations.json", gold)
    original.dump(out / "assets.json", assets)
    original.dump(out / "preparation.json", preparation)
    original.dump(out / "gold_recheck.json", verify_gold(out, tasks, gold))
    original.dump(out / "schedule.json", make_plan(tasks))
    code_hashes = {str(p): original.sha(p) for p in inputs()}
    snapshots = out / "source_snapshot"
    snapshots.mkdir(exist_ok=True)
    for p in inputs():
        shutil.copy2(p, snapshots / p.name)
    frozen_files = {str(p.relative_to(out)): original.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    original.dump(out / "protocol.json", {**CONFIG, "frozen_at_utc": audited.now(),
                  "code_hashes": code_hashes, "source_input_hashes": source_inputs,
                  "frozen_files": frozen_files})
    print(json.dumps({"status": "PREPARED", "questions": len(tasks), "planned_answers": 576,
                      "gold_rechecked": len(gold), "output": str(out)}, ensure_ascii=False), flush=True)


def validate_frozen(out):
    protocol = read(out / "protocol.json")
    assert all(protocol[k] == value for k, value in CONFIG.items())
    for name, expected in protocol["code_hashes"].items():
        assert original.sha(name) == expected, name
    for name, expected in protocol["frozen_files"].items():
        assert original.sha(out / name) == expected, name
    for name, expected in protocol["source_input_hashes"].items():
        assert original.sha(name) == expected, name


def b_ordered(asset, task, selector):
    match = original.URI_RE.search(selector["answer"]) if selector["ok"] else None
    selected = match.group(0) if match else None
    valid = selected in asset["nodes"] and selected in {s["uri"] for s in asset["index"]["symbols"]}
    if not valid:
        return [], selected, False
    members = original.baseline_cross_file_members(asset["nodes"], selected, task["question"])
    return [(0, {"id": uid, "level": 0, "text": original.fragment(asset["nodes"][uid]),
                  "source_uris": [uid]}) for uid in members], selected, True


def run(out, url, dev=False):
    validate_frozen(out)
    client = audited.AuditedClient(out, url)
    environment = audited.runtime_environment(client)
    environment_path = out / "environment.json"
    if environment_path.exists():
        assert read(environment_path)["fingerprint"] == environment["fingerprint"]
    else:
        original.dump(environment_path, environment)
    tasks = read(out / ("dev_tasks.json" if dev else "tasks.json"))
    task_map = {t["id"]: t for t in tasks}
    assets = read(out / "assets.json")
    plan = ([{"task_id": t["id"], "repeat": 0, "arm": arm} for t in tasks for arm in ["A", "B"]]
            if dev else read(out / "schedule.json"))
    result_path = out / ("results_dev.jsonl" if dev else "results.jsonl")
    prior = audited.rows(result_path)
    assert [{k: r[k] for k in ("task_id", "repeat", "arm")} for r in prior] == plan[:len(prior)]
    session_id = audited.digest([audited.now(), dev])[:20]
    original.dump(out / f"session_{session_id}.json", {"started_at_utc": audited.now(),
                  "dev": dev, "resume_after_rows": len(prior), "environment": environment})
    client.reset_query()
    warmup = client.complete('Return only {"answer":0}.', "warmup", 32, {"session_id": session_id})
    assert warmup["ok"]
    for i, entry in enumerate(plan):
        if i < len(prior):
            continue
        task, arm = task_map[entry["task_id"]], entry["arm"]
        asset, root = assets[task["project"]], out / "projects" / task["project"]
        client.reset_query()
        started, started_utc = time.perf_counter(), audited.now()
        outline = original._candidate_symbol_outline(asset["index"], task["question"], 24)
        selector = client.complete(original._selector_prompt(task["question"], outline), "select", 96,
                                   {**entry, "dev": dev, "session_id": session_id})
        select_seconds = time.perf_counter() - started
        expanding = time.perf_counter()
        retrieval_task = {"question": task["question"]}
        ordered, selected, valid = (audited.baseline_ordered(asset, root, retrieval_task, selector) if arm == "A"
                                    else b_ordered(asset, retrieval_task, selector))
        expansion_seconds = time.perf_counter() - expanding
        packing = time.perf_counter()
        context, token_count, chosen, rejected = original.pack(client, ordered, CONFIG["evidence_cap"])
        packing_seconds = time.perf_counter() - packing
        assert token_count <= CONFIG["evidence_cap"]
        pre_answer_seconds = time.perf_counter() - started
        call = client.complete(original.answer_prompt(task["question"], context), "answer", 128,
                               {**entry, "dev": dev, "session_id": session_id})
        query_seconds, ended_utc = time.perf_counter() - started, audited.now()
        correct, parsed, failure = original.evaluate_answer(call, task["expected"])
        if not valid:
            correct, failure = False, "selector_invalid"
        sources = {u for item in chosen for u in item["source_uris"]}
        required = set(task["required_uris"])
        primary_path = asset["nodes"][selected]["path"] if valid else None
        cross_sources = {u for u in sources if asset["nodes"][u]["path"] != primary_path}
        row = {**entry, "session_id": session_id, "split": task.get("split", "development"),
               "project": task["project"], "category": task["category"], "question": task["question"],
               "expected": task["expected"], "correct": correct, "parsed_answer": parsed, "failure": failure,
               "selected_uri": selected, "selection_valid": valid, "selection_correct": selected == task["target_uri"],
               "selector": selector, "answer_call": call, "context": context, "context_tokens": token_count,
               "selected_context_tokens": token_count, "chosen": chosen, "rejected": rejected,
               "query_seconds": query_seconds, "select_seconds": select_seconds,
               "expansion_seconds": expansion_seconds, "packing_seconds": packing_seconds,
               "pre_answer_seconds": pre_answer_seconds, "started_at_utc": started_utc, "ended_at_utc": ended_utc,
               "tokenize_http_calls": client.token_http_count, "tokenize_seconds": client.token_seconds,
               "input_tokens": selector["input_tokens"] + call["input_tokens"],
               "output_tokens": (selector["output_tokens"] or 0) + (call["output_tokens"] or 0),
               "raw_evidence_recall": len(sources & required) / len(required) if required else 1,
               "all_raw_evidence": required <= sources, "unique_source_count": len(sources),
               "cross_file_source_count": len(cross_sources), "source_files": sorted({asset["nodes"][u]["path"] for u in sources}),
               "compaction_seconds": 0}
        with result_path.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{'dev' if dev else 'eval'} {i+1}/{len(plan)} {entry['task_id']} {arm} r{entry['repeat']} "
              f"correct={int(correct)} tokens={token_count} seconds={query_seconds:.3f}", flush=True)
    original.dump(out / f"completed_{'dev' if dev else 'eval'}.json", {"completed_at_utc": audited.now(),
                  "rows": len(plan), "results_sha256": original.sha(result_path), "session_id": session_id})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "dev", "run"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.out)
    else:
        run(args.out, args.url, args.phase == "dev")


if __name__ == "__main__":
    main()
