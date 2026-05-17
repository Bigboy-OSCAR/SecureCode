from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from .indexer import compact_outline, expand_symbol_context, read_span, resolve_symbol, symbol_map
from .make_corpus import SCALE_DEFAULTS, generate_corpus


DEFAULT_MODEL = Path("/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf")
DEFAULT_MODES = ["full_repo", "full_file", "line_span", "symbol_oracle", "symbol_select"]
EXPERIMENTAL_MODES = ["symbol_bundle_oracle", "symbol_filtered_select_bundle"]
ALL_MODES = DEFAULT_MODES + EXPERIMENTAL_MODES
URI_RE = re.compile(r"memory://symbol/[^\s'\"`]+::[A-Za-z_][\w.]*")
FILE_RE = re.compile(r"\b[\w./-]+\.py\b")
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b")
STOPWORDS = {
    "answer",
    "class",
    "combine",
    "constant",
    "does",
    "exact",
    "file",
    "final",
    "for",
    "function",
    "given",
    "inside",
    "literal",
    "module",
    "number",
    "only",
    "return",
    "returns",
    "string",
    "the",
    "value",
    "what",
    "when",
    "with",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_code(root: Path) -> str:
    chunks = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        chunks.append(f"### file: {rel}\n```python\n{path.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(chunks)


def _file_code(root: Path, rel_path: str) -> str:
    path = root / rel_path
    return f"### file: {rel_path}\n```python\n{path.read_text(encoding='utf-8')}\n```"


def _answer_prompt(question: str, context: str) -> str:
    return f"""You are answering a code comprehension benchmark.
Use only the provided code context. If concrete inputs are given, trace the Python operations exactly.
For string operations, preserve every character that the code does not change.
For numeric operations, calculate from the literal constants in the code.
Return only the requested final value. No markdown, no code fence, no prose.

Question:
{question}

Code context:
{context}

Answer:
"""


def _selector_prompt(question: str, outline: list[dict[str, Any]]) -> str:
    return f"""You are a symbol selector for a Python codebase.
Return exactly one URI from the symbol index. No prose, no markdown.

Question:
{question}

Symbol index JSON:
{json.dumps(outline, ensure_ascii=False, separators=(",", ":"))}

URI:
"""


def _chat_wrap(user_prompt: str) -> str:
    return (
        "<|im_start|>system\n"
        "You are a precise code analysis assistant. Follow output constraints exactly."
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_prompt}"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _clean_output(text: str) -> str:
    text = text.replace("\b", "")
    if "generate:" in text:
        text = text.split("generate:", 1)[1]
        text = text.split("\n\n", 1)[-1]
    for marker in ["common_perf_print:", "llama_memory_breakdown_print:", "[ Prompt:"]:
        if marker in text:
            text = text.split(marker, 1)[0]
    text = text.replace("[end of text]", "")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    return text.strip()


def _parse_perf(text: str) -> dict[str, float | int | None]:
    perf: dict[str, float | int | None] = {
        "prompt_eval_ms": None,
        "prompt_tokens": None,
        "eval_ms": None,
        "eval_tokens": None,
        "total_ms": None,
        "prompt_tps": None,
        "generation_tps": None,
    }
    prompt_match = re.search(
        r"prompt eval time =\s*([0-9.]+) ms /\s*(\d+) tokens .*?([0-9.]+) tokens per second",
        text,
    )
    if prompt_match:
        perf["prompt_eval_ms"] = float(prompt_match.group(1))
        perf["prompt_tokens"] = int(prompt_match.group(2))
        perf["prompt_tps"] = float(prompt_match.group(3))
    eval_match = re.search(
        r"eval time =\s*([0-9.]+) ms /\s*(\d+) runs .*?([0-9.]+) tokens per second",
        text,
    )
    if eval_match:
        perf["eval_ms"] = float(eval_match.group(1))
        perf["eval_tokens"] = int(eval_match.group(2))
        perf["generation_tps"] = float(eval_match.group(3))
    total_match = re.search(r"total time =\s*([0-9.]+) ms /", text)
    if total_match:
        perf["total_ms"] = float(total_match.group(1))
    compact_match = re.search(r"\[ Prompt:\s*([0-9.]+) t/s \| Generation:\s*([0-9.]+) t/s \]", text)
    if compact_match:
        perf["prompt_tps"] = float(compact_match.group(1))
        perf["generation_tps"] = float(compact_match.group(2))
    return perf


def _run_llama(args: argparse.Namespace, prompt: str, purpose: str) -> dict[str, Any]:
    estimated_tokens = max(1, round(len(prompt) / 4))
    if args.dry_run:
        return {
            "purpose": purpose,
            "answer": "",
            "wall_seconds": 0.0,
            "prompt_chars": len(prompt),
            "estimated_prompt_tokens": estimated_tokens,
            "prompt_eval_ms": None,
            "prompt_tokens": None,
            "eval_ms": None,
            "eval_tokens": None,
            "total_ms": None,
            "prompt_tps": None,
            "generation_tps": None,
            "returncode": 0,
        }

    llama_bin = shutil.which(args.llama_bin) or args.llama_bin
    chat_prompt = _chat_wrap(prompt)
    with tempfile.NamedTemporaryFile("w", suffix=".prompt.txt", encoding="utf-8", delete=False) as prompt_file:
        prompt_file.write(chat_prompt)
        prompt_path = Path(prompt_file.name)

    command = [
        llama_bin,
        "-m",
        str(args.model),
        "-f",
        str(prompt_path),
        "-n",
        str(args.n_predict),
        "--no-display-prompt",
        "--temp",
        "0",
        "--seed",
        str(args.seed),
        "--ctx-size",
        str(args.ctx_size),
        "--simple-io",
        "-no-cnv",
        "--no-warmup",
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
    finally:
        try:
            prompt_path.unlink()
        except FileNotFoundError:
            pass
    wall_seconds = time.perf_counter() - started
    perf_output = completed.stdout + "\n" + completed.stderr
    perf = _parse_perf(perf_output)
    answer_source = completed.stdout if completed.stdout.strip() else perf_output
    return {
        "purpose": purpose,
        "answer": _clean_output(answer_source),
        "wall_seconds": wall_seconds,
        "prompt_chars": len(prompt),
        "estimated_prompt_tokens": estimated_tokens,
        **perf,
        "returncode": completed.returncode,
    }


def _is_correct(answer: str, expected_substrings: list[str], forbidden_substrings: list[str] | None = None) -> bool:
    folded = answer.casefold()
    forbidden_substrings = forbidden_substrings or []
    return all(item.casefold() in folded for item in expected_substrings) and not any(
        item.casefold() in folded for item in forbidden_substrings
    )


def _required_substrings(task: dict[str, Any]) -> list[str]:
    return task.get("expected_substrings") or task.get("required_substrings") or []


def _forbidden_substrings(task: dict[str, Any]) -> list[str]:
    return task.get("forbidden_substrings") or []


def _question_terms(question: str) -> set[str]:
    terms: set[str] = set()
    for match in IDENTIFIER_RE.findall(question):
        for part in re.split(r"[._]", match):
            folded = part.casefold()
            if len(folded) > 1 and folded not in STOPWORDS:
                terms.add(folded)
        folded_match = match.casefold()
        if folded_match not in STOPWORDS:
            terms.add(folded_match)
    return terms


def _candidate_symbol_outline(index: dict[str, Any], question: str, limit: int) -> list[dict[str, Any]]:
    explicit_files = {path.lstrip("./") for path in FILE_RE.findall(question)}
    terms = _question_terms(question)
    folded_question = question.casefold()
    scored: list[tuple[int, dict[str, Any]]] = []

    for symbol in index["symbols"]:
        path = symbol["path"]
        qualname = symbol["qualname"]
        name = symbol["name"]
        if explicit_files and path not in explicit_files and qualname.casefold() not in folded_question:
            continue
        symbol_parts = {part.casefold() for part in re.split(r"[._]", qualname)}
        path_parts = {part.casefold() for part in re.split(r"[/._-]", path)}
        score = 0

        if path in explicit_files:
            score += 30
        if qualname.casefold() in folded_question:
            score += 20
        if name.casefold() in terms:
            score += 16
        score += 3 * len(symbol_parts & terms)
        score += len(path_parts & terms)

        if score:
            scored.append((score, symbol))

    if not scored:
        scored = [(1, symbol) for symbol in index["symbols"]]

    scored.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["start_line"]))
    selected = [symbol for _, symbol in scored[:limit]]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for symbol in selected:
        grouped.setdefault(symbol["path"], []).append(symbol)

    return [
        {
            "file": path,
            "symbols": [
                {
                    "kind": symbol["kind"],
                    "qualname": symbol["qualname"],
                    "uri": symbol["uri"],
                }
                for symbol in symbols
            ],
        }
        for path, symbols in sorted(grouped.items())
    ]


def _make_mode_prompt(mode: str, root: Path, index: dict[str, Any], task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    target = symbol_map(index)[task["target_uri"]]
    if mode == "full_repo":
        return _answer_prompt(task["question"], _all_code(root)), {"resolved_uri": None}
    if mode == "full_file":
        return _answer_prompt(task["question"], _file_code(root, target["path"])), {"resolved_uri": None}
    if mode == "line_span":
        span = read_span(root, target["path"], target["start_line"], target["end_line"], numbered=True)
        context = f"### span: memory://{target['path']}#L{target['start_line']}-L{target['end_line']}\n```python\n{span}\n```"
        return _answer_prompt(task["question"], context), {"resolved_uri": task["target_uri"]}
    if mode == "symbol_oracle":
        symbol = resolve_symbol(root, index, task["target_uri"], numbered=True)
        context = f"### symbol: {task['target_uri']}\n```python\n{symbol}\n```"
        return _answer_prompt(task["question"], context), {"resolved_uri": task["target_uri"]}
    if mode == "symbol_bundle_oracle":
        bundle = expand_symbol_context(
            root,
            index,
            task["target_uri"],
            question=task["question"],
            numbered=False,
            dependency_depth=1,
        )
        bundle_meta = {key: value for key, value in bundle.items() if key != "context"}
        return _answer_prompt(task["question"], bundle["context"]), {"resolved_uri": task["target_uri"], **bundle_meta}
    raise ValueError(f"unsupported single-prompt mode: {mode}")


def _run_case_mode(args: argparse.Namespace, root: Path, index: dict[str, Any], outline: list[dict[str, Any]], task: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode in {"symbol_select", "symbol_filtered_select_bundle"}:
        if mode == "symbol_filtered_select_bundle":
            selector_outline = _candidate_symbol_outline(index, task["question"], args.selector_candidates)
        else:
            selector_outline = outline
        selector_prompt = _selector_prompt(task["question"], selector_outline)
        selector = _run_llama(args, selector_prompt, "select")
        selected = URI_RE.search(selector["answer"])
        selected_uri = selected.group(0) if selected else None
        selection_correct = selected_uri == task["target_uri"]
        if selected_uri and selected_uri in symbol_map(index):
            if mode == "symbol_filtered_select_bundle":
                bundle = expand_symbol_context(
                    root,
                    index,
                    selected_uri,
                    question=task["question"],
                    numbered=False,
                    dependency_depth=args.bundle_depth,
                    max_symbols=args.bundle_max_symbols,
                )
                context = bundle["context"]
                bundle = {key: value for key, value in bundle.items() if key != "context"}
            else:
                bundle = {}
                selected_source = resolve_symbol(root, index, selected_uri, numbered=True)
                context = f"### selected_symbol: {selected_uri}\n```python\n{selected_source}\n```"
        else:
            bundle = {}
            context = f"### selected_symbol: {selected_uri}\nSelector did not return a resolvable symbol URI."
        answer_prompt = _answer_prompt(task["question"], context)
        answer = _run_llama(args, answer_prompt, "answer")
        answer_correct = _is_correct(answer["answer"], _required_substrings(task), _forbidden_substrings(task))
        correct = answer_correct if mode == "symbol_filtered_select_bundle" else selection_correct and answer_correct
        return {
            "mode": mode,
            "selected_uri": selected_uri,
            "selection_correct": selection_correct,
            "correct": correct,
            "answer_text": answer["answer"],
            "candidate_outline_symbols": sum(len(item["symbols"]) for item in selector_outline),
            **bundle,
            "calls": [selector, answer],
            "prompt_chars": selector["prompt_chars"] + answer["prompt_chars"],
            "estimated_prompt_tokens": selector["estimated_prompt_tokens"] + answer["estimated_prompt_tokens"],
            "wall_seconds": selector["wall_seconds"] + answer["wall_seconds"],
            "prompt_tokens": _sum_present([selector.get("prompt_tokens"), answer.get("prompt_tokens")]),
            "prompt_eval_ms": _sum_present([selector.get("prompt_eval_ms"), answer.get("prompt_eval_ms")]),
        }

    prompt, extra = _make_mode_prompt(mode, root, index, task)
    answer = _run_llama(args, prompt, "answer")
    return {
        "mode": mode,
        **extra,
        "correct": _is_correct(answer["answer"], _required_substrings(task), _forbidden_substrings(task)),
        "answer_text": answer["answer"],
        "calls": [answer],
        "prompt_chars": answer["prompt_chars"],
        "estimated_prompt_tokens": answer["estimated_prompt_tokens"],
        "wall_seconds": answer["wall_seconds"],
        "prompt_tokens": answer.get("prompt_tokens"),
        "prompt_eval_ms": answer.get("prompt_eval_ms"),
    }


def _sum_present(values: list[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _prepare_workspace(args: argparse.Namespace) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    work_dir = args.work_dir / args.scale
    manifest_path = work_dir / "manifest.json"
    regenerate = args.regenerate or not manifest_path.exists()
    if not regenerate:
        manifest = _read_json(manifest_path)
        regenerate = not Path(manifest["corpus_root"]).exists()
    if regenerate:
        manifest = generate_corpus(work_dir, args.scale, args.noise_files, args.noise_functions)
    root = Path(manifest["corpus_root"])
    index = _read_json(work_dir / "symbol_index.json")
    tasks_path = args.tasks_file or work_dir / "tasks.json"
    tasks = _read_json(tasks_path)
    outline = compact_outline(index)
    return root, index, outline, tasks, manifest


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("\nSummary")
    print("mode, cases, accuracy, mean_wall_s, mean_prompt_chars, mean_prompt_tokens")
    for mode in ALL_MODES:
        group = [row for row in rows if row["mode"] == mode]
        if not group:
            continue
        accuracy = sum(1 for row in group if row["correct"]) / len(group)
        prompt_tokens = [row["prompt_tokens"] or row["estimated_prompt_tokens"] for row in group]
        print(
            f"{mode}, {len(group)}, {accuracy:.2f}, "
            f"{mean(row['wall_seconds'] for row in group):.3f}, "
            f"{mean(row['prompt_chars'] for row in group):.0f}, "
            f"{mean(prompt_tokens):.0f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark full context vs line span vs symbol selector access.")
    parser.add_argument("--work-dir", type=Path, default=Path("symbol_test/work"))
    parser.add_argument("--scale", choices=sorted(SCALE_DEFAULTS), default="small")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--noise-files", type=int)
    parser.add_argument("--noise-functions", type=int)
    parser.add_argument("--tasks-file", type=Path)
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES, choices=ALL_MODES)
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--selector-candidates", type=int, default=24)
    parser.add_argument("--bundle-depth", type=int, default=1)
    parser.add_argument("--bundle-max-symbols", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", type=Path, default=Path(os.environ.get("LLAMA_MODEL", DEFAULT_MODEL)))
    parser.add_argument("--llama-bin", default=os.environ.get("LLAMA_BIN", "llama-completion"))
    parser.add_argument("--ctx-size", type=int, default=8192)
    parser.add_argument("--n-predict", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    root, index, outline, tasks, manifest = _prepare_workspace(args)
    if args.limit_cases:
        tasks = tasks[: args.limit_cases]
    if not args.dry_run and not args.model.exists():
        raise SystemExit(f"model not found: {args.model}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.out or args.work_dir / f"results_{args.scale}_{timestamp}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with output.open("w", encoding="utf-8") as handle:
        for run_no in range(args.runs):
            for task in tasks:
                for mode in args.modes:
                    started = time.strftime("%H:%M:%S")
                    print(f"[{started}] run={run_no + 1} task={task['id']} mode={mode}", flush=True)
                    result = _run_case_mode(args, root, index, outline, task, mode)
                    row = {
                        "run": run_no + 1,
                        "task_id": task["id"],
                        "question": task["question"],
                        "target_uri": task["target_uri"],
                        "expected_substrings": _required_substrings(task),
                        "forbidden_substrings": _forbidden_substrings(task),
                        "scale": args.scale,
                        "manifest": manifest,
                        **result,
                    }
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                    rows.append(row)

    print(f"\nWrote {len(rows)} rows -> {output}")
    _print_summary(rows)


if __name__ == "__main__":
    main()
