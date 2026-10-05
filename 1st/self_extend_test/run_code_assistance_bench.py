from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .llama2_selfextend_common import (
    MODELS,
    RESULTS,
    WORK,
    clean_generation,
    ensure_dirs,
    parse_perf,
    require_models,
    write_csv,
    write_json,
)


TASKS = [
    {
        "id": "function_definition",
        "question": "In the repository context, what exact string does derive_rotation_marker return when the region is apac and the shard id is 7? Answer only the exact string.",
        "expected": ["ROTATE::APAC::0007"],
    },
    {
        "id": "symbol_reference",
        "question": "Which function calls derive_rotation_marker inside schedulers/rotation.py? Answer only the function name.",
        "expected": ["schedule_rotation"],
    },
    {
        "id": "test_failure_cause",
        "question": "The failing test is test_rotation_marker_keeps_zero_padding. What is the precise root cause in code? Answer in one short sentence and include the bad expression.",
        "expected": ["lstrip", "0"],
    },
]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def noise_module(module_no: int, functions: int) -> str:
    blocks = [
        f'"""Noise module {module_no:03d} for long-context code assistant retrieval."""',
        f"MODULE_ID = {module_no}",
        "",
    ]
    for fn_no in range(functions):
        name = f"derive_rotation_marker_shadow_{module_no:03d}_{fn_no:03d}" if fn_no % 11 == 0 else f"helper_{module_no:03d}_{fn_no:03d}"
        blocks.append(
            f'''
def {name}(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + {fn_no})
    if shard.endswith("7"):
        return f"shadow:{{normalized}}:{{shard}}"
    return f"noise:{{normalized}}:{{shard}}"
'''
        )
    return "\n".join(blocks)


def generate_repo(root: Path, noise_files: int, noise_functions: int) -> dict[str, Any]:
    corpus = root / "code_assistant_repo"
    if corpus.exists():
        for old in corpus.rglob("*.py"):
            old.unlink()

    write(
        corpus / "schedulers" / "rotation.py",
        '''
from services.markers import derive_rotation_marker


def schedule_rotation(region: str, shard_id: int, urgent: bool = False) -> dict[str, str]:
    marker = derive_rotation_marker(region, shard_id)
    tier = "hot" if urgent else "normal"
    return {"marker": marker, "tier": tier}


def schedule_shadow_rotation(region: str, shard_id: int) -> str:
    return f"shadow::{region.lower()}::{shard_id}"
''',
    )
    write(
        corpus / "services" / "markers.py",
        '''
def derive_rotation_marker(region: str, shard_id: int) -> str:
    normalized = region.strip().upper()
    shard = f"{shard_id:04d}"
    return f"ROTATE::{normalized}::{shard}"


def derive_rotation_marker_buggy(region: str, shard_id: int) -> str:
    normalized = region.strip().upper()
    shard = f"{shard_id:04d}".lstrip("0")
    return f"ROTATE::{normalized}::{shard}"
''',
    )
    write(
        corpus / "tests" / "test_rotation.py",
        '''
from services.markers import derive_rotation_marker_buggy


def test_rotation_marker_keeps_zero_padding() -> None:
    assert derive_rotation_marker_buggy("apac", 7) == "ROTATE::APAC::0007"
''',
    )
    for module_no in range(noise_files):
        write(corpus / "noise" / f"module_{module_no:03d}.py", noise_module(module_no, noise_functions))

    files = sorted(path for path in corpus.rglob("*.py"))
    return {
        "corpus_root": str(corpus),
        "files": len(files),
        "noise_files": noise_files,
        "noise_functions": noise_functions,
    }


def repo_context(root: Path) -> str:
    chunks = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        chunks.append(f"### file: {rel}\n```python\n{path.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(chunks)


def prompt_for(question: str, context: str) -> str:
    return f"""[INST] You are a code analysis assistant. Use only the repository context. Keep the answer exact and brief.

Question:
{question}

Repository context:
{context}
[/INST]
"""


def run_llama(model_key: str, prompt: str, group: int, ctx_size: int, n_predict: int, timeout: int, seed: int) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".prompt.txt", encoding="utf-8", delete=False) as handle:
        handle.write(prompt)
        prompt_path = Path(handle.name)

    command = [
        "llama-completion",
        "-m",
        str(MODELS[model_key]),
        "-f",
        str(prompt_path),
        "-n",
        str(n_predict),
        "--ctx-size",
        str(ctx_size),
        "--no-display-prompt",
        "--temp",
        "0",
        "--seed",
        str(seed),
        "--simple-io",
        "-no-cnv",
        "--no-warmup",
        "--perf",
    ]
    if group != 1:
        command.extend(["--grp-attn-n", str(group)])

    start = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    finally:
        prompt_path.unlink(missing_ok=True)
    elapsed = time.monotonic() - start
    output = proc.stdout + "\n" + proc.stderr
    failure = ""
    if proc.returncode != 0:
        if "prompt is too long" in output:
            failure = "prompt_too_long"
        else:
            failure = "nonzero_exit"
    return {
        "returncode": proc.returncode,
        "failure": failure,
        "elapsed_sec": round(elapsed, 3),
        "answer": clean_generation(proc.stdout),
        **parse_perf(output),
        "raw_output": output,
    }


def is_correct(answer: str, expected: list[str]) -> bool:
    folded = answer.casefold()
    return all(item.casefold() in folded for item in expected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a long-repo code assistance benchmark with llama-completion Self-Extend.")
    parser.add_argument("--models", nargs="+", default=["q4_k_m", "q5_k_m"], choices=sorted(MODELS))
    parser.add_argument("--groups", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--ctx-size", type=int, default=0, help="Explicit ctx size for all groups. 0 uses base_ctx_size * group.")
    parser.add_argument("--base-ctx-size", type=int, default=4096)
    parser.add_argument("--noise-files", type=int, default=40)
    parser.add_argument("--noise-functions", type=int, default=30)
    parser.add_argument("--limit-tasks", type=int)
    parser.add_argument("--n-predict", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--out-prefix", default="llama2_code_assistance")
    args = parser.parse_args()

    ensure_dirs()
    require_models(args.models)
    manifest = generate_repo(WORK, args.noise_files, args.noise_functions)
    context = repo_context(Path(manifest["corpus_root"]))
    tasks = TASKS[: args.limit_tasks] if args.limit_tasks else TASKS

    rows = []
    for model_key in args.models:
        for group in args.groups:
            label = "off" if group == 1 else f"g{group}"
            ctx_size = args.ctx_size if args.ctx_size else args.base_ctx_size * group
            for task in tasks:
                prompt = prompt_for(task["question"], context)
                result = run_llama(model_key, prompt, group, ctx_size, args.n_predict, args.timeout, args.seed)
                case = f"{model_key}_{label}_{task['id']}"
                log_path = RESULTS / "code_assistance_logs" / f"{case}.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(result.pop("raw_output"), encoding="utf-8")
                row = {
                    "case": case,
                    "model": model_key,
                    "group": group,
                    "label": label,
                    "task_id": task["id"],
                    "expected": task["expected"],
                    "correct": result["returncode"] == 0 and is_correct(result["answer"], task["expected"]),
                    "ctx_size": ctx_size,
                    "prompt_chars": len(prompt),
                    "estimated_prompt_tokens": max(1, round(len(prompt) / 4)),
                    "manifest": manifest,
                    "log": str(log_path),
                    **result,
                }
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)

    write_json(RESULTS / f"{args.out_prefix}.json", rows)
    write_csv(RESULTS / f"{args.out_prefix}.csv", rows)


if __name__ == "__main__":
    main()
