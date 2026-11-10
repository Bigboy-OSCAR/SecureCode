"""Audit every paired sample, summarize observed effects, and write Korean report."""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np

sys.dont_write_bytecode = True
import run_experiment as run

OUT, HERE, REPO = run.OUT, run.HERE, run.REPO
REPORT = REPO / "2nd/Documents/Md_Files/2026-11-09_HumanEval+_Full_file_R0_비교_실험보고서.md"


def link(name, path):
    return f"[{name}]({Path(path).resolve()})"


def read_calls():
    return [run.read(p) for p in sorted((OUT / "calls").glob("*.json.gz"))]


def verify():
    run.validate()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(run.MODEL), local_files_only=True)
    token_counter = run.Counter(tokenizer)
    with gzip.open(OUT / "HumanEvalPlus-v0.1.10.jsonl.gz", "rt") as f:
        problems = {p["task_id"]: p for p in map(json.loads, f)}
    assert len(problems) == 164
    tasks = run.read(OUT / "tasks.json")
    assert len(tasks) == 164 and {t["task_id"] for t in tasks} == set(problems)
    assert {p.name for p in (OUT / "corpus").glob("*.py")} == {t["path"] for t in tasks}
    for t in tasks:
        assert set(t) == {"task_id", "entry_point", "path", "question"}
        p = problems[t["task_id"]]
        assert (OUT / "corpus" / t["path"]).read_text() == p["prompt"]
        assert t["question"] == run.request(p["entry_point"], t["path"])
    assets = run.read(OUT / "assets.json")
    nodes = run.original.source_nodes(OUT / "corpus")
    assert nodes == assets["nodes"]
    raw = run.original.raw_items(nodes)
    assert raw == assets["raw"]
    retriever = run.original.Retriever(raw)
    all_files = run.full_context()
    schedule = run.read(OUT / "schedule.json")
    calls = read_calls()
    grading = run.read(OUT / "grading/results.json")
    assert len(calls) == len(schedule) == len(grading) == 328
    assert Counter(c["task_id"] for c in calls) == {k: 2 for k in problems}
    assert Counter(c["arm"] for c in calls) == {"FULL": 164, "R0": 164}
    assert Counter(schedule[i]["arm"] for i in range(0, 328, 2)) == {"FULL": 82, "R0": 82}
    assert len(list((OUT / "intents").glob("*.json"))) == 328
    completion = run.read(OUT / "generation_complete.json")
    for path in (OUT / "calls").glob("*.json.gz"):
        assert run.sha(path) == completion["call_sha256"][path.name]
    recoveries = [run.read(p) for p in sorted((OUT / "recovery").glob("*/recovery.json"))]
    for recovery in recoveries:
        # A restart must never replace a completed response with another sample.
        for name, expected in recovery["completed_sha256"].items():
            assert run.sha(OUT / "calls" / name) == expected, name
    for i, (row, entry, score) in enumerate(zip(calls, schedule, grading)):
        assert all(row[k] == entry[k] == score[k] for k in ["index", "task_id", "arm"])
        assert row["index"] == i and row["status"] == "complete"
        assert row["task"] == tasks[int(row["task_id"].split("/")[1])]
        assert row["solution"] == run.clean_solution(row["answer"])
        assert row["solution_sha256"] == run.digest(row["solution"]) == score["solution_sha256"]
        if row["arm"] == "FULL":
            context, sources = all_files, set(nodes)
            assert row["chosen"] == [] and row["rejected"] == []
        else:
            ranked = retriever.ranked(row["task"]["question"], raw)
            context, n, chosen, rejected = run.original.pack(token_counter, ranked, run.CONFIG["r0_source_budget"])
            assert n <= 1024 and row["chosen"] == chosen and row["rejected"] == rejected
            sources = {u for c in chosen for u in c["source_uris"]}
        assert row["context"] == context
        assert row["context_tokens"] == token_counter.tokens(context)
        expected_prompt = run.format_prompt(tokenizer, row["task"]["question"], context)
        assert row["formatted_prompt"] == expected_prompt
        assert row["formatted_prompt_sha256"] == run.digest(expected_prompt)
        assert row["input_tokens"] == token_counter.tokens(expected_prompt)
        assert row["input_tokens"] + 2048 <= 32768
        assert row["source_count"] == len(sources)
        target = run.original.uri(row["task"]["path"], row["task"]["entry_point"])
        assert row["target_included"] == (target in sources)
        assert row["query_seconds"] > 0 and row["generation_seconds"] > 0
        assert abs(row["query_seconds"] - row["generation_seconds"] - row["preparation_seconds"]) < 0.1
        try:
            tree = ast.parse(row["solution"])
            syntax_ok = True
            has_entry = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == row["task"]["entry_point"] for n in tree.body)
        except SyntaxError:
            syntax_ok = has_entry = False
        assert row["syntax_ok"] == syntax_ok and row["has_entry_point"] == has_entry
        key = f"{i:03d}_{row['arm']}_{row['task_id'].replace('/', '_')}.json.gz"
        assert score["call_sha256"] == run.sha(OUT / "calls" / key)
        p = problems[row["task_id"]]
        assert score["base_pass"] == (score["base"]["status"] == "pass")
        assert score["plus_pass"] == (score["base_pass"] and score["plus"]["status"] == "pass")
        for group in ["base", "plus"]:
            s = score[group]
            assert s["tests"] == len(p[group + "_input"])
            if s["status"] == "pass":
                assert s["checked"] == s["tests"] and s["first_failure"] is None
    for i in range(0, 328, 2):
        assert calls[i]["task_id"] == calls[i + 1]["task_id"]
        assert calls[i]["task"]["question"] == calls[i + 1]["task"]["question"]
        assert calls[i]["arm"] != calls[i + 1]["arm"]
    grade_complete = run.read(OUT / "grading/complete.json")
    assert run.sha(OUT / "grading/results.json") == grade_complete["results_sha256"]
    assert run.sha(HERE / "evaluate_solutions.py") == grade_complete["driver_sha256"]
    adaptation = run.read(OUT / "grading/evaluator_adaptation.json")
    assert adaptation["driver_sha256"] == grade_complete["driver_sha256"]
    controls = run.read(OUT / "grading/controls.json")
    assert controls["verified"] and len(controls["records"]) == 164
    assert sum(r["plus_pass"] for r in controls["records"]) == 163
    negative = run.read(OUT / "grading/negative_control.json")
    assert not negative["HumanEval/0"]["plus_pass"] and not negative["HumanEval/32"]["plus_pass"]
    assert negative["known_valid_root_positive_control"]["plus_pass"]
    manifest = run.read(OUT / "model_manifest.json")
    for name, expected_hash in manifest["files_sha256"].items():
        assert run.sha(run.MODEL / name) == expected_hash, name
    audit = {
        "status": "PASS", "verified_at_utc": run.now(), "tasks": 164, "paired_calls": 328,
        "checks": ["Every corpus file equals public dataset prompt", "No gold/test field in generation task records",
                   "Original R0 AST, candidates, ranking and packing independently recomputed",
                   "Every FULL prompt contains all 164 unchanged files", "Every model input retokenized",
                   "All prompt/solution/call hashes match", "Balanced paired schedule and no missing/extra calls",
                   "Quality outcomes match official test statuses and test counts", "Evaluation controls audited",
                   "Every local model file hash rechecked", "Protocol and original source files unchanged"],
        "session_count": len({c["session"] for c in calls}),
        "interrupted_attempts": len(recoveries),
        "preserved_pre_interruption_calls_verified": [r["completed_preserved"] for r in recoveries],
        "report_driver_sha256": run.sha(__file__),
    }
    run.dump(OUT / "verification.json", audit)
    return calls, grading, problems


