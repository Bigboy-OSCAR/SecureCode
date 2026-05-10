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

from .make_corpus import SCALE_DEFAULTS, generate_corpus
from .source_tools import compact_catalog, read_source, run_tool


DEFAULT_MODEL = Path("/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf")
DEFAULT_MODES = ["full_source", "pointer_oracle", "pointer_select"]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _answer_prompt(question: str, context: str) -> str:
    return f"""You are answering a benchmark about external disk sources.
Use only the provided context. Keep the answer short and exact.

Question:
{question}

Context:
{context}

Answer:
"""


def _full_source_context(work_dir: Path, manifest: dict[str, Any], task: dict[str, Any]) -> str:
    text = read_source(work_dir, manifest, task["pointer"])
    return f"### external source: {task['pointer']}\n```text\n{text}\n```"


def _pointer_context(task: dict[str, Any], tool_output: str) -> str:
    tool = task["tool"]
    return (
        f"### source pointer\n{task['pointer']}\n\n"
        f"### extraction tool\n{tool['name']}({json.dumps(tool['args'], ensure_ascii=False, separators=(',', ':'))})\n\n"
        f"### extracted content\n```text\n{tool_output}\n```"
    )


def _selector_prompt(question: str, catalog: list[dict[str, Any]]) -> str:
    tool_spec = [
        {
            "tool": "grep_log",
            "args": {
                "pointer": "source://log/...",
                "pattern": "regex string",
                "before": "integer context lines before match",
                "after": "integer context lines after match",
            },
        },
        {
            "tool": "extract_doc_section",
            "args": {
                "pointer": "source://doc/...",
                "query": "section heading or close phrase",
            },
        },
        {
            "tool": "extract_json_field",
            "args": {
                "pointer": "source://json/...",
                "path": "dot.path.to.field",
            },
        },
    ]
    return f"""You select one disk source extraction tool call.
Return exactly one compact JSON object on one line with keys "tool" and "args". No prose, no markdown.
Do not request raw file contents; use the pointer and an extraction tool.

Selection rules:
- If the question contains a request_id, use grep_log and set pattern to that exact request id.
- If the question asks for a named section, use extract_doc_section with that exact heading phrase.
- If the question asks for multiple JSON fields under one object, extract the parent object path from the catalog hints.
- Prefer a slightly broader extraction that contains all requested fields over a narrow path that may miss sibling fields.
- JSON paths are dot-separated object paths only. Do not use commas inside a JSON path.
- Example: for source_pointer_enabled and max_context_policy under northwind-prod security, use path "tenants.northwind-prod.security".

Question:
{question}

Source catalog:
{json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))}

Available tools:
{json.dumps(tool_spec, ensure_ascii=False, separators=(",", ":"))}

JSON:
"""


def _chat_wrap(user_prompt: str) -> str:
    return (
        "<|im_start|>system\n"
        "You are a precise tool-using assistant. Follow output constraints exactly."
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
            "raw_tail": "",
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
        "raw_tail": perf_output[-1200:],
    }


def _is_correct(answer: str, expected_substrings: list[str]) -> bool:
    folded = answer.casefold()
    return all(item.casefold() in folded for item in expected_substrings)


