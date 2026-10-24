"""Audited, concurrent-control remeasurement with fact-preserving context compaction.

V1 inputs/results are read-only. No task answers are used in ranking or packing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import time
import urllib.request

import experiment as v1

HERE = Path(__file__).resolve().parent
BASE = v1.DEFAULT_OUT
OUT = BASE / "revision_v2"
CONFIG = {
    "version": "2.0",
    "arms": ["A", "RH", "C"],
    "evidence_cap": 1024,
    "new_question_repeats": 3,
    "old_question_repeats": 1,
    "temperature": 0,
    "seed": 1,
    "order_seed": 20261021,
    "answer_max_tokens": 128,
    "selector_max_tokens": 96,
    "ctx_size": 8192,
    "model_prompt_cache": False,
    "token_count_cache": "cleared at every query; ordinary memoization allowed within a query",
    "schedule": "randomized task-repeat blocks; six arm permutations balanced within each repeat",
    "C": "RH's identical selected items, same order; remove duplicate raw symbol/import payloads and shorten headers; preserve every unique source and summary body exactly; do not refill freed capacity",
    "reader": "unchanged v1 answer_prompt and chat wrapper",
    "primary_speed_contrast": "C minus RH, new questions",
    "quality_contrasts": ["C minus A", "C minus RH"],
    "inference": "six project clusters; exploratory intervals, no claim of independent new repositories",
    "timing": "physical query wall time including tokenizer, selectors, packing, compaction, answer HTTP and small audit-log overhead; no shared selector",
    "known_test_reuse": "original 48 questions are a separate exploratory regression set; not held out",
}
SERVER_COMMAND = [
    "/opt/homebrew/bin/llama-server", "-m", str(v1.MODEL),
    "--host", "127.0.0.1", "--port", "8766", "--ctx-size", "8192",
    "--parallel", "1", "--no-warmup", "--cache-ram", "0", "--no-cache-prompt",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class AuditedClient(v1.Client):
    def __init__(self, out, url):
        super().__init__(out, url)
        self.token_http_count = 0
        self.token_seconds = 0.0

    def reset_query(self):
        self.token_cache.clear()
        self.token_http_count = 0
        self.token_seconds = 0.0

    def get(self, endpoint):
        with urllib.request.urlopen(self.url + endpoint, timeout=300) as handle:
            return json.load(handle)

    def tokens(self, text):
        if text not in self.token_cache:
            started = time.perf_counter()
            self.token_cache[text] = len(self.post("/tokenize", {
                "content": text, "add_special": False, "parse_special": True,
            })["tokens"])
            self.token_seconds += time.perf_counter() - started
            self.token_http_count += 1
        return self.token_cache[text]

    def complete(self, prompt, purpose, max_tokens, meta=None):
        started, started_utc = time.perf_counter(), now()
        wrapped = v1._chat_wrap(prompt)
        input_tokens = self.tokens(wrapped)
        payload = {
            "prompt": wrapped, "n_predict": max_tokens, "temperature": 0,
            "seed": 1, "cache_prompt": False, "id_slot": 0,
            "stop": ["<|im_end|>", "<|im_start|>"], "stream": False,
        }
        rec = {
            "purpose": purpose, "meta": meta or {}, "prompt": prompt,
            "request": payload, "endpoint": self.url + "/completion",
            "started_at_utc": started_utc, "input_tokens": input_tokens,
            "max_output_tokens": max_tokens,
        }
        try:
            if input_tokens + max_tokens > CONFIG["ctx_size"]:
                raise ValueError("Input plus reserved output exceeds model context")
            response = self.post("/completion", payload)
            rec.update({
                "answer": response.get("content", "").strip(),
                "output_tokens": response.get("tokens_predicted"),
                "timings": response.get("timings", {}),
                "stop_type": response.get("stop_type"),
                "truncated": response.get("truncated", False),
                "stopped_limit": response.get("stopped_limit", False),
                "ok": not response.get("truncated", False)
                      and not response.get("stopped_limit", False)
                      and response.get("stop_type") != "limit",
            })
        except Exception as exc:
            rec.update(ok=False, answer="", output_tokens=0, timings={},
                       error=f"{type(exc).__name__}: {exc}")
        rec["wall_seconds"] = time.perf_counter() - started
        rec["ended_at_utc"] = now()
        rec["call_id"] = digest([payload, purpose, meta, started_utc])[:20]
        with self.calls.open("a") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def compact_selected(asset, chosen):
    """Preserve unique source/import/summary payloads, including exact whitespace."""
    lookup = {item["id"]: item for item in asset["raw"] + asset["summaries"]}
    selected_payload = {"source": {}, "imports": {}, "summary": {}}
    emitted_payload = {"source": {}, "imports": {}, "summary": {}}
    context = []
    raw_occurrences = 0
    for selection in chosen:
        item = lookup[selection["id"]]
        if item["level"] == 0:
            # Reconstruct the actual selected raw text, not inferred provenance.
            assert item["text"] == "\n\n".join(v1.fragment(asset["nodes"][u]) for u in item["source_uris"])
            for uid in item["source_uris"]:
                raw_occurrences += 1
                node = asset["nodes"][uid]
                selected_payload["source"][uid] = node["source"]
                selected_payload["imports"][node["path"]] = node["imports"]
                if uid in emitted_payload["source"]:
                    continue
                block = f"# Code {node['path']}::{node['name']}\n"
                if node["path"] not in emitted_payload["imports"]:
                    if node["imports"]:
                        block += node["imports"] + "\n"
                    emitted_payload["imports"][node["path"]] = node["imports"]
                block += node["source"]
                context.append(block)
                emitted_payload["source"][uid] = node["source"]
        else:
            prefix = f"### {item['id']}\n"
            assert item["text"].startswith(prefix)
            body = item["text"][len(prefix):]
            selected_payload["summary"][item["id"]] = body
            if item["id"] in emitted_payload["summary"]:
                continue
            if item["level"] == 1:
                label = item["id"].split("memory://symbol/", 1)[1]
                header = f"# Function summary {label}\n"
            elif item["level"] == 2:
                header = f"# File summary {item['path']}\n"
            else:
                header = "# Project summary\n"
            context.append(header + body)
            emitted_payload["summary"][item["id"]] = body
    assert selected_payload == emitted_payload
    return "\n\n".join(context), {
        "payload_preserved": True,
        "selected_payload_sha256": digest(selected_payload),
        "emitted_payload_sha256": digest(emitted_payload),
        "unique_raw_symbols": len(emitted_payload["source"]),
        "raw_occurrences_before": raw_occurrences,
        "unique_import_blocks": len(emitted_payload["imports"]),
        "summary_bodies": len(emitted_payload["summary"]),
        "scope": "unique code/import/summary bodies preserved; metadata, repetition and presentation changed",
    }


def baseline_ordered(asset, root, task, selector):
    match = v1.URI_RE.search(selector["answer"]) if selector["ok"] else None
    selected_uri = match.group(0) if match else None
    valid = selected_uri in {s["uri"] for s in asset["index"]["symbols"]} and selected_uri in asset["nodes"]
    if not valid:
        return [], selected_uri, False
    bundle = v1.expand_symbol_context(
        root, asset["index"], selected_uri, question=task["question"],
        numbered=False, dependency_depth=1, max_symbols=8,
    )
    ordered = []
    for index, text in enumerate(re.split(r"\n\n(?=### )", bundle["context"])):
        header = text.split("```", 1)[0]
        ids = v1.URI_RE.findall(header)
        for assignment in bundle.get("bundle_assignments", []):
            if assignment["path"] in header and f"L{assignment['start_line']}-L{assignment['end_line']}" in header:
                ids.extend(v1.uri(assignment["path"], name) for name in assignment["names"])
        ordered.append((0, {"id": f"native:{index}", "level": 0, "text": text,
                            "source_uris": sorted(set(ids))}))
    return ordered, selected_uri, True


def schedule(tasks, repeats, seed):
    rng = random.Random(seed)
    plan = []
    permutations = list(itertools.permutations(CONFIG["arms"]))
    for repeat in range(repeats):
        ordered_tasks = list(tasks)
        rng.shuffle(ordered_tasks)
        arm_orders = list(permutations)
        rng.shuffle(arm_orders)
        for index, task in enumerate(ordered_tasks):
            for arm in arm_orders[index % len(arm_orders)]:
                plan.append({"task_id": task["id"], "repeat": repeat, "arm": arm})
    return plan


def validate_tasks(out):
    new = json.loads((out / "holdout/eval_tasks.json").read_text())
    old = json.loads((BASE / "dataset/eval_tasks.json").read_text())
    dev = json.loads((BASE / "dataset/dev_tasks.json").read_text())
    for name, tasks, count in (("new", new, 48), ("old", old, 48), ("dev", dev, 8)):
        assert len(tasks) == count, (name, "Unexpected task count")
        assert len({t["id"] for t in tasks}) == count, (name, "Duplicate task IDs")
        assert len({(t["project"], t["question"]) for t in tasks}) == count
    assert not ({t["id"] for t in new} & {t["id"] for t in old})
    assert not ({(t["project"], t["question"]) for t in new}
                & {(t["project"], t["question"]) for t in old})
    assert {t["project"] for t in new} == {t["project"] for t in old}
    assert not ({t["project"] for t in dev} & {t["project"] for t in old})
    return {
        name: v1.sha(out / "holdout" / name)
        for name in ("eval_tasks.json", "manifest.json", "gold_validation.json")
    }


def runtime_environment(client):
    props = client.get("/props")
    assert props["default_generation_settings"]["n_ctx"] == 8192
    assert props["total_slots"] == 1
    assert Path(props["model_path"]).resolve() == v1.MODEL.resolve()
    command = subprocess.run([SERVER_COMMAND[0], "--version"], text=True, capture_output=True)
    fingerprint = {
        "server_binary_sha256": v1.sha(SERVER_COMMAND[0]),
        "model_sha256": v1.sha(v1.MODEL),
        "server_properties": {key: props[key] for key in (
            "default_generation_settings", "total_slots", "model_path",
            "build_info", "chat_template", "bos_token", "eos_token",
        )},
    }
    return {
        "recorded_at_utc": now(), "python": sys.version, "platform": platform.platform(),
        "server_command": SERVER_COMMAND,
        "llama_version_stdout": command.stdout, "llama_version_stderr": command.stderr,
        "fingerprint": fingerprint, "fingerprint_sha256": digest(fingerprint),
        "server_props": props, "server_health": client.get("/health"),
    }


def prepare(out, client):
    out.mkdir(parents=True, exist_ok=True)
    holdout = out / "holdout/eval_tasks.json"
    if not holdout.exists():
        raise FileNotFoundError("New-question set must be constructed and independently verified first")
    task_artifacts = validate_tasks(out)
    protocol = {
        **CONFIG, "frozen_at_utc": now(),
        "new_task_sha256": v1.sha(holdout),
        "old_task_sha256": v1.sha(BASE / "dataset/eval_tasks.json"),
        "experiment_v2_sha256": v1.sha(__file__),
        "task_artifact_hashes": task_artifacts,
        "holdout_generator_sha256": v1.sha(HERE / "holdout_v2.py"),
        "dependency_hashes": {
            "experiment_v1": v1.sha(v1.__file__),
            "baseline_indexer": v1.sha(v1.REPO / "1st/symbol_test/symbol_bench/indexer.py"),
            "baseline_runner": v1.sha(v1.REPO / "1st/symbol_test/symbol_bench/run_benchmark.py"),
        },
        "source_snapshot": {p.name: v1.sha(p) for p in sorted((BASE / "assets").glob("*.json"))},
        "development_policy": "Only 8 original development questions used for plumbing; no accuracy-based parameter search",
        "change_rationale": "V1 server timings identify prefill as the dominant cost; preserve evidence bodies rather than blindly halving the context budget",
    }
    dest = out / "protocol.json"
    if dest.exists():
        prior = json.loads(dest.read_text())
        assert {k: v for k, v in prior.items() if k != "frozen_at_utc"} == {k: v for k, v in protocol.items() if k != "frozen_at_utc"}
    else:
        v1.dump(dest, protocol)
    environment = runtime_environment(client)
    env_path = out / "environment.json"
    if env_path.exists():
        assert json.loads(env_path.read_text())["fingerprint"] == environment["fingerprint"]
    else:
        v1.dump(env_path, environment)


def run(out, client, split):
    protocol = json.loads((out / "protocol.json").read_text())
    assert all(protocol[k] == v for k, v in CONFIG.items()), "Configuration changed after freeze"
    assert protocol["experiment_v2_sha256"] == v1.sha(__file__), "Code changed after freeze"
    assert protocol["new_task_sha256"] == v1.sha(out / "holdout/eval_tasks.json")
    assert protocol["old_task_sha256"] == v1.sha(BASE / "dataset/eval_tasks.json")
    assert protocol["task_artifact_hashes"] == validate_tasks(out)
    assert protocol["holdout_generator_sha256"] == v1.sha(HERE / "holdout_v2.py")
    assert protocol["dependency_hashes"] == {
        "experiment_v1": v1.sha(v1.__file__),
        "baseline_indexer": v1.sha(v1.REPO / "1st/symbol_test/symbol_bench/indexer.py"),
        "baseline_runner": v1.sha(v1.REPO / "1st/symbol_test/symbol_bench/run_benchmark.py"),
    }
    current_environment = runtime_environment(client)
    frozen_environment = json.loads((out / "environment.json").read_text())
    assert current_environment["fingerprint"] == frozen_environment["fingerprint"], "Server/model changed"
    asset_hashes = {p.name: v1.sha(p) for p in sorted((BASE / "assets").glob("*.json"))}
    assert protocol["source_snapshot"] == asset_hashes, "Assets changed after freeze"
    if split == "new":
        task_path, repeats = out / "holdout/eval_tasks.json", CONFIG["new_question_repeats"]
    elif split == "old":
        task_path, repeats = BASE / "dataset/eval_tasks.json", CONFIG["old_question_repeats"]
    else:
        task_path, repeats = BASE / "dataset/dev_tasks.json", 1
    tasks = json.loads(task_path.read_text())
    task_map = {t["id"]: t for t in tasks}
    assets = {p.stem: json.loads(p.read_text()) for p in (BASE / "assets").glob("*.json")}
    retrieval, preparation_times = {}, {}
    for project in sorted({t["project"] for t in tasks}):
        asset = assets[project]
        root = BASE / "dataset/projects" / project
        assert asset["source_sha256"] == {p.relative_to(root).as_posix(): v1.sha(p) for p in sorted(root.rglob("*.py"))}
        started = time.perf_counter()
        retriever = v1.Retriever(asset["raw"])
        retriever.ranked("", asset["raw"] + asset["summaries"])
        preparation_times[project] = time.perf_counter() - started
        retrieval[project] = retriever
    plan = schedule(tasks, repeats, CONFIG["order_seed"] + {"new": 0, "old": 100, "dev": 200}[split])
    identity = {
        "config": CONFIG, "code_sha256": v1.sha(__file__), "v1_code_sha256": v1.sha(v1.__file__),
        "task_sha256": v1.sha(task_path), "protocol_sha256": v1.sha(out / "protocol.json"),
        "asset_sha256": asset_hashes,
        "runtime_fingerprint_sha256": current_environment["fingerprint_sha256"],
        "environment_sha256": v1.sha(out / "environment.json"),
        "schedule": plan, "split": split,
    }
    lock = out / f"identity_{split}.json"
    if lock.exists():
        assert json.loads(lock.read_text()) == identity, "Refusing mixed-version resume"
    else:
        v1.dump(lock, identity)
    result_path = out / f"results_{split}.jsonl"
    prior = rows(result_path)
    done = {(r["task_id"], r["repeat"], r["arm"]) for r in prior}
    assert len(done) == len(prior)
    session_id = digest([split, now()])[:20]
    v1.dump(out / f"preparation_{split}_{session_id}.json", {
        "recorded_at_utc": now(), "session_id": session_id,
        "document_vector_build_seconds": preparation_times,
        "summary_source": "unchanged v1 summaries; no new summary model calls",
        "runtime_fingerprint_sha256": current_environment["fingerprint_sha256"],
    })
    client.reset_query()
    warmup = client.complete('Return only {"answer":0}.', "warmup", 32,
                             {"split": split, "session_id": session_id})
    assert warmup["ok"], "Warmup failed"
    for index, entry in enumerate(plan):
        task, arm, repeat = task_map[entry["task_id"]], entry["arm"], entry["repeat"]
        if (task["id"], repeat, arm) in done:
            continue
        client.reset_query()
        started, started_utc = time.perf_counter(), now()
        asset = assets[task["project"]]
        selector, selection_valid, selected_uri = None, True, None
        if arm == "A":
            outline = v1._candidate_symbol_outline(asset["index"], task["question"], 24)
            selector = client.complete(v1._selector_prompt(task["question"], outline), "select", 96,
                                       {"split": split, **entry})
            ordered, selected_uri, selection_valid = baseline_ordered(
                asset, BASE / "dataset/projects" / task["project"], task, selector)
        else:
            ordered = retrieval[task["project"]].ranked(task["question"], asset["raw"] + asset["summaries"])
        original, original_tokens, chosen, rejected = v1.pack(client, ordered, 1024)
        compaction_started = time.perf_counter()
        compaction = None
        if arm == "C":
            context, compaction = compact_selected(asset, chosen)
            context_tokens = client.tokens(context)
        else:
            context, context_tokens = original, original_tokens
        compaction_seconds = time.perf_counter() - compaction_started if arm == "C" else 0
        assert context_tokens <= 1024
        pre_answer_seconds = time.perf_counter() - started
        call = client.complete(v1.answer_prompt(task["question"], context), "answer", 128,
                               {"split": split, **entry})
        query_seconds, ended_utc = time.perf_counter() - started, now()
        correct, parsed, failure = v1.evaluate_answer(call, task["expected"])
        if not selection_valid:
            correct, failure = False, "selector_invalid"
        raw_seen = {u for c in chosen if c["level"] == 0 for u in c["source_uris"]}
        required = set(task["required_uris"])
        record = {
            **entry, "split": split, "session_id": session_id,
            "project": task["project"], "category": task["category"],
            "question": task["question"], "expected": task["expected"], "correct": correct,
            "parsed_answer": parsed, "failure": failure, "selected_uri": selected_uri,
            "selector": selector, "answer_call": call, "context": context,
            "context_tokens": context_tokens, "selected_context_tokens": original_tokens,
            "selected_context_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "chosen": chosen, "rejected": rejected, "compaction": compaction,
            "compaction_seconds": compaction_seconds, "pre_answer_seconds": pre_answer_seconds,
            "query_seconds": query_seconds, "started_at_utc": started_utc, "ended_at_utc": ended_utc,
            "tokenize_http_calls": client.token_http_count, "tokenize_seconds": client.token_seconds,
            "input_tokens": call["input_tokens"] + (selector["input_tokens"] if selector else 0),
            "output_tokens": (call["output_tokens"] or 0) + ((selector["output_tokens"] or 0) if selector else 0),
            "raw_evidence_recall": len(raw_seen & required) / len(required) if required else None,
            "all_raw_evidence": required <= raw_seen,
        }
        with result_path.open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{split} {index+1}/{len(plan)} {task['id']} {arm} r{repeat} "
              f"ok={int(correct)} context={context_tokens}/{original_tokens} seconds={query_seconds:.3f}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "dev", "new", "old"])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    client = AuditedClient(args.out, args.url)
    if args.phase == "prepare":
        prepare(args.out, client)
    else:
        run(args.out, client, args.phase)


if __name__ == "__main__":
    main()
