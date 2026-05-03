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

from .indexer import compact_outline, read_span, resolve_symbol, symbol_map
from .make_corpus import SCALE_DEFAULTS, generate_corpus


DEFAULT_MODEL = Path("/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf")
DEFAULT_MODES = ["full_repo", "full_file", "line_span", "symbol_oracle", "symbol_select"]
URI_RE = re.compile(r"memory://symbol/[^\s'\"`]+::[A-Za-z_][\w.]*")


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
Use only the provided code context. Keep the answer short and exact.

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


def _is_correct(answer: str, expected_substrings: list[str]) -> bool:
    folded = answer.casefold()
    return all(item.casefold() in folded for item in expected_substrings)


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
    raise ValueError(f"unsupported single-prompt mode: {mode}")


def _run_case_mode(args: argparse.Namespace, root: Path, index: dict[str, Any], outline: list[dict[str, Any]], task: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "symbol_select":
        selector_prompt = _selector_prompt(task["question"], outline)
        selector = _run_llama(args, selector_prompt, "select")
        selected = URI_RE.search(selector["answer"])
        selected_uri = selected.group(0) if selected else None
        selection_correct = selected_uri == task["target_uri"]
        if selected_uri and selected_uri in symbol_map(index):
            selected_source = resolve_symbol(root, index, selected_uri, numbered=True)
            context = f"### selected_symbol: {selected_uri}\n```python\n{selected_source}\n```"
        else:
            context = f"### selected_symbol: {selected_uri}\nSelector did not return a resolvable symbol URI."
        answer_prompt = _answer_prompt(task["question"], context)
        answer = _run_llama(args, answer_prompt, "answer")
        correct = selection_correct and _is_correct(answer["answer"], task["expected_substrings"])
        return {
            "mode": mode,
            "selected_uri": selected_uri,
            "selection_correct": selection_correct,
            "correct": correct,
            "answer_text": answer["answer"],
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
        "correct": _is_correct(answer["answer"], task["expected_substrings"]),
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
    tasks = _read_json(work_dir / "tasks.json")
    outline = compact_outline(index)
    return root, index, outline, tasks, manifest


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("\nSummary")
    print("mode, cases, accuracy, mean_wall_s, mean_prompt_chars, mean_prompt_tokens")
    for mode in DEFAULT_MODES:
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
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES, choices=DEFAULT_MODES)
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument("--runs", type=int, default=1)
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
                        "expected_substrings": task["expected_substrings"],
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
