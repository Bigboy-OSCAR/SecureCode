"""Reproducible local experiment. No external services or benchmark answer exposure."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "1st"))
from symbol_test.symbol_bench.indexer import build_index, expand_symbol_context
from symbol_test.symbol_bench.run_benchmark import (
    _candidate_symbol_outline, _selector_prompt, _chat_wrap, URI_RE
)

DEFAULT_OUT = REPO / "2nd/Documents/test_results/evidence"
MODEL = REPO / "1st/symbol_test/work/models/qwen2.5-coder-7b-instruct-q5_k_m.gguf"
ARMS = ["A", "B", "R0", "RF", "RH"]
CONFIG = {
    "version": "1.0", "arms": ARMS, "main_budget": 1024, "sensitivity_budget": 512,
    "repeats": 3, "temperature": 0, "seed": 1, "order_seed": 20261020,
    "ctx_size": 8192, "answer_max_tokens": 128, "summary_max_tokens": 256,
    "selector_candidates": 24, "selector_max_tokens": 96,
    "cache_prompt": False, "timeout_seconds": 300,
    "raw_bundle_dependency_depth": 3,
    "baseline_bundle_dependency_depth": 1, "baseline_bundle_max_symbols": 8,
    "B_max_function_hops": 2, "B_max_functions": 8,
    "retrieval": "cosine TF-IDF, IDF fitted on raw candidates; unseen terms use smoothed df=0 IDF in every arm",
    "raw_candidates": "dependency bundles plus atomic function/constant originals; identical in R0/RF/RH",
    "grouping": "AST symbol dependency bundles -> per-file summaries -> project summary",
    "packing": "descending cosine; skip whole nodes that do not fit; no truncation",
    "grading": "exact JSON object/value and types after stripping at most one complete outer JSON code fence",
    "primary_comparison": "RH-A", "summary_comparison": "RH-R0",
    "hierarchy_comparison": "RH-RF", "bootstrap_unit": "project",
}


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Client:
    def __init__(self, out, url="http://127.0.0.1:8766"):
        self.out, self.url = Path(out), url
        self.calls = self.out / "model_calls.jsonl"
        self.token_cache = {}

    def post(self, endpoint, payload):
        request = urllib.request.Request(
            self.url + endpoint, json.dumps(payload).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=CONFIG["timeout_seconds"]) as f:
            return json.load(f)

    def tokens(self, text):
        if text not in self.token_cache:
            self.token_cache[text] = len(self.post(
                "/tokenize", {"content": text, "add_special": False}
            )["tokens"])
        return self.token_cache[text]

    def complete(self, prompt, purpose, max_tokens, meta=None):
        started = time.perf_counter()
        wrapped = _chat_wrap(prompt)
        input_tokens = self.tokens(wrapped)
        rec = {"purpose": purpose, "meta": meta or {}, "prompt": prompt,
               "input_tokens": input_tokens, "max_output_tokens": max_tokens}
        try:
            if input_tokens + max_tokens > CONFIG["ctx_size"]:
                raise ValueError("input plus reserved output exceeds context")
            response = self.post("/completion", {
                "prompt": wrapped, "n_predict": max_tokens, "temperature": 0,
                "seed": 1, "cache_prompt": False, "id_slot": 0,
                "stop": ["<|im_end|>", "<|im_start|>"], "stream": False,
            })
            rec.update({
                "answer": response.get("content", "").strip(),
                "output_tokens": response.get("tokens_predicted"),
                "timings": response.get("timings", {}),
                "stop_type": response.get("stop_type"),
                "truncated": response.get("truncated", False),
                "stopped_limit": response.get("stopped_limit", False),
                "ok": not response.get("truncated", False) and not response.get("stopped_limit", False)
                      and response.get("stop_type") != "limit",
            })
        except Exception as exc:
            rec.update(ok=False, answer="", output_tokens=0,
                       error=f"{type(exc).__name__}: {exc}", timings={})
        rec["wall_seconds"] = time.perf_counter() - started
        rec["call_id"] = hashlib.sha256(
            (wrapped + purpose + json.dumps(meta, sort_keys=True) + str(time.time_ns())).encode()
        ).hexdigest()[:16]
        with self.calls.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def uri(path, name):
    return f"memory://symbol/{path}::{name}"


def source_nodes(root):
    """Raw nodes preserve import declarations, constants and exact executable source."""
    root = Path(root)
    nodes, module_lookup, parsed = {}, {}, {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        mod = rel[:-3].replace("/", ".")
        text = path.read_text()
        tree, lines = ast.parse(text), text.splitlines()
        module_lookup[mod] = rel
        imports = [n for n in tree.body if isinstance(n, (ast.ImportFrom, ast.Import))]
        import_text = "\n".join(ast.get_source_segment(text, n) for n in imports)
        parsed[rel] = (tree, imports)
        for node in tree.body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [n.id for target in node.targets for n in ast.walk(target) if isinstance(n, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            for name in names:
                uid = uri(rel, name)
                source = "\n".join(lines[node.lineno - 1:node.end_lineno])
                nodes[uid] = {
                    "id": uid, "path": rel, "name": name, "source": source,
                    "imports": import_text, "start": node.lineno, "end": node.end_lineno,
                    "refs": sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}),
                    "deps": [], "kind": "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "constant",
                }
    for uid, n in nodes.items():
        _, imports = parsed[n["path"]]
        aliases = {}
        for imp in imports:
            if isinstance(imp, ast.ImportFrom):
                rel = module_lookup.get(imp.module)
                if rel:
                    for alias in imp.names:
                        aliases[alias.asname or alias.name] = uri(rel, alias.name)
        for ref in n["refs"]:
            dep = aliases.get(ref, uri(n["path"], ref))
            if dep in nodes and dep != uid:
                n["deps"].append(dep)
        n["deps"] = sorted(set(n["deps"]))
    return nodes


def closure(nodes, start, depth=3):
    seen, frontier = [], [start]
    for _ in range(depth + 1):
        next_nodes = []
        for uid in frontier:
            if uid in seen or uid not in nodes:
                continue
            seen.append(uid)
            next_nodes.extend(nodes[uid]["deps"])
        frontier = next_nodes
    return seen


def baseline_cross_file_members(nodes, start, question):
    """Match the native expansion's 8-function cap and two expansion rounds."""
    functions, constants = [start], []
    start_path = nodes[start]["path"]
    for uid, node in nodes.items():
        if (node["kind"] == "function" and node["path"] == start_path
                and node["name"].lower() in question.lower() and uid not in functions
                and len(functions) < 8):
            functions.append(uid)
    frontier = [start]
    for _ in range(2):
        next_frontier = []
        for uid in frontier:
            for dep in nodes[uid]["deps"]:
                if nodes[dep]["kind"] == "constant":
                    if dep not in constants:
                        constants.append(dep)
                elif dep not in functions and len(functions) < 8:
                    functions.append(dep)
                    next_frontier.append(dep)
        frontier = next_frontier
    return functions + constants