def summarize(calls, scores):
    keyed = {(r["task_id"], r["arm"]): {**r, **s} for r, s in zip(calls, scores)}
    ids = [f"HumanEval/{i}" for i in range(164)]
    byarm = {a: [keyed[(i, a)] for i in ids] for a in ["FULL", "R0"]}
    fields = ["input_tokens", "context_tokens", "output_tokens", "query_seconds", "preparation_seconds",
              "generation_seconds", "first_token_seconds", "peak_memory_gb", "source_count"]
    summary = {"created_at_utc": run.now(), "tasks": 164, "arms": {}, "paired": {}}
    for arm, rows in byarm.items():
        group = {
            "base_correct": sum(r["base_pass"] for r in rows), "plus_correct": sum(r["plus_pass"] for r in rows),
            "base_pass_percent": 100 * np.mean([r["base_pass"] for r in rows]),
            "plus_pass_percent": 100 * np.mean([r["plus_pass"] for r in rows]),
            "extra_tests_reject_base_pass": sum(r["base_pass"] and not r["plus_pass"] for r in rows),
            "target_included": sum(r["target_included"] for r in rows),
            "syntax_errors": sum(not r["syntax_ok"] for r in rows),
            "missing_entrypoint": sum(not r["has_entry_point"] for r in rows),
            "length_limited": sum(r["finish_reason"] == "length" for r in rows),
            "finish_reasons": dict(Counter(r["finish_reason"] for r in rows)),
        }
        for field in fields:
            values = np.array([r[field] for r in rows], dtype=float)
            group[field] = {"mean": float(values.mean()), "median": float(np.median(values)),
                            "p95": float(np.quantile(values, .95)), "sum": float(values.sum()),
                            "min": float(values.min()), "max": float(values.max())}
        summary["arms"][arm] = group
    f, r = byarm["FULL"], byarm["R0"]
    pairs = {"both_pass": [], "full_only": [], "r0_only": [], "neither_pass": []}
    for tid, a, b in zip(ids, f, r):
        label = "both_pass" if a["plus_pass"] and b["plus_pass"] else "full_only" if a["plus_pass"] else "r0_only" if b["plus_pass"] else "neither_pass"
        pairs[label].append(tid)
    summary["paired"] = {k: {"count": len(v), "task_ids": v} for k, v in pairs.items()}
    rng = np.random.default_rng(20261109)
    indices = rng.integers(0, 164, size=(10000, 164))
    contrasts = {}
    for name, field, scale, ratio in [
        ("plus_pass_difference_pp", "plus_pass", 100, False),
        ("base_pass_difference_pp", "base_pass", 100, False),
        ("query_seconds_difference", "query_seconds", 1, False),
        ("input_token_reduction_percent", "input_tokens", 100, True),
        ("query_time_reduction_percent", "query_seconds", 100, True),
    ]:
        fv, rv = np.array([x[field] for x in f], float), np.array([x[field] for x in r], float)
        if ratio:
            point = scale * (1 - rv.mean() / fv.mean())
            boot = scale * (1 - rv[indices].mean(axis=1) / fv[indices].mean(axis=1))
        else:
            point = scale * (rv - fv).mean()
            boot = scale * (rv - fv)[indices].mean(axis=1)
        contrasts[name] = {"estimate": float(point), "ci95": list(map(float, np.quantile(boot, [.025, .975])))}
    summary["contrasts"] = contrasts
    summary["mean_query_speedup"] = summary["arms"]["FULL"]["query_seconds"]["mean"] / summary["arms"]["R0"]["query_seconds"]["mean"]
    summary["sessions"] = sorted({c["session"] for c in calls})
    summary["session_counts"] = {session: dict(Counter(c["arm"] for c in calls if c["session"] == session))
                                 for session in summary["sessions"]}
    summary["interrupted_attempts"] = len(list((OUT / "recovery").glob("*/recovery.json")))
    same_session_ids = [tid for tid in ids if keyed[tid, "FULL"]["session"] == keyed[tid, "R0"]["session"]]
    summary["cross_session_pairs"] = [tid for tid in ids if tid not in same_session_ids]
    if same_session_ids:
        full_time = float(np.mean([keyed[tid, "FULL"]["query_seconds"] for tid in same_session_ids]))
        r0_time = float(np.mean([keyed[tid, "R0"]["query_seconds"] for tid in same_session_ids]))
        summary["same_session_timing_sensitivity"] = {
            "pairs": len(same_session_ids), "FULL_mean_seconds": full_time, "R0_mean_seconds": r0_time,
            "R0_minus_FULL_seconds": r0_time - full_time,
            "reduction_percent": 100 * (1 - r0_time / full_time),
            "scope": "Supplementary timing check only; primary quality, tokens, and timing keep all 164 pairs.",
        }
    summary["first_generation_utc"] = min(c["started_at_utc"] for c in calls)
    summary["last_generation_utc"] = max(c["ended_at_utc"] for c in calls)
    run.dump(OUT / "summary.json", summary)
    for arm in ["FULL", "R0"]:
        with (OUT / f"samples_{arm}.jsonl").open("w") as out:
            for row in byarm[arm]:
                out.write(json.dumps({"task_id": row["task_id"], "solution": row["solution"]}, ensure_ascii=False) + "\n")
    with (OUT / "per_task_results.jsonl").open("w") as out:
        for tid in ids:
            out.write(json.dumps({"task_id": tid, **{a: {k: keyed[tid, a][k] for k in ["base_pass", "plus_pass", "input_tokens", "output_tokens", "query_seconds", "target_included", "finish_reason"]} for a in ["FULL", "R0"]}}) + "\n")
    return summary, keyed


