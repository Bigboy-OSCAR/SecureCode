"""Paired all-files versus unchanged R0 retrieval on HumanEval+ specifications.

Only public prompts become corpus files. Canonical solutions and test inputs
are never loaded by the generation phase. See protocol.json for frozen scope.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "2nd/Documents/test_results/evidence/humaneval_full_r0_20261109"
MODEL = Path("/Users/oscar/.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-5bit")
R0_DIR = HERE.parent / "symbol_raptor"
sys.path.insert(0, str(R0_DIR))
import experiment as original

SYSTEM = "You are a helpful coding assistant. Return only self-contained Python code, without explanation or markdown fences."
CONFIG = {
    "version": "HumanEvalPlus-ALLFILES-R0-1.0",
    "dataset": "HumanEvalPlus v0.1.10, full 164 tasks; no mini/noextreme/filtering",
    "model": str(MODEL),
    "arms": ["FULL", "R0"],
    "samples_per_task_per_arm": 1,
    "temperature": 0,
    "seed": 1,
    "order_seed": 20261109,
    "context_limit": 32768,
    "max_output_tokens": 2048,
    "r0_source_budget": 1024,
    "enable_thinking": False,
    "prompt_cache_reuse": False,
    "prefill_step_size": 512,
    "FULL": "Read and concatenate all 164 public prompt files verbatim, in fixed filename order, with file boundary headings; no truncation, search, or gold content.",
    "R0": "Reuse original.source_nodes, raw_items, Retriever and pack without changes. Sublinear TF-IDF cosine; depth-three dependency bundles and atomic nodes; descending score, whole candidates within 1024 tokens; skip fully covered candidates. No LLM selector or fallback.",
    "request": "Identical target function name and neutral file path for both arms; no target docstring repeated in query.",
    "task_adaptation": "Treat 164 independent HumanEval+ public specifications as an artificial read-only workspace. Generate one requested function per query. This is a retrieval-conditioned HumanEval+ variant, not the standard single-prompt leaderboard setup or a real multi-file repository benchmark.",
    "leakage": "Only prompt is written to corpus. canonical_solution, contract, test, base_input and plus_input are excluded. Public docstring examples remain. Test outputs never influence prompting, retrieval or generation.",
    "schedule": "Seeded shuffled task order; adjacent paired arms; exactly 82 FULL-first and 82 R0-first pairs. Greedy single attempt, no repair or outcome-dependent rerun.",
    "postprocess": "Trim outer whitespace and at most one complete outer python/py/unlabelled markdown fence; otherwise preserve generated text. Do not append reference prompt, add imports, repair code, or sanitize by the expected answer.",
    "timing": "Wall time from corpus read or ranking through packing, chat formatting, tokenization and full model generation. Excludes one-time data/index/model loading, output persistence, grading and analysis. Cold prompt cache per query; per-query synchronization/cache cleanup before start. One observation per task/arm, no repeated timing estimate.",
    "primary_quality": "Percentage of tasks whose one generated solution passes BOTH all original and all extra HumanEval+ tests. Paired task-level comparison; no best-of-n.",
    "secondary": "Base pass@1; input/output tokens; end-to-end query latency; target specification inclusion; syntax/limit failures; index preparation time.",
    "inference": "Descriptive paired task bootstrap, 10000 draws seed 20261109, percentile 95% intervals. Shared corpus and related tasks mean these are not independent-repository generalization intervals. One model/configuration and one timing run.",
    "overflow": "Stop preflight if any FULL or R0 request plus reserved output exceeds context_limit; never silently truncate or subsample.",
    "tuning": "Freeze inputs/settings/code before generation. No correctness results consulted to choose generation/retrieval settings.",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    if path.suffix == ".gz":
        with gzip.open(tmp, "wt", encoding="utf8") as f:
            json.dump(obj, f, ensure_ascii=False)
    else:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf8") as f:
            return json.load(f)
    return json.loads(path.read_text())


def filename(task_id):
    return f"task_{int(task_id.split('/')[1]):03d}.py"


def request(entry_point, path):
    return (f"Implement the function `{entry_point}` in file `{path}`. "
            "Follow that file's docstring exactly. Return a self-contained Python solution "
            "defining the requested function and any needed imports or helper functions. "
            "Do not implement the other files.")


def user_prompt(question, context):
    return "Workspace source files:\n\n" + context + "\n\nTask:\n" + question


def format_prompt(tokenizer, question, context):
    return tokenizer.apply_chat_template(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": user_prompt(question, context)}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )


class Counter:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def tokens(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=False))


def full_context():
    # Preserve exact file bytes decoded as UTF-8; separators are outside each file.
    return "\n\n".join(f"### file {p.name}\n" + p.read_text()
                       for p in sorted((OUT / "corpus").glob("*.py")))


def clean_solution(text):
    text = text.strip()
    m = re.fullmatch(r"```(?:python|py)?[ \t]*\n(.*?)\n```", text, re.DOTALL)
    return (m.group(1).strip() if m else text) + "\n"


def packages():
    return {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}


def prepare():
    assert not (OUT / "protocol.json").exists(), "Protocol already frozen"
    from transformers import AutoTokenizer
    start = time.perf_counter()
    dataset_path = OUT / "HumanEvalPlus-v0.1.10.jsonl.gz"
    assert sha(dataset_path) == read(OUT / "download.json")["sha256"]
    with gzip.open(dataset_path, "rt") as f:
        problems = [json.loads(line) for line in f if line.strip()]
    assert len(problems) == 164 and {p["task_id"] for p in problems} == {f"HumanEval/{i}" for i in range(164)}
    corpus = OUT / "corpus"
    corpus.mkdir(exist_ok=True)
    tasks = []
    for p in sorted(problems, key=lambda p: int(p["task_id"].split("/")[1])):
        path = filename(p["task_id"])
        (corpus / path).write_text(p["prompt"])
        assert (corpus / path).read_text() == p["prompt"]
        ast.parse(p["prompt"])
        tasks.append({"task_id": p["task_id"], "entry_point": p["entry_point"],
                      "path": path, "question": request(p["entry_point"], path)})
    data_seconds = time.perf_counter() - start
    start = time.perf_counter()
    nodes = original.source_nodes(corpus)
    raw = original.raw_items(nodes)
    retriever = original.Retriever(raw)
    retriever.ranked("", raw)
    index_seconds = time.perf_counter() - start
    dump(OUT / "assets.json", {"nodes": nodes, "raw": raw})
    dump(OUT / "tasks.json", tasks)
    tok = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    counter = Counter(tok)
    full = full_context()
    checks = []
    for task in tasks:
        ranked = retriever.ranked(task["question"], raw)
        context, count, chosen, rejected = original.pack(counter, ranked, CONFIG["r0_source_budget"])
        sources = {u for c in chosen for u in c["source_uris"]}
        target_uri = original.uri(task["path"], task["entry_point"])
        assert target_uri in nodes, task["task_id"]
        ft = counter.tokens(format_prompt(tok, task["question"], full))
        rt = counter.tokens(format_prompt(tok, task["question"], context))
        assert max(ft, rt) + CONFIG["max_output_tokens"] <= CONFIG["context_limit"], (ft, rt)
        checks.append({"task_id": task["task_id"], "full_input_tokens": ft,
                       "r0_input_tokens": rt, "r0_context_tokens": count,
                       "r0_has_target": target_uri in sources,
                       "r0_target_rank": next(i + 1 for i, (_, v) in enumerate(ranked) if target_uri in v["source_uris"]),
                       "r0_source_count": len(sources)})
    order = tasks.copy()
    rng = random.Random(CONFIG["order_seed"])
    rng.shuffle(order)
    first = ["FULL"] * 82 + ["R0"] * 82
    rng.shuffle(first)
    schedule = []
    for task, first_arm in zip(order, first):
        for arm in [first_arm, "R0" if first_arm == "FULL" else "FULL"]:
            schedule.append({"index": len(schedule), "task_id": task["task_id"], "arm": arm})
    dump(OUT / "schedule.json", schedule)
    dump(OUT / "preflight.json", {
        "created_at_utc": now(), "tasks": 164,
        "base_tests": sum(len(p["base_input"]) for p in problems),
        "extra_tests": sum(len(p["plus_input"]) for p in problems),
        "corpus_chars": sum(len(p["prompt"]) for p in problems),
        "full_context_tokens": counter.tokens(full), "source_nodes": len(nodes),
        "dependency_edges": sum(len(n["deps"]) for n in nodes.values()),
        "raw_candidates": len(raw), "data_preparation_seconds": data_seconds,
        "index_build_seconds": index_seconds, "checks": checks,
    })
    sources = [Path(__file__), Path(original.__file__),
               REPO / "1st/symbol_test/symbol_bench/indexer.py",
               REPO / "1st/symbol_test/symbol_bench/run_benchmark.py"]
    for p in sources:
        dest = OUT / "source_snapshot" / p.relative_to(REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    model_hashes = {p.name: sha(p) for p in sorted(MODEL.iterdir()) if p.is_file()}
    dump(OUT / "model_manifest.json", {"path": str(MODEL), "files_sha256": model_hashes})
    dump(OUT / "protocol.json", {
        "config": CONFIG, "system_prompt": SYSTEM, "frozen_at_utc": now(),
        "python": sys.version, "platform": platform.platform(), "packages": packages(),
        "source_sha256": {str(p): sha(p) for p in sources},
        "inputs_sha256": {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*"))
                          if p.is_file() and "source_snapshot" not in p.parts},
    })
    print(json.dumps({"status": "frozen", "calls": len(schedule),
                      "full_input_range": [min(c["full_input_tokens"] for c in checks), max(c["full_input_tokens"] for c in checks)],
                      "r0_target_included": sum(c["r0_has_target"] for c in checks),
                      "nodes": len(nodes), "index_seconds": index_seconds}), flush=True)


def validate():
    p = read(OUT / "protocol.json")
    assert p["config"] == CONFIG
    for name, expected in p["source_sha256"].items():
        assert sha(name) == expected, name
    for name, expected in p["inputs_sha256"].items():
        assert sha(OUT / name) == expected, name
    assert packages() == p["packages"], "Installed package set changed after freeze"


def run(limit=None):
    validate()
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    lock = (OUT / "generation.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.write(str(os.getpid()))
    lock.flush()
    session = now().replace(":", "-")
    print("Loading frozen local model", flush=True)
    start = time.perf_counter()
    model, tokenizer = load(str(MODEL))
    mx.eval(model.parameters())
    model_seconds = time.perf_counter() - start
    sampler = make_sampler(temp=0)
    counter = Counter(tokenizer)
    tasks = {t["task_id"]: t for t in read(OUT / "tasks.json")}
    assets = read(OUT / "assets.json")
    raw, nodes = assets["raw"], assets["nodes"]
    start = time.perf_counter()
    retriever = original.Retriever(raw)
    retriever.ranked("", raw)
    vector_seconds = time.perf_counter() - start
    # A non-benchmark warmup compiles kernels; no target generation is reused.
    warm_text = format_prompt(tokenizer, "Return a Python function that returns 1.", "")
    start = time.perf_counter()
    warm = list(stream_generate(model, tokenizer, tokenizer.encode(warm_text, add_special_tokens=False),
                               max_tokens=32, sampler=sampler, prefill_step_size=512))
    mx.synchronize()
    dump(OUT / "sessions" / (session + ".json"), {
        "pid": os.getpid(), "started_at_utc": now(), "hardware": mx.device_info(),
        "model_load_seconds": model_seconds, "document_vectors_seconds": vector_seconds,
        "warmup_seconds": time.perf_counter() - start,
        "warmup_answer": "".join(e.text for e in warm), "packages": packages(),
    })
    print("Model ready; starting paired generation", flush=True)
    completed_this_run = 0
    for entry in read(OUT / "schedule.json"):
        key = f"{entry['index']:03d}_{entry['arm']}_{entry['task_id'].replace('/', '_')}"
        dest = OUT / "calls" / (key + ".json.gz")
        intent = OUT / "intents" / (key + ".json")
        if dest.exists():
            assert read(dest)["status"] == "complete"
            continue
        assert not intent.exists(), f"Unresolved prior generation, inspect before resuming: {intent}"
        if limit is not None and completed_this_run >= limit:
            break
        task = tasks[entry["task_id"]]
        mx.synchronize()
        mx.clear_cache()
        mx.reset_peak_memory()
        mx.random.seed(CONFIG["seed"])
        dump(intent, {**entry, "session": session, "started_at_utc": now(), "pid": os.getpid()})
        started = time.perf_counter()
        utc = now()
        if entry["arm"] == "FULL":
            context = full_context()
            chosen, rejected = [], []
            selected_sources = set(nodes)
            context_tokens = counter.tokens(context)
            rank_seconds = 0
        else:
            ranking_start = time.perf_counter()
            ordered = retriever.ranked(task["question"], raw)
            rank_seconds = time.perf_counter() - ranking_start
            context, context_tokens, chosen, rejected = original.pack(counter, ordered, CONFIG["r0_source_budget"])
            selected_sources = {u for c in chosen for u in c["source_uris"]}
        text = format_prompt(tokenizer, task["question"], context)
        ids = tokenizer.encode(text, add_special_tokens=False)
        assert len(ids) + CONFIG["max_output_tokens"] <= CONFIG["context_limit"]
        preparation_seconds = time.perf_counter() - started
        gen_start = time.perf_counter()
        pieces, first_token_seconds = [], None
        events = stream_generate(model, tokenizer, ids, max_tokens=CONFIG["max_output_tokens"],
                                 sampler=sampler, prefill_step_size=CONFIG["prefill_step_size"])
        try:
            for event in events:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - started
                pieces.append(event.text)
        finally:
            events.close()
        mx.synchronize()
        generation_seconds = time.perf_counter() - gen_start
        query_seconds = time.perf_counter() - started
        answer = "".join(pieces)
        solution = clean_solution(answer)
        try:
            parsed = ast.parse(solution)
            syntax_ok = True
            has_entry_point = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == task["entry_point"] for n in parsed.body)
        except SyntaxError:
            syntax_ok = has_entry_point = False
        row = {
            **entry, "status": "complete", "session": session, "started_at_utc": utc,
            "ended_at_utc": now(), "task": task, "context": context, "formatted_prompt": text,
            "formatted_prompt_sha256": digest(text), "input_tokens": len(ids),
            "context_tokens": context_tokens, "output_tokens": event.generation_tokens,
            "answer": answer, "solution": solution, "solution_sha256": digest(solution),
            "query_seconds": query_seconds, "preparation_seconds": preparation_seconds,
            "retrieval_seconds": rank_seconds, "generation_seconds": generation_seconds,
            "first_token_seconds": first_token_seconds, "prompt_tps": event.prompt_tps,
            "generation_tps": event.generation_tps, "finish_reason": event.finish_reason,
            "peak_memory_gb": event.peak_memory, "chosen": chosen, "rejected": rejected,
            "source_count": len(selected_sources), "syntax_ok": syntax_ok,
            "has_entry_point": has_entry_point,
            "target_included": original.uri(task["path"], task["entry_point"]) in selected_sources,
        }
        assert event.prompt_tokens == len(ids), (event.prompt_tokens, len(ids))
        dump(dest, row)
        with (OUT / "progress.jsonl").open("a") as f:
            f.write(json.dumps({k: row[k] for k in ("index", "task_id", "arm", "session", "input_tokens", "output_tokens", "query_seconds", "finish_reason", "target_included")}) + "\n")
        print(f"{entry['index']+1}/328 {entry['task_id']} {entry['arm']} input={len(ids)} output={event.generation_tokens} seconds={query_seconds:.2f}", flush=True)
        completed_this_run += 1
    if len(list((OUT / "calls").glob("*.json.gz"))) == 328:
        dump(OUT / "generation_complete.json", {"completed_at_utc": now(), "calls": 328,
            "call_sha256": {p.name: sha(p) for p in sorted((OUT / "calls").glob("*.json.gz"))}})
        print("GENERATION COMPLETE", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["prepare", "run", "validate"])
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    {"prepare": prepare, "validate": validate, "run": lambda: run(args.limit)}[args.phase]()
