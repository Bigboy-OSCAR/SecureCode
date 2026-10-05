"""Run the affected 24 benchmark cases and save their execution provenance."""

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path


out = Path(__file__).resolve().parent
base = out.parents[3]
model = base / "symbol_test/work/models/qwen2.5-coder-7b-instruct-q5_k_m.gguf"
hard = base / "symbol_test/tasks/medium_hard_tasks.json"
configs = [
    ("hard_bundle_rerun", ["symbol_bundle_oracle", "symbol_filtered_select_bundle"], 8192, hard),
    ("basic_full_repo_rerun", ["full_repo"], 65536, None),
    ("hard_default_rerun", ["full_repo", "full_file", "line_span", "symbol_oracle", "symbol_select"], 65536, hard),
]


def now():
    return datetime.datetime.now().astimezone().isoformat()


metadata = {
    "started_at": now(),
    "model": json.loads((model.parent / "model_origin.json").read_text()),
    "hardware": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
    "os": subprocess.check_output(["sw_vers"], text=True).strip(),
    "code_sha256": hashlib.sha256((base / "symbol_test/symbol_bench/run_benchmark.py").read_bytes()).hexdigest(),
    "task_sha256": hashlib.sha256(hard.read_bytes()).hexdigest(),
    "runs": [],
}
version = subprocess.run(["/opt/homebrew/bin/llama-completion", "--version"], capture_output=True, text=True)
metadata["llama_version"] = version.stdout + version.stderr
meta = out / "rerun_metadata.json"


def save():
    meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


save()
for name, modes, ctx, tasks in configs:
    result = out / (name + ".jsonl")
    command = [
        sys.executable, "-u", "-m", "symbol_test.symbol_bench.run_benchmark",
        "--scale", "medium", "--modes", *modes, "--model", str(model),
        "--llama-bin", "/opt/homebrew/bin/llama-completion", "--ctx-size", str(ctx),
        "--n-predict", "64", "--seed", "1", "--runs", "1", "--timeout", "300", "--out", str(result),
    ]
    if tasks:
        command += ["--tasks-file", str(tasks)]
    entry = {
        "name": name, "command": command, "started_at": now(), "ctx_size": ctx,
        "n_predict": 64, "seed": 1, "runs": 1, "timeout_seconds": 300, "result": str(result),
    }
    metadata["runs"].append(entry)
    save()
    print("Starting", name, flush=True)
    with (out / (name + "_execution.txt")).open("w") as log:
        process = subprocess.Popen(command, cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        returncode = process.wait()
    entry.update(returncode=returncode, finished_at=now())
    if returncode == 0:
        rows = [json.loads(line) for line in result.read_text().splitlines()]
        entry.update(cases=len(rows), successful_executions=sum(row["execution_ok"] for row in rows), correct=sum(row["correct"] for row in rows))
    save()
    if returncode:
        raise SystemExit(returncode)
    if name == "hard_bundle_rerun" and not entry["successful_executions"]:
        raise SystemExit("No bundle call executed successfully; inspect runtime errors.")
metadata["finished_at"] = now()
save()
print("All 24 real-model benchmark cases completed.", flush=True)