def report(s, keyed, problems):
    f, r = s["arms"]["FULL"], s["arms"]["R0"]
    c, p = s["contrasts"], s["paired"]
    pre = run.read(OUT / "preflight.json")
    delta_count = r["plus_correct"] - f["plus_correct"]
    if delta_count > 0:
        quality = f"R0에서 테스트를 모두 통과한 함수가 **{delta_count}개 늘었습니다**. 같은 164개 요청에 한 번씩 답하게 했을 때, 사용자가 추가 수정 없이 사용할 수 있는 후보를 테스트 기준으로 더 많이 얻었다는 의미입니다."
    elif delta_count < 0:
        quality = f"R0에서 테스트를 모두 통과한 함수가 **{-delta_count}개 줄었습니다**. 자료를 덜 읽히는 이득과 함께, 사용자가 오류를 수정하거나 다시 생성해야 하는 요청이 그만큼 늘어난 결과입니다."
    else:
        quality = "두 방식에서 테스트를 모두 통과한 함수 수는 같습니다. 전체 성공 수를 유지하면서 입력을 줄인 결과이지만, 개별 문항의 성공 여부까지 같다는 뜻은 아닙니다."
    ci = c["plus_pass_difference_pp"]["ci95"]
    uncertainty = ("이 범위에 0이 포함되므로, 이번 한 번의 실행만으로 어느 방식의 기능 정확도가 일관되게 높다고 단정하기 어렵습니다."
                   if ci[0] <= 0 <= ci[1] else "이 재표집 범위는 한쪽 방향에 머물렀습니다. 다만 이는 이번 문항 구성에 대한 민감도이며, 다른 모델·저장소에서도 같은 차이가 난다는 보장은 아닙니다.")
    def mean(g, field, digits=1):
        return f"{g[field]['mean']:,.{digits}f}"
    date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    def kst(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    qpp = c["plus_pass_difference_pp"]["estimate"]
    interruption_note = ""
    timing_sensitivity_note = ""
    if s["interrupted_attempts"]:
        interruption_note = (
            f"실행은 **{len(s['sessions'])}개 세션**으로 나뉘었습니다. 목표의 일시정지·재개 사이에 이전 계산 프로세스가 종료된 것을 확인했으며, "
            f"완료 결과는 그대로 보존하고 응답이 저장되지 않은 중단 시도 **{s['interrupted_attempts']}건**부터 재개했습니다. "
            "따라서 328개의 완료 해법 외에 미완료 시도가 별도로 존재합니다. 정답 여부를 보고 재시도한 것은 아닙니다. "
            "아래 토큰·시간 표는 완료된 요청 기준이며, 기록되지 않은 중단 시도의 계산량과 대기시간은 포함하지 않습니다. "
            "전체 작업에 실제 소비된 총 자원량을 이 표만으로 확정할 수는 없습니다.\n"
        )
    if s["cross_session_pairs"]:
        sensitivity = s["same_session_timing_sensitivity"]
        timing_sensitivity_note = (
            f"추가로 두 방식이 서로 다른 세션에서 실행된 **{', '.join(s['cross_session_pairs'])}**를 시간 분석에서만 빼고 확인했습니다. "
            f"같은 세션에서 비교된 **{sensitivity['pairs']}쌍**의 평균은 Full file **{sensitivity['FULL_mean_seconds']:.2f}초**, "
            f"R0 **{sensitivity['R0_mean_seconds']:.2f}초**, 시간 절감률 **{sensitivity['reduction_percent']:.2f}%**입니다. "
            "이는 재시작을 사이에 둔 비교가 전체 시간 차이에 얼마나 영향을 주는지 확인하는 보조 분석입니다. "
            "주 결과의 정확도·입력량·시간에는 모든 164쌍을 유지했습니다.\n"
        )
    storage_note = ""
    if (OUT / "generation_storage_audit.json").exists():
        storage = run.read(OUT / "generation_storage_audit.json")
        storage_note = (
            f"진행 중 Git 작업으로 작업 폴더에서 사라진 완료 응답 **{storage['git_stash_response_hashes_preserved']}개**는 임시 보관본에서 원본 그대로 복구했습니다. "
            "이 사건으로 재생성한 응답은 0개입니다. 최종 328개 응답은 완료 기록의 해시와 별도 사본을 모두 대조했고, "
            "일시정지 전 15개 및 Git 복구 4개의 원본 해시도 보존됐음을 확인했습니다.\n"
        )
    doc = f"""# HumanEval+에서 Full file과 R0를 비교한 실험

작성: {date} · 생성 실행: {kst(s['first_generation_utc'])} ~ {kst(s['last_generation_utc'])}

## 1. 결과와 의미

**164개 명세 파일을 모두 입력하는 Full file과, 기존 R0 검색으로 고른 원문만 입력하는 방식을 같은 Qwen3.8-27B 모델에서 비교했습니다.** 164문항마다 두 방식으로 완료한 해법 하나씩, 총 328개 해법을 새로 생성해 채점했습니다. HumanEval+ 전체 추가 테스트를 포함했으며, 누락된 문항이나 정답 여부를 보고 다시 생성한 해법은 없습니다.

R0는 질문당 평균 입력을 **{mean(f, 'input_tokens')} → {mean(r, 'input_tokens')}토큰**, 즉 **{c['input_token_reduction_percent']['estimate']:.2f}%** 줄였습니다. 이 수치는 모델이 읽어야 하는 자료와 지시문의 양이 줄었다는 뜻입니다. 평균 질의 처리시간은 **{mean(f, 'query_seconds', 2)} → {mean(r, 'query_seconds', 2)}초**로 바뀌었습니다. 기능 정확도는 **{f['plus_correct']}/164개({f['plus_pass_percent']:.2f}%) → {r['plus_correct']}/164개({r['plus_pass_percent']:.2f}%)**, 차이는 **{qpp:+.2f}%p**였습니다.

{quality}

정확도 차이의 문항 재표집 95% 구간은 **{ci[0]:+.2f} ~ {ci[1]:+.2f}%p**입니다. {uncertainty}

이 실험은 **HumanEval+의 독립적인 함수 명세를 하나의 가상 작업공간으로 묶은 비교**입니다. 표준 HumanEval+처럼 대상 명세 하나만 직접 주는 조건과 입력 구성이 다르며, 실제 저장소의 파일 간 의존성을 찾아가는 실험도 아닙니다. 따라서 아래 결과를 공식 모델 순위표의 점수나 일반적인 저장소 검색 성능으로 그대로 해석하면 안 됩니다.

## 2. 무엇을 비교했는가

### 2.1 데이터와 입력 구성

데이터셋은 **HumanEval+**이며, EvalPlus의 **HumanEvalPlus v0.1.10 전체 164문항**을 사용했습니다. 기본 테스트는 **{pre['base_tests']:,}개**, 추가 테스트는 **{pre['extra_tests']:,}개**, 합계 **{pre['base_tests'] + pre['extra_tests']:,}개**입니다. 이 개수는 각 문항에 준비된 검증 입력을 합한 것으로, 실패한 해법까지 모든 입력을 끝까지 실행했다는 뜻은 아닙니다. 채점기는 첫 실패 이후 해당 테스트 묶음의 실행을 중단할 수 있습니다. [공식 데이터 설명](https://github.com/evalplus/evalplus/blob/master/docs/cli.md), [사용한 배포본](https://github.com/evalplus/humanevalplus_release/releases/tag/v0.1.10)

각 문항의 공개 `prompt`를 `task_000.py`부터 `task_163.py`까지 한 파일씩 저장했습니다. 파일에는 문제에서 원래 제공하는 함수 선언·설명·예시와 공개 보조 코드가 들어갑니다. **정답 구현, 별도 계약 조건, 채점용 기본·추가 입력과 테스트 코드는 검색 자료 및 모델 입력에서 제외했습니다.** 공개 설명문 안의 예시는 원래 문제의 일부이므로 보존했습니다.

두 방식에 동일하게 “지정한 파일의 지정한 함수를 설명에 맞게 구현하라”는 요청을 전달했습니다. 요청에는 함수 이름과 파일 경로만 들어가며, 대상 설명문을 별도로 다시 붙이지 않았습니다. 함수 이름이 중복되는 문항이 있으므로 경로까지 지정했습니다.

| 비교 항목 | Full file | R0 |
|---|---|---|
| 모델에게 제공한 자료 | 164개 파일의 전체 원문, 파일명 순서 | TF-IDF 검색으로 선택한 함수·상수 원문 |
| 자료 크기 제한 | 전체를 보존; 자르지 않음 | 출처 표시를 포함한 원문 자료 최대 1,024토큰 |
| 자료를 고르는 과정 | 전체 파일 읽기 | 기존 코드의 AST 색인 → 원문 후보 → 유사도 순위 → 예산 안에 통째로 담기 |
| 추가 모델 선택 호출 | 없음 | 없음 |
| 질문당 채점한 완료 해법 | 1개 | 1개 |
| 정답·숨겨진 테스트 제공 | 없음 | 없음 |

**R0는 프로그램이 색인과 검색 점수로 자료를 고른 뒤, 선택한 실제 원문을 모델에게 전달하는 방식입니다.** 함수 단위 후보와 깊이 3의 의존성 묶음을 만드는 기존 `source_nodes`·`raw_items`·`Retriever`·`pack`을 수정 없이 재사용했습니다. 이번 공개 명세에서는 노드 **{pre['source_nodes']}개**, 연결 **{pre['dependency_edges']}개**가 나왔습니다. 연결이 없으므로 이번 결과가 검증하는 것은 주로 이름·경로로 필요한 함수 명세를 찾아 입력을 줄이는 효과입니다.

### 2.2 고정한 실행 조건

| 항목 | 조건과 이 조건을 둔 이유 |
|---|---|
| 모델 | 로컬 `Qwen3.8-27B-MLX-5bit` 배포본; 두 방식이 같은 모델 파일을 사용하도록 해 검색 방식 외의 차이를 줄임 |
| 장비·실행 도구 | Apple M3 Pro, 메모리 36GiB, Python 3.12.11, MLX 0.32.4 / MLX-LM 0.32.2 |
| 입력·출력 공간 | 32,768토큰 한도, 출력 최대 2,048토큰 예약; 모든 전체 입력이 실제로 들어가는지 사전 확인 |
| 생성 설정 | temperature 0, seed 1, 추론 모드 비활성화, 질문마다 새 프롬프트 캐시 |
| 실행 순서 | 문항 순서를 고정 seed로 섞고 같은 문항의 두 방식을 연속 실행; Full file 선행 82쌍, R0 선행 82쌍 |
| 응답 후처리 | 바깥 공백과 완전한 바깥 코드 울타리 하나만 제거; 코드 수정·정답 프롬프트 추가·재시도 없음 |
| 채점 | EvalPlus 0.3.1의 실행·허용오차·시간제한과 특수 판정 사용; 아래 6절의 공개 보정 적용 |

문항·방식마다 완료된 해법 하나씩을 채점했으며, 여러 완료 답 중 가장 좋은 답을 고르지 않았습니다. 모델 파일 전체의 SHA-256을 시작 전과 검증 시 대조했고, 자료와 생성 설정은 응답 생성 전에 고정했습니다.

{interruption_note}
{storage_note}
## 3. 지표가 측정하는 것과 실제 결과

### 3.1 기능 정확도: 한 번 작성한 함수가 실제 입력에서도 동작하는가

**HumanEval+ pass@1**은 요청마다 한 번 생성한 코드가 해당 문항의 기본 테스트와 추가 테스트를 모두 통과한 비율입니다. 예시 몇 개에만 맞춘 코드보다, 다양한 입력과 경계 조건에서도 요구 기능을 지키는 코드를 얼마나 많이 만드는지 보기 위한 지표입니다. 높을수록 이 테스트 범위 안에서 수정이 필요한 함수가 적습니다. 테스트가 모든 가능한 입력을 증명하는 것은 아닙니다.

**기본 HumanEval pass@1**은 원래의 기본 테스트만 통과했는지 봅니다. 추가 테스트를 붙였을 때 점수가 내려간 문항은, 간단한 검증에서는 드러나지 않았던 오류를 더 엄격한 검사로 발견한 사례입니다. **%p**는 두 비율 사이의 차이입니다. 여기서는 문항 하나가 약 **0.61%p**에 해당합니다.

| 지표 | Full file | R0 | R0의 변화와 의미 |
|---|---:|---:|---|
| **HumanEval+ pass@1** | **{f['plus_pass_percent']:.2f}% ({f['plus_correct']}/164)** | **{r['plus_pass_percent']:.2f}% ({r['plus_correct']}/164)** | **{qpp:+.2f}%p**, 전체 테스트를 통과한 함수 {delta_count:+d}개 |
| 기본 HumanEval pass@1 | {f['base_pass_percent']:.2f}% ({f['base_correct']}/164) | {r['base_pass_percent']:.2f}% ({r['base_correct']}/164) | {c['base_pass_difference_pp']['estimate']:+.2f}%p; 기본 검증을 통과하는 비율의 차이 |
| 기본 테스트는 통과했으나 추가 테스트에서 탈락 | {f['extra_tests_reject_base_pass']}개 | {r['extra_tests_reject_base_pass']}개 | 기본 검사에서 놓쳤던 실패를 추가 검사로 발견한 수; 단독으로 품질 순위를 매기지 않음 |
| 파이썬 문법 오류 | {f['syntax_errors']}개 | {r['syntax_errors']}개 | 실행 전에 코드 자체를 읽을 수 없는 실패; 작을수록 좋음 |
| 출력 길이 한도 도달 | {f['length_limited']}개 | {r['length_limited']}개 | 코드가 끝나기 전에 잘렸을 가능성을 점검하는 수치; 성공으로 간주하지 않고 나온 코드 그대로 채점 |

추가 테스트에서 탈락한 수는 **기본 테스트를 통과한 해법들 안에서** 드러난 실패를 세는 진단 지표입니다. 기본 테스트부터 실패한 코드가 많아도 이 수는 작아질 수 있으므로, 이 값만 낮다고 품질이 좋아졌다고 해석하지 않습니다. 전체 품질 비교에는 기본·추가 테스트를 함께 통과한 비율을 사용합니다.

같은 164문항의 결과를 짝지어 보면 다음과 같습니다. 전체 성공 수만으로 가려지는, 어떤 요청에서 결과가 바뀌었는지 보여줍니다.

| 문항의 결과 | 개수 | 해석 |
|---|---:|---|
| 두 방식 모두 통과 | {p['both_pass']['count']} | 입력 방식이 달라도 요구 기능을 만족한 요청 |
| Full file만 통과 | {p['full_only']['count']} | R0로 바꿨을 때 성공을 잃은 요청 |
| R0만 통과 | {p['r0_only']['count']} | R0로 바꿨을 때 새로 성공한 요청 |
| 두 방식 모두 실패 | {p['neither_pass']['count']} | 입력 방식 변경만으로 해결되지 않은 요청 |

정확도 차이 **{qpp:+.2f}%p**의 문항 단위 짝지은 부트스트랩 95% 구간은 **{ci[0]:+.2f} ~ {ci[1]:+.2f}%p**입니다. 같은 문항의 Full file·R0 결과를 한 쌍으로 유지한 채 164쌍을 복원추출해 10,000번 계산했습니다. 이 구간은 **평가 문항의 구성이 조금 달라질 때 평균 차이가 얼마나 흔들리는지** 확인하기 위한 것입니다. {uncertainty} 모델의 반복 생성 변동이나 실행일 차이는 이 구간에 들어 있지 않습니다.

### 3.2 입력 토큰: 모델에게 읽히는 양을 얼마나 줄였는가

**토큰**은 모델이 글과 코드를 나눠 처리하는 단위입니다. 입력 토큰 수는 한 요청을 풀기 위해 모델에게 얼마나 많은 자료를 읽히는지 측정합니다. 더 적은 입력으로 같은 기능 정확도를 유지한다면, 제한된 입력 공간을 아끼고 불필요한 자료 읽기를 줄인 것입니다. 토큰 감소 자체가 정확도 상승이나 같은 비율의 비용·메모리 절감을 보장하지는 않습니다.

| 지표 | Full file | R0 | 의미 |
|---|---:|---:|---|
| 평균 총 입력 토큰 | {mean(f, 'input_tokens')} | {mean(r, 'input_tokens')} | 원문뿐 아니라 파일 표시·질문·시스템 지시문·대화 형식을 모두 포함한 실제 입력량 |
| 평균 원문 자료 영역 토큰 | {mean(f, 'context_tokens')} | {mean(r, 'context_tokens')} | 원문과 출처 표시로 구성한 자료 영역의 크기; 질문·시스템 지시문은 제외 |
| 완료된 164회 총 입력 토큰 | {f['input_tokens']['sum']:,.0f} | {r['input_tokens']['sum']:,.0f} | 같은 전체 요청 묶음의 완료 응답에 대응하는 누적 입력량 |
| 평균 출력 토큰 | {mean(f, 'output_tokens')} | {mean(r, 'output_tokens')} | 생성한 코드 길이; 짧다는 이유만으로 품질이 좋다고 판단하지 않음 |
| 평균 제공 소스 노드 수 | {mean(f, 'source_count')} | {mean(r, 'source_count')} | 모델이 함께 받은 함수·상수 단위 원문의 수 |

누적 입력 절감률은 `100 × (1 − R0 총 입력 / Full file 총 입력)`으로 계산해 **{c['input_token_reduction_percent']['estimate']:.2f}%**였습니다. 이는 같은 164개 요청에서 읽힌 입력이 그만큼 줄었다는 뜻입니다. 외부 유료 API를 사용하지 않았으므로 이 비율을 금전 절약액으로 환산하지 않았습니다.

### 3.3 질의 처리시간: 코드가 완성될 때까지 얼마나 기다리는가

**총 질의 처리시간**은 모델이 이미 로딩된 상태에서 파일 읽기 또는 검색을 시작해, 코드 생성과 장치의 계산 완료 확인을 끝낼 때까지의 시간입니다. 한 요청의 코드가 완성되기를 기다리는 시간을 비교하기 위한 지표이므로, 낮을수록 답의 생성이 빨리 끝납니다. 자료 구성·토큰 계산·모델의 입력 처리·코드 생성을 포함합니다. 모델 로딩·사전 색인·준비 실행, 측정 전 캐시 정리와 실행 기록 작성, 생성 후 응답 정리·파일 저장·채점은 제외했습니다. 네트워크 전송이나 실제 화면 표시 시간도 측정하지 않았으므로, 전체 작업 경과시간이나 서비스의 전체 응답시간과 구분해야 합니다.

평균은 전체 요청 묶음의 총 대기 부담을, 중앙값은 가운데에 있는 요청의 대기를 보여줍니다. 95백분위는 느린 쪽 요청의 대기를 살피는 지표로, 이번 관측값의 약 95%가 그 시간 이하입니다. 각 문항을 한 번만 측정했으므로 운영 환경의 안정적인 지연 보장 수치는 아닙니다.

| 지표 | Full file | R0 |
|---|---:|---:|
| 평균 총 질의 처리시간 | {mean(f, 'query_seconds', 2)}초 | {mean(r, 'query_seconds', 2)}초 |
| 중앙값 | {f['query_seconds']['median']:.2f}초 | {r['query_seconds']['median']:.2f}초 |
| 95백분위 | {f['query_seconds']['p95']:.2f}초 | {r['query_seconds']['p95']:.2f}초 |
| 평균 첫 생성 토큰 반환시간 | {mean(f, 'first_token_seconds', 2)}초 | {mean(r, 'first_token_seconds', 2)}초 |
| 평균 자료 준비시간 | {mean(f, 'preparation_seconds', 3)}초 | {mean(r, 'preparation_seconds', 3)}초 |
| 평균 모델 처리시간 | {mean(f, 'generation_seconds', 2)}초 | {mean(r, 'generation_seconds', 2)}초 |

**첫 생성 토큰 반환시간**은 자료 준비를 시작한 뒤 모델이 첫 생성 토큰을 반환하기까지 걸린 시간으로, 응답이 시작되기 전의 대기를 살피는 지표입니다. 실제 화면에 첫 글자가 표시된 시각은 따로 측정하지 않았습니다. **자료 준비시간**은 파일 읽기 또는 검색·자료 선택·입력 구성·토큰 계산에 드는 부담을, **모델 처리시간**은 입력을 읽고 코드를 생성하는 부담을 구분해서 보기 위한 값입니다. 첫 토큰 반환시간은 총 처리시간에 포함되는 구간이므로 총 시간에 다시 더하지 않습니다.

평균 총 질의 처리시간의 절감률은 **{c['query_time_reduction_percent']['estimate']:.2f}%**, Full file 시간을 R0 시간으로 나눈 비는 **{s['mean_query_speedup']:.2f}배**였습니다. 이번 장비와 설정에서는 한 해법이 완성되기까지의 처리 대기가 평균 **{f['query_seconds']['mean'] - r['query_seconds']['mean']:.2f}초(약 {(f['query_seconds']['mean'] - r['query_seconds']['mean']) / 60:.2f}분)** 짧아진 결과입니다. 이 배수는 평균 처리시간의 비이며, 동시 요청 처리량을 측정한 값은 아닙니다. 입력 길이뿐 아니라 생성한 코드의 길이도 달라지므로, 시간 차이를 전부 검색 효과 하나로 분리해 설명할 수는 없습니다.

R0−Full file 평균 시간 차이는 **{c['query_seconds_difference']['estimate']:+.2f}초**, 문항을 짝지어 재표집한 95% 구간은 **{c['query_seconds_difference']['ci95'][0]:+.2f} ~ {c['query_seconds_difference']['ci95'][1]:+.2f}초**입니다. 발열·다른 앱의 작업·실행 순서가 영향을 줄 수 있어, 순서를 균형 있게 섞고 프롬프트 캐시 재사용을 막았습니다. 반복 측정으로 기기 상태의 영향을 따로 추정하지는 않았습니다.

**이 시간 비교는 요청 간 프롬프트 캐시를 재사용하지 않은 조건입니다.** 공통 문서 접두부의 계산을 재사용하는 배포 설정은 측정하지 않았습니다. 따라서 이번 시간 절감률을 그런 서비스 환경에 그대로 적용할 수는 없습니다.

{timing_sensitivity_note}

### 3.4 명세 포함률과 사전 작업

**대상 명세 포함률**은 요청한 함수의 공개 원문 노드가 실제 모델 입력에 들어갔는지 확인합니다. 검색 단계에서 문제 설명을 놓쳐 모델이 추측해야 하는 상황이 얼마나 생기는지 보기 위한 지표입니다. Full file은 **{f['target_included']}/164**, R0도 **{r['target_included']}/164**였습니다. R0가 이번 명세를 모두 포함했지만, 이것만으로 모델이 설명을 정확히 따랐다는 뜻은 아닙니다. 보조 함수까지 원래 파일 전체가 보존됐다는 지표도 아닙니다.

사전 AST 추출·후보 생성·검색 벡터 구성에는 **{pre['index_build_seconds']:.4f}초**가 걸렸습니다. 이는 첫 요청 전에 자료를 검색 가능한 형태로 만드는 비용이며, 질의 시간 표와 별도로 기록했습니다. 현재 작은 자료 묶음에서 한 번 잰 값이므로 큰 저장소의 구축 시간으로 일반화하지 않습니다.

## 4. 문항별 변화의 근거

"""
    changed = []
    for category in ["r0_only", "full_only"]:
        for tid in p[category]["task_ids"][:3]:
            a, b = keyed[tid, "FULL"], keyed[tid, "R0"]
            changed.append(f"| {tid} · `{problems[tid]['entry_point']}` | {'통과' if a['plus_pass'] else '실패'} | {'통과' if b['plus_pass'] else '실패'} | {a['input_tokens']:,} → {b['input_tokens']:,} | {a['query_seconds']:.2f} → {b['query_seconds']:.2f}초 |")
    if changed:
        doc += "아래는 성공 여부가 달라진 문항을 각 방향에서 문항 번호 순으로 최대 3개씩 제시한 것입니다. 전체 경향을 대표한다고 임의로 가정하지 않았으며, 전체 문항의 결과도 별도 파일로 보존했습니다.\n\n| 문항·함수 | Full file | R0 | 입력 토큰 | 총 질의 시간 |\n|---|---|---|---:|---:|\n" + "\n".join(changed) + "\n\n"
    else:
        doc += "두 방식 사이에서 HumanEval+ 통과 여부가 바뀐 문항은 없습니다.\n\n"
    if (HERE / "case_notes.md").exists() and (OUT / "case_diagnostics.json").exists():
        doc += (HERE / "case_notes.md").read_text().strip() + "\n\n"
    doc += f"""## 5. 해석의 범위

- **검색하기 쉬운 요청 형태입니다.** 함수 이름과 파일 경로를 요청에 제공했으므로 이름을 모르는 자연어 질문보다 대상 탐색이 쉽습니다. 별도의 경로 정답 강제 선택이나 검색 실패 시 정답 명세 추가는 사용하지 않았습니다.
- **파일 간 의존성 탐색 효과는 측정하지 못했습니다.** 독립적인 문제 명세를 묶었고 실제 추출된 연결도 0개입니다. 많은 코드 파일이 서로 호출하는 저장소에서 R0가 필요한 구현을 모두 찾아오는지는 별도 실험이 필요합니다.
- **두 입력 구성 전체를 비교한 결과입니다.** 자료의 양뿐 아니라 선택된 내용·배치 순서·파일 또는 함수 표시 형식도 달라집니다. 정확도 차이를 이 요인 중 하나의 독립적인 효과로 분리하지는 않았습니다.
- **표준 HumanEval+ 모델 점수와 직접 비교할 수 없습니다.** 전체 164문항과 공식 테스트를 썼지만 입력을 작업공간 검색 형태로 바꿨습니다. 공개 벤치마크가 모델 학습에 포함됐는지까지 확인한 실험도 아닙니다.
- **한 모델·한 장비·한 번의 생성입니다.** 더 큰 저장소, 다른 R0 예산, 모델 변경, 반복 실행의 결과를 여기서 예측할 수 없습니다. 부트스트랩도 공유된 자료와 서로 비슷한 문제를 새로운 독립 저장소로 바꿔 주지는 않습니다.
- **성공은 테스트 범위 안에서의 성공입니다.** 코드 보안, 모든 미지 입력, 유지보수성, 전력 사용량, 유료 서비스 비용은 별도 측정하지 않았습니다.

## 6. 채점 도구 검증과 보정

모델 해법을 채점하기 전에 배포된 정답 구현으로 평가 경로를 확인했습니다. EvalPlus 0.3.1에서는 macOS의 주소 공간 제한 설정이 오류를 일으켜, 공식 환경 변수 `EVALPLUS_MAX_MEMORY_BYTES=-1`로 해당 선택적 메모리 제한을 해제했습니다. 테스트별 시간제한·오류 격리 기능은 유지했습니다.

또한 다항식의 근을 구하는 `HumanEval/32`의 성공 판정 뒤 합격 기록을 빠뜨리는 0.3.1의 문제를 확인했습니다. **현재 공식 상위 소스에 있는 합격·진행 기록 보정만 반영**했으며, 다항식 잔차를 검사하는 판정 기준이나 허용오차는 바꾸지 않았습니다. [공식 판정 구현](https://github.com/evalplus/evalplus/blob/master/evalplus/eval/__init__.py)

보정 후 배포 정답 중 **163/164개**는 기본·추가 테스트를 모두 통과했습니다. 나머지 `HumanEval/32`는 배포된 Newton 방식 정답이 추가 입력 **6개**에서 요구 잔차를 만족하지 못했습니다. 이는 모델 응답을 보기 전에 확인된 참조 풀이의 수치 계산 문제입니다. 이 문항은 정답 코드의 반환값과 비교하지 않고 **반환한 근이 실제 다항식을 충분히 0에 가깝게 만드는지** 판정하므로, 부정확한 참조 반환값을 정답으로 강제하지 않았습니다. 해당 문항과 모든 테스트를 그대로 유지했습니다. 알려진 올바른 근은 통과하고 잘못된 근은 탈락하는 별도 양성·음성 대조도 확인했습니다.

최종 검증은 328개 입력을 다시 구성·토큰 계산하고, R0 선택 결과를 재계산하며, 원문·응답·채점 기록·모델 파일의 해시를 대조했습니다. 이는 저장된 실험 기록이 설계와 일치한다는 검증이며, 외부 기관의 성능 인증을 뜻하지는 않습니다.

## 7. 원자료와 재현

| 자료 | 경로 |
|---|---|
| 고정한 실험 조건 | {link('protocol.json', OUT / 'protocol.json')} |
| 데이터 출처와 해시 | {link('download.json', OUT / 'download.json')} |
| 사전 입력·검색 점검 | {link('preflight.json', OUT / 'preflight.json')} |
| 모델 배포본과 고정 버전 확인 | {link('model_provenance.json', OUT / 'model_provenance.json')} |
| 중단·재개와 기존 결과 보존 기록 | {link('recovery 폴더', OUT / 'recovery')} |
| 집계 수치와 구간 | {link('summary.json', OUT / 'summary.json')} |
| 164문항의 방식별 결과 | {link('per_task_results.jsonl', OUT / 'per_task_results.jsonl')} |
| 전체 입력·출력·시간 | {link('calls 폴더', OUT / 'calls')} |
| 실제 테스트 판정 | {link('grading/results.json', OUT / 'grading/results.json')} |
| 참조 풀이 점검 | {link('grading/controls.json', OUT / 'grading/controls.json')} |
| 평가 보정의 정확한 내용 | {link('evaluator_adaptation.json', OUT / 'grading/evaluator_adaptation.json')} |
| 전수 검증 | {link('verification.json', OUT / 'verification.json')} |
| 원본·사본·복구 결과 보존 검증 | {link('generation_storage_audit.json', OUT / 'generation_storage_audit.json')} |
| 원자료로 독립 재계산한 수치 검증 | {link('independent_stats_review.json', OUT / 'independent_stats_review.json')} |
| 사례의 실제 입력·출력 확인 | {link('case_diagnostics.json', OUT / 'case_diagnostics.json')} |
| 실행·채점·집계 코드 | {link('실험 폴더', HERE)} |

생성 결과는 {link('Full file 해법', OUT / 'samples_FULL.jsonl')}과 {link('R0 해법', OUT / 'samples_R0.jsonl')}에도 문항별로 저장했습니다. 원문 입력과 생성 로그를 보존했으므로 실패 사례도 확인할 수 있습니다. 사전 실험·이전 QASPER 결과는 이번 결과에 섞지 않았습니다.

기존 결과를 검증하고 보고서를 다시 만들려면 저장소 루트에서 다음 명령을 실행합니다. 새 생성 실험은 기존 기록을 덮어쓰지 않고 출력 폴더를 바꿔 별도 실행해야 합니다.

```sh
2nd/experiments/humaneval_benchmark/.venv/bin/python 2nd/experiments/humaneval_benchmark/analyze_and_report.py
```
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(doc)
    run.dump(OUT / "report_manifest.json", {"created_at_utc": run.now(), "report": str(REPORT),
        "report_sha256": run.sha(REPORT), "summary_sha256": run.sha(OUT / "summary.json"),
        "verification_sha256": run.sha(OUT / "verification.json"),
        "analysis_code_sha256": run.sha(__file__),
        "case_notes_sha256": run.sha(HERE / "case_notes.md") if (HERE / "case_notes.md").exists() and (OUT / "case_diagnostics.json").exists() else None,
        "case_diagnostics_sha256": run.sha(OUT / "case_diagnostics.json") if (OUT / "case_diagnostics.json").exists() else None})


if __name__ == "__main__":
    calls, scores, problems = verify()
    summary, keyed = summarize(calls, scores)
    report(summary, keyed, problems)
    print(json.dumps({"report": str(REPORT), "plus_pass": {a: summary['arms'][a]['plus_pass_percent'] for a in ['FULL', 'R0']},
                      "verification": "PASS"}, ensure_ascii=False), flush=True)