def fragment(node):
    return (f"### {node['id']} lines {node['start']}-{node['end']}\n"
            f"{node['imports']}\n{node['source']}")


def raw_items(nodes):
    items = []
    for uid, node in nodes.items():
        members = closure(nodes, uid)
        text = "\n\n".join(fragment(nodes[m]) for m in members)
        items.append({
            "id": uid, "level": 0, "text": text, "source_uris": members,
            "path": node["path"], "kind": node["kind"],
        })
        if len(members) > 1:
            items.append({
                "id": "atomic:" + uid, "level": 0, "text": fragment(node),
                "source_uris": [uid], "path": node["path"], "kind": "raw_atomic",
            })
    return items


def words(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower()
    # Preserve underscore compound words and their parts for code/name matching.
    matches = re.findall(r"[a-z][a-z0-9_]*|\d+", text)
    tokens = []
    for word in matches:
        tokens.append(word)
        if "_" in word:
            tokens.extend(word.split("_"))
    return [w for w in tokens if len(w) > 1]


class Retriever:
    def __init__(self, raw):
        df = Counter()
        for item in raw:
            df.update(set(words(item["text"])))
        self.idf = {w: math.log((1 + len(raw)) / (1 + n)) + 1 for w, n in df.items()}
        self.unseen_idf = math.log(1 + len(raw)) + 1
        self.vectors = {}

    def vector(self, text):
        counts = Counter(words(text))
        v = {w: (1 + math.log(n)) * self.idf.get(w, self.unseen_idf) for w, n in counts.items()}
        norm = math.sqrt(sum(x*x for x in v.values())) or 1
        return {w: x/norm for w, x in v.items()}

    def ranked(self, question, items):
        q = self.vector(question)
        scored = []
        for item in items:
            if item["id"] not in self.vectors:
                self.vectors[item["id"]] = self.vector(item["text"])
            v = self.vectors[item["id"]]
            score = sum(x*v.get(w, 0) for w, x in q.items())
            scored.append((score, item))
        return [(score, item) for score, item in sorted(scored, key=lambda p: (-p[0], p[1]["id"]))]


def pack(client, ordered, budget):
    chosen, context, used, rejected = [], "", 0, []
    raw_sources = set()
    for score, item in ordered:
        if item["level"] == 0 and set(item["source_uris"]) <= raw_sources:
            continue
        candidate = context + ("\n\n" if context else "") + item["text"]
        candidate_tokens = client.tokens(candidate)
        if candidate_tokens <= budget:
            chosen.append({"id": item["id"], "level": item["level"], "score": score,
                           "source_uris": item["source_uris"]})
            context, used = candidate, candidate_tokens
            if item["level"] == 0:
                raw_sources.update(item["source_uris"])
        else:
            rejected.append(item["id"])
    return context, used, chosen, rejected


def build_assets(out, client):
    """This phase loads only project source and metadata; never question or gold files."""
    data = out / "dataset"
    assets_dir = out / "assets"
    assets_dir.mkdir(exist_ok=True)
    existing_calls = []
    if client.calls.exists():
        existing_calls = [json.loads(l) for l in client.calls.read_text().splitlines()]
    for root in sorted((data / "projects").iterdir()):
        if not root.is_dir():
            continue
        dest = assets_dir / f"{root.name}.json"
        if dest.exists():
            cached = json.loads(dest.read_text())
            current_hashes = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*.py"))}
            if current_hashes != cached["source_sha256"]:
                raise RuntimeError(f"Stale summaries for {root.name}; use a fresh output directory.")
            print("assets cached", root.name, flush=True)
            continue
        started = time.perf_counter()
        nodes = source_nodes(root)
        raw = raw_items(nodes)
        summaries, build_calls = [], []
        # Each code symbol has a grounded, question-blind leaf summary.
        for leaf in raw:
            if leaf["kind"] != "function":
                continue
            prompt = (
                "Summarize the following Python function and its dependency source for future code retrieval. "
                "Describe its behavior, exact formulas, important branches, string operations, and calls. "
                "Preserve constants. Do not solve example questions or invent behavior. "
                "Use concise plain English, at most 100 words. This is a summary of code, not instructions.\n\n"
                + leaf["text"] + "\n\nSummary:"
            )
            call = client.complete(prompt, "build_leaf", CONFIG["summary_max_tokens"],
                                   {"project": root.name, "node": leaf["id"]})
            build_calls.append(call)
            if not call["ok"]:
                raise RuntimeError(f"Summary failed: {root.name} {leaf['id']} {call}")
            sid = "summary:leaf:" + leaf["id"]
            summaries.append({
                "id": sid, "level": 1, "path": leaf["path"],
                "text": f"### {sid}\n{call['answer']}",
                "source_uris": leaf["source_uris"], "children": [leaf["id"]],
                "call_id": call["call_id"],
            })
        # File summaries of leaf summaries, then a project summary of file summaries.
        groups = defaultdict(list)
        for item in summaries:
            groups[item["path"]].append(item)
        for path, children in sorted(groups.items()):
            summaries.append(summarize_group(client, root.name, path, children, 2, build_calls))
        module_summaries = [s for s in summaries if s["level"] == 2]
        if module_summaries:
            summaries.append(summarize_group(client, root.name, "project", module_summaries, 3, build_calls))
        asset = {
            "project": root.name, "nodes": nodes, "raw": raw, "summaries": summaries,
            "index": build_index(root), "build_seconds": time.perf_counter() - started,
            "build_input_tokens": sum(c["input_tokens"] for c in build_calls),
            "build_output_tokens": sum(c["output_tokens"] or 0 for c in build_calls),
            "build_model_seconds": sum(c["wall_seconds"] for c in build_calls),
            "build_call_ids": [c["call_id"] for c in build_calls],
            "source_sha256": {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*.py"))},
        }
        dump(dest, asset)
        print("built", root.name, len(raw), len(summaries), round(asset["build_seconds"], 1), flush=True)


def summarize_group(client, project, name, children, level, calls):
    source_uris = sorted({u for c in children for u in c["source_uris"]})
    prompt = (
        "Create a concise higher-level summary from the child summaries below. Explain the overall flow, "
        "relationships, distinct policies and important exceptions. Preserve exact formulas, boundaries, "
        "constants and string rules when supplied. Do not infer missing relationships or answer specific questions. "
        "Use at most 100 words of plain English.\n\n"
        + "\n\n".join(c["text"] for c in children) + "\n\nSummary:"
    )
    call = client.complete(prompt, f"build_level_{level}", CONFIG["summary_max_tokens"],
                           {"project": project, "group": name})
    calls.append(call)
    if not call["ok"]:
        raise RuntimeError(f"Group summary failed: {project} {name}: {call}")
    sid = f"summary:level{level}:{name}"
    return {"id": sid, "level": level, "path": name,
            "text": f"### {sid}\n{call['answer']}",
            "source_uris": source_uris, "children": [c["id"] for c in children],
            "call_id": call["call_id"]}


def answer_prompt(question, context):
    return (
        "Answer a Python code comprehension question using only the provided code and summaries. "
        "Trace exact Python operations; preserve case, slashes and spaces. "
        "Source code takes precedence over summaries if they conflict. "
        "If information is insufficient, use null. "
        'Return only one valid JSON object of the form {"answer": <requested value>}. '
        "No markdown or explanation. For a set/list of names, return the requested sorted JSON list.\n\n"
        f"Question:\n{question}\n\nCode context:\n{context}\n\nAnswer:"
    )


def evaluate_answer(call, expected):
    if not call["ok"]:
        return False, None, "execution_or_limit"
    text = call["answer"].strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return False, None, "invalid_json"
    if not isinstance(obj, dict) or set(obj) != {"answer"}:
        return False, obj, "invalid_schema"
    actual = obj["answer"]
    # Exact JSON semantics, no substring grading; forbid bool == integer accidental equality.
    correct = json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(expected, sort_keys=True, ensure_ascii=False)
    return correct, actual, None if correct else ("abstained" if actual is None else "wrong_answer")


def run_eval(out, client, split="eval", repeats=3, budget=1024, arms=None, tag="main"):
    tasks = json.loads((out / "dataset" / f"{split}_tasks.json").read_text())
    arms = arms or ARMS
    assets = {p.stem: json.loads(p.read_text()) for p in (out / "assets").glob("*.json")}
    retrievers = {p: Retriever(a["raw"]) for p, a in assets.items()}
    # All document vectors are index-time work, not condition-specific first-query work.
    for project, asset in assets.items():
        retrievers[project].ranked("", asset["raw"] + asset["summaries"])
    results_path = out / f"results_{split}_{tag}.jsonl"
    run_identity = {
        "config": CONFIG, "experiment_sha256": sha(__file__), "split": split,
        "budget": budget, "repeats": repeats, "arms": arms,
        "task_sha256": sha(out / "dataset" / f"{split}_tasks.json"),
        "asset_hashes": {p.name: sha(p) for p in sorted((out / "assets").glob("*.json"))},
    }
    lock_path = out / f"run_identity_{split}_{tag}.json"
    if lock_path.exists() and json.loads(lock_path.read_text()) != run_identity:
        raise RuntimeError("Run identity changed; use a fresh result destination rather than mixing runs.")
    dump(lock_path, run_identity)
    previous = [json.loads(l) for l in results_path.read_text().splitlines()] if results_path.exists() else []
    done = {(r["task_id"], r["arm"], r["repeat"]) for r in previous}
    # A/B share one selector outcome per task per repeat, cost charged fully to each.
    selectors = {}
    for r in previous:
        if r.get("selector"):
            selectors[(r["task_id"], r["repeat"])] = r["selector"]
    schedule = [(task, repeat, arm) for repeat in range(repeats) for task in tasks for arm in arms]
    random.Random(CONFIG["order_seed"]).shuffle(schedule)
    n = len(schedule)
    for i, (task, repeat, arm) in enumerate(schedule):
        key = (task["id"], arm, repeat)
        if key in done:
            continue
        started = time.perf_counter()
        asset = assets[task["project"]]
        root = out / "dataset/projects" / task["project"]
        selector, selection_seconds, selector_elapsed_here = None, 0.0, 0.0
        selected_uri, selection_valid = None, True
        if arm in ("A", "B"):
            skey = (task["id"], repeat)
            if skey not in selectors:
                selector_started = time.perf_counter()
                outline = _candidate_symbol_outline(asset["index"], task["question"], CONFIG["selector_candidates"])
                select = client.complete(_selector_prompt(task["question"], outline), "select",
                                         CONFIG["selector_max_tokens"], {"task": task["id"], "repeat": repeat})
                selectors[skey] = select
                selector_elapsed_here = time.perf_counter() - selector_started
                selectors[skey]["selector_pipeline_seconds"] = selector_elapsed_here
            selector = selectors[skey]
            selection_seconds = selector.get("selector_pipeline_seconds", selector["wall_seconds"])
            match = URI_RE.search(selector["answer"]) if selector["ok"] else None
            selected_uri = match.group(0) if match else None
            indexed_function_uris = {s["uri"] for s in asset["index"]["symbols"]}
            selection_valid = selected_uri in indexed_function_uris and selected_uri in asset["nodes"]
            if selection_valid and arm == "A":
                bundle = expand_symbol_context(root, asset["index"], selected_uri,
                                               question=task["question"], numbered=False,
                                               dependency_depth=1, max_symbols=8)
                # Preserve native ordering and code, pack complete native fragments.
                native_fragments = re.split(r"\n\n(?=### )", bundle["context"])
                ordered = []
                for idx, text in enumerate(native_fragments):
                    ids = URI_RE.findall(text.split("```", 1)[0])
                    # Constants in native bundle headers use names and spans, not symbol URIs.
                    header = text.split("```", 1)[0]
                    for a in bundle.get("bundle_assignments", []):
                        if a["path"] in header and f"L{a['start_line']}-L{a['end_line']}" in header:
                            ids.extend(uri(a["path"], name) for name in a["names"])
                    ordered.append((0, {"id": f"native:{idx}", "level": 0, "text": text, "source_uris": sorted(set(ids))}))
            elif selection_valid:
                members = baseline_cross_file_members(asset["nodes"], selected_uri, task["question"])
                ordered = [(0, {"id": uid, "level": 0, "text": fragment(asset["nodes"][uid]),
                                 "source_uris": [uid]}) for uid in members]
            else:
                ordered = []
        else:
            items = list(asset["raw"])
            if arm == "RF":
                items += [s for s in asset["summaries"] if s["level"] == 1]
            elif arm == "RH":
                items += asset["summaries"]
            ordered = retrievers[task["project"]].ranked(task["question"], items)
        context, context_tokens, chosen, rejected = pack(client, ordered, budget)
        # Total query time below uses deterministic reconstruction for the shared selector:
        # retrieval/packing measured directly, selector full uncached cost, answer full uncached cost.
        pre_answer_seconds = time.perf_counter() - started
        call = client.complete(answer_prompt(task["question"], context), "answer", CONFIG["answer_max_tokens"],
                               {"task": task["id"], "arm": arm, "repeat": repeat, "budget": budget, "tag": tag})
        correct, parsed, failure = evaluate_answer(call, task["expected"])
        if not selection_valid:
            correct, failure = False, "selector_invalid"
        raw_seen = {u for c in chosen if c["level"] == 0 for u in c["source_uris"]}
        cited = {u for c in chosen for u in c["source_uris"]}
        required = set(task["required_uris"])
        # Server-inference wall is independently comparable and includes all charged model calls.
        model_seconds = call["wall_seconds"] + (selector["wall_seconds"] if selector else 0)
        retrieval_seconds = pre_answer_seconds - selector_elapsed_here
        rec = {
            "task_id": task["id"], "project": task["project"], "category": task["category"],
            "arm": arm, "repeat": repeat, "budget": budget, "correct": correct, "parsed_answer": parsed,
            "expected": task["expected"], "failure": failure, "selected_uri": selected_uri,
            "selection_correct": selected_uri == task["target_uri"] if selector else None,
            "selector": selector, "answer_call": call, "context": context,
            "context_tokens": context_tokens, "chosen": chosen, "rejected": rejected,
            "raw_evidence_recall": len(raw_seen & required) / len(required) if required else None,
            "provenance_recall_not_content_recall": len(cited & required) / len(required) if required else None,
            "all_raw_evidence": required <= raw_seen,
            "input_tokens": call["input_tokens"] + (selector["input_tokens"] if selector else 0),
            "output_tokens": (call["output_tokens"] or 0) + ((selector["output_tokens"] or 0) if selector else 0),
            "model_seconds": model_seconds,
            "retrieval_seconds": retrieval_seconds,
            "query_seconds": retrieval_seconds + selection_seconds + call["wall_seconds"],
            "pre_answer_seconds_observed": pre_answer_seconds,
            "loop_wall_seconds": time.perf_counter() - started,
        }
        with results_path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{split} {tag} {i+1}/{n} {task['id']} {arm} r{repeat} "
              f"{int(correct)} tokens={rec['input_tokens']} s={model_seconds:.2f}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "build", "dev", "eval", "sensitivity"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    client = Client(out, args.url)
    if args.phase == "prepare":
        from corpus_builder import build
        build(out / "dataset")
        dump(out / "protocol.json", {**CONFIG, "created_at": datetime.now(timezone.utc).isoformat(),
                                    "note": "Fixed before any evaluation outputs; development project only for plumbing checks."})
        dump(out / "environment.json", {
            "platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version, "model_path": str(MODEL), "model_sha256": sha(MODEL),
            "model_bytes": MODEL.stat().st_size,
            "llama_version": subprocess.run(["/opt/homebrew/bin/llama-server", "--version"], capture_output=True, text=True).stdout,
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip(),
            "experiment_sha256": sha(__file__), "corpus_builder_sha256": sha(HERE / "corpus_builder.py"),
            "baseline_indexer_sha256": sha(REPO / "1st/symbol_test/symbol_bench/indexer.py"),
            "baseline_runner_sha256": sha(REPO / "1st/symbol_test/symbol_bench/run_benchmark.py"),
        })
    elif args.phase == "build":
        build_assets(out, client)
    elif args.phase == "dev":
        run_eval(out, client, split="dev", repeats=1)
    elif args.phase == "eval":
        run_eval(out, client)
    elif args.phase == "sensitivity":
        run_eval(out, client, budget=512, repeats=1, arms=["R0", "RH"], tag="budget512")


if __name__ == "__main__":
    main()
