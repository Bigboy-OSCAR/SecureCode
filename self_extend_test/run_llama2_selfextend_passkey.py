from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from .llama2_selfextend_common import MODELS, RESULTS, ensure_dirs, require_models, write_csv, write_json


FULL_CASES = [
    ("off", 1, 160, [16, 80, 144]),
    ("off", 1, 180, [18, 90, 162]),
    ("g2", 2, 160, [16, 80, 144]),
    ("g2", 2, 180, [18, 90, 162]),
    ("g2", 2, 320, [32, 160, 288]),
    ("g4", 4, 160, [16, 80, 144]),
    ("g4", 4, 180, [18, 90, 162]),
    ("g4", 4, 320, [32, 160, 288]),
]

QUICK_CASES = [
    ("off", 1, 160, [80, 144]),
    ("off", 1, 180, [90]),
    ("g2", 2, 160, [80, 144]),
    ("g2", 2, 180, [90, 162]),
    ("g2", 2, 320, [160, 288]),
    ("g4", 4, 320, [160, 288]),
]


def parse_output(stdout: str, stderr: str) -> dict:
    text = stdout + stderr
    passkey = None
    match = re.search(r"passkey = (\d+)", text)
    if match:
        passkey = match.group(1)

    answer = " ".join(stdout.split())

    prompt_tokens = None
    match = re.search(r"prompt tokens: (\d+)", text)
    if match:
        prompt_tokens = int(match.group(1))

    n_ctx = None
    match = re.search(r"main: n_len = \d+, n_ctx = (\d+)", text)
    if match:
        n_ctx = int(match.group(1))

    prompt_tps = None
    match = re.search(r"prompt eval time =.*?,\s+([0-9.]+) tokens per second", text)
    if match:
        prompt_tps = float(match.group(1))

    return {
        "passkey": passkey,
        "answer": answer,
        "correct": bool(passkey and passkey in answer),
        "prompt_tokens": prompt_tokens,
        "n_ctx": n_ctx,
        "prompt_tps": prompt_tps,
    }


def run_case(model_key: str, model: Path, label: str, group: int, junk: int, pos: int, seed: int, timeout: int) -> dict:
    command = [
        "llama-passkey",
        "-m",
        str(model),
        "--keep",
        "32",
        "--predict",
        "64",
        "--temp",
        "0",
        "--junk",
        str(junk),
        "--pos",
        str(pos),
        "--seed",
        str(seed),
    ]
    if group != 1:
        command.extend(["--grp-attn-n", str(group)])

    name = f"{model_key}_{label}_junk{junk}_pos{pos}_seed{seed}"
    start = time.monotonic()
    proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    elapsed = time.monotonic() - start
    combined = proc.stdout + proc.stderr
    log_path = RESULTS / "llama2_passkey_logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("=== STDOUT ===\n" + proc.stdout + "\n=== STDERR ===\n" + proc.stderr, encoding="utf-8")

    row = {
        "case": name,
        "model": model_key,
        "label": label,
        "group": group,
        "junk": junk,
        "pos": pos,
        "depth": round(pos / junk, 3),
        "seed": seed,
        "returncode": proc.returncode,
        "elapsed_sec": round(elapsed, 3),
        "log": str(log_path),
        **parse_output(proc.stdout, proc.stderr),
    }
    if proc.returncode != 0:
        if "failed to find a memory slot" in combined:
            row["failure"] = "context_slot_overflow"
        elif "Insufficient Memory" in combined:
            row["failure"] = "metal_oom"
        else:
            row["failure"] = "nonzero_exit"
    else:
        row["failure"] = ""
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Llama-2-7B-chat Self-Extend passkey tests.")
    parser.add_argument("--models", nargs="+", default=["q4_k_m", "q5_k_m"], choices=sorted(MODELS))
    parser.add_argument("--full", action="store_true", help="Run the full 48-case matrix instead of the quick matrix.")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out-prefix", default="llama2_selfextend_passkey")
    args = parser.parse_args()

    ensure_dirs()
    require_models(args.models)
    cases = FULL_CASES if args.full else QUICK_CASES
    rows = []
    for model_key in args.models:
        for label, group, junk, positions in cases:
            for pos in positions:
                row = run_case(model_key, MODELS[model_key], label, group, junk, pos, args.seed, args.timeout)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)

    write_json(RESULTS / f"{args.out_prefix}.json", rows)
    write_csv(RESULTS / f"{args.out_prefix}.csv", rows)


if __name__ == "__main__":
    main()