def _sum_present(values: list[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    candidates = [stripped]
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _run_case_mode(
    args: argparse.Namespace,
    work_dir: Path,
    manifest: dict[str, Any],
    catalog: list[dict[str, Any]],
    task: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    if mode == "full_source":
        context = _full_source_context(work_dir, manifest, task)
        answer = _run_llama(args, _answer_prompt(task["question"], context), "answer")
        return {
            "mode": mode,
            "correct": answer["returncode"] == 0 and _is_correct(answer["answer"], task["expected_substrings"]),
            "answer_text": answer["answer"],
            "selected_tool": None,
            "selection_correct": None,
            "tool_output_chars": None,
            "calls": [answer],
            "prompt_chars": answer["prompt_chars"],
            "estimated_prompt_tokens": answer["estimated_prompt_tokens"],
            "wall_seconds": answer["wall_seconds"],
            "prompt_tokens": answer.get("prompt_tokens"),
            "prompt_eval_ms": answer.get("prompt_eval_ms"),
        }

    if mode == "pointer_oracle":
        tool_output = run_tool(work_dir, manifest, task["tool"]["name"], task["tool"]["args"])
        answer = _run_llama(args, _answer_prompt(task["question"], _pointer_context(task, tool_output)), "answer")
        return {
            "mode": mode,
            "correct": answer["returncode"] == 0 and _is_correct(answer["answer"], task["expected_substrings"]),
            "answer_text": answer["answer"],
            "selected_tool": task["tool"],
            "selection_correct": True,
            "tool_output_chars": len(tool_output),
            "calls": [answer],
            "prompt_chars": answer["prompt_chars"],
            "estimated_prompt_tokens": answer["estimated_prompt_tokens"],
            "wall_seconds": answer["wall_seconds"],
            "prompt_tokens": answer.get("prompt_tokens"),
            "prompt_eval_ms": answer.get("prompt_eval_ms"),
        }

    if mode == "pointer_select":
        selector = _run_llama(args, _selector_prompt(task["question"], catalog), "select")
        selected_tool = _extract_json_object(selector["answer"])
        tool_output = "Selector did not return a valid tool JSON object."
        selection_correct = False
        if selected_tool and "tool" in selected_tool and "args" in selected_tool:
            try:
                tool_output = run_tool(work_dir, manifest, str(selected_tool["tool"]), dict(selected_tool["args"]))
                selection_correct = _is_correct(tool_output, task["expected_substrings"])
            except Exception as exc:  # noqa: BLE001 - benchmark records tool failures as data.
                tool_output = f"Tool execution failed: {exc}"
        context = (
            f"### selected tool call\n{json.dumps(selected_tool, ensure_ascii=False, indent=2)}\n\n"
            f"### extracted content\n```text\n{tool_output}\n```"
        )
        answer = _run_llama(args, _answer_prompt(task["question"], context), "answer")
        correct = answer["returncode"] == 0 and _is_correct(answer["answer"], task["expected_substrings"])
        return {
            "mode": mode,
            "correct": correct,
            "answer_text": answer["answer"],
            "selected_tool": selected_tool,
            "selection_correct": selection_correct,
            "tool_output_chars": len(tool_output),
            "calls": [selector, answer],
            "prompt_chars": selector["prompt_chars"] + answer["prompt_chars"],
            "estimated_prompt_tokens": selector["estimated_prompt_tokens"] + answer["estimated_prompt_tokens"],
            "wall_seconds": selector["wall_seconds"] + answer["wall_seconds"],
            "prompt_tokens": _sum_present([selector.get("prompt_tokens"), answer.get("prompt_tokens")]),
            "prompt_eval_ms": _sum_present([selector.get("prompt_eval_ms"), answer.get("prompt_eval_ms")]),
        }

    raise ValueError(f"unsupported mode: {mode}")


def _prepare_workspace(args: argparse.Namespace) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    work_dir = args.work_dir / args.scale
    manifest_path = work_dir / "manifest.json"
    regenerate = args.regenerate or not manifest_path.exists()
    if not regenerate:
        manifest = _read_json(manifest_path)
        regenerate = not Path(manifest["sources_root"]).exists()
    if regenerate:
        manifest = generate_corpus(work_dir, args.scale, args.log_lines, args.doc_sections, args.json_tenants)
    tasks = _read_json(work_dir / "tasks.json")
    catalog = compact_catalog(manifest)
    return work_dir, manifest, catalog, tasks


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("\nSummary")
    print("mode, cases, accuracy, mean_wall_s, mean_prompt_chars, mean_prompt_tokens, mean_prompt_eval_ms, selection_accuracy")
    for mode in DEFAULT_MODES:
        group = [row for row in rows if row["mode"] == mode]
        if not group:
            continue
        accuracy = sum(1 for row in group if row["correct"]) / len(group)
        prompt_tokens = [row["prompt_tokens"] or row["estimated_prompt_tokens"] for row in group]
        eval_values = [row["prompt_eval_ms"] for row in group if row.get("prompt_eval_ms") is not None]
        selections = [row["selection_correct"] for row in group if row.get("selection_correct") is not None]
        selection_accuracy = "" if not selections else f"{sum(1 for value in selections if value) / len(selections):.2f}"
        eval_mean = 0 if not eval_values else mean(eval_values)
        print(
            f"{mode}, {len(group)}, {accuracy:.2f}, "
            f"{mean(row['wall_seconds'] for row in group):.3f}, "
            f"{mean(row['prompt_chars'] for row in group):.0f}, "
            f"{mean(prompt_tokens):.0f}, {eval_mean:.2f}, {selection_accuracy}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark full external source injection vs source pointer extraction.")
    parser.add_argument("--work-dir", type=Path, default=Path("source_pointer_test/work"))
    parser.add_argument("--scale", choices=sorted(SCALE_DEFAULTS), default="small")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--log-lines", type=int)
    parser.add_argument("--doc-sections", type=int)
    parser.add_argument("--json-tenants", type=int)
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES, choices=DEFAULT_MODES)
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", type=Path, default=Path(os.environ.get("LLAMA_MODEL", DEFAULT_MODEL)))
    parser.add_argument("--llama-bin", default=os.environ.get("LLAMA_BIN", "llama-completion"))
    parser.add_argument("--ctx-size", type=int, default=32768)
    parser.add_argument("--n-predict", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    work_dir, manifest, catalog, tasks = _prepare_workspace(args)
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
                    result = _run_case_mode(args, work_dir, manifest, catalog, task, mode)
                    row = {
                        "run": run_no + 1,
                        "task_id": task["id"],
                        "question": task["question"],
                        "pointer": task["pointer"],
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
