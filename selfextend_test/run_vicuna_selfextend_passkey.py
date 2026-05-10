#!/usr/bin/env python3
import csv
import json
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = Path(
    "/Users/oscar/.cache/huggingface/hub/models--TheBloke--vicuna-7B-v1.5-GGUF/"
    "snapshots/8b4a138d6ba32660c42b5df6dad7ad5c23b80c8c/vicuna-7b-v1.5.Q4_K_M.gguf"
)
OUT_DIR = ROOT / "results"
OUT_DIR.mkdir(exist_ok=True)

BASE_CMD = [
    "llama-passkey",
    "-m",
    str(MODEL),
    "--keep",
    "32",
    "--predict",
    "64",
    "--temp",
    "0",
]

# junk ~= prompt length / 24 for llama-passkey's built-in haystack text.
CASES = [
    ("off", 1, 160, [16, 80, 144]),
    ("off", 1, 180, [18, 90, 162]),
    ("g2", 2, 160, [16, 80, 144]),
    ("g2", 2, 180, [18, 90, 162]),
    ("g2", 2, 320, [32, 160, 288]),
    ("g4", 4, 160, [16, 80, 144]),
    ("g4", 4, 180, [18, 90, 162]),
    ("g4", 4, 320, [32, 160, 288]),
]


def parse_output(stdout: str, stderr: str) -> dict:
    text = stdout + stderr
    passkey = None
    m = re.search(r"passkey = (\d+)", text)
    if m:
        passkey = m.group(1)

    # llama-passkey prints generated tokens to stdout and progress/perf to stderr.
    # Keeping them separate avoids false negatives from interleaved terminal output.
    answer = " ".join(stdout.split())

    prompt_tokens = None
    m = re.search(r"prompt tokens: (\d+)", text)
    if m:
        prompt_tokens = int(m.group(1))

    n_ctx = None
    m = re.search(r"main: n_len = \d+, n_ctx = (\d+)", text)
    if m:
        n_ctx = int(m.group(1))

    prompt_tps = None
    m = re.search(r"prompt eval time =.*?,\s+([0-9.]+) tokens per second", text)
    if m:
        prompt_tps = float(m.group(1))

    return {
        "passkey": passkey,
        "answer": answer,
        "correct": bool(passkey and passkey in answer),
        "prompt_tokens": prompt_tokens,
        "n_ctx": n_ctx,
        "prompt_tps": prompt_tps,
    }


def run_case(label: str, group: int, junk: int, pos: int, seed: int) -> dict:
    cmd = BASE_CMD + ["--junk", str(junk), "--pos", str(pos), "--seed", str(seed)]
    if group != 1:
        cmd.extend(["--grp-attn-n", str(group)])

    name = f"{label}_junk{junk}_pos{pos}_seed{seed}"
    start = time.monotonic()
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=240)
    elapsed = time.monotonic() - start
    combined = proc.stdout + proc.stderr
    (OUT_DIR / f"{name}.log").write_text(
        "=== STDOUT ===\n" + proc.stdout + "\n=== STDERR ===\n" + proc.stderr
    )

    parsed = parse_output(proc.stdout, proc.stderr)
    row = {
        "case": name,
        "label": label,
        "group": group,
        "junk": junk,
        "pos": pos,
        "depth": round(pos / junk, 3),
        "seed": seed,
        "returncode": proc.returncode,
        "elapsed_sec": round(elapsed, 3),
        **parsed,
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
    rows = []
    seed = 1
    for label, group, junk, positions in CASES:
        for pos in positions:
            row = run_case(label, group, junk, pos, seed)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    json_path = OUT_DIR / "vicuna_selfextend_passkey_results.json"
    csv_path = OUT_DIR / "vicuna_selfextend_passkey_results.csv"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
