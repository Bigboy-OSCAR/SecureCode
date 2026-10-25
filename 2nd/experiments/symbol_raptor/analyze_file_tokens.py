"""Count whole-file counterfactual inputs using the experiment's exact tokenizer.

No answer generation, grading change, truncation, or fabricated latency baseline.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import shutil
from statistics import mean
import sys
sys.dont_write_bytecode = True
import experiment_r0 as exp
import audit_v2 as audit

DEFAULT_OUT = exp.original.DEFAULT_OUT / "file_tokens_20261024"
FIELDS = ["code_tokens", "answer_input_tokens", "selector_input_tokens", "total_input_tokens",
          "peak_call_input_tokens", "peak_call_input_with_output_reserve"]


def aggregate(group):
    return {"questions": len(group), **{f"mean_{key}": mean(r[key] for r in group) for key in FIELDS},
            "min_code_tokens": min(r["code_tokens"] for r in group),
            "max_code_tokens": max(r["code_tokens"] for r in group),
            "mean_peak_input_window_pct": 100*mean(r["peak_call_input_tokens"] for r in group)/8192}


def run(out):
    assert not (out / "summary.json").exists(), "Use a fresh directory to preserve completed evidence"
    exp.validate_frozen(exp.DEFAULT_OUT)
    exp.ab.validate_frozen(exp.ab.DEFAULT_OUT)
    out.mkdir(parents=True,exist_ok=True)
    history = out / "history"
    history.mkdir(exist_ok=True)
    shutil.copy2(exp.REPORT, history / "report_before_file_tokens.md")
    shutil.copy2(Path(__file__).parent / "report_r0.py", history / "report_generator_before_file_tokens.py")
    for name in ["report_manifest.json", "completion_audit.json"]:
        shutil.copy2(exp.DEFAULT_OUT / name, history / name)
    tasks = exp.read(exp.DEFAULT_OUT / "tasks.json")
    assets = exp.read(exp.DEFAULT_OUT / "assets.json")
    rows = exp.audited.rows(exp.ab.DEFAULT_OUT / "results.jsonl") + exp.audited.rows(exp.DEFAULT_OUT / "results.jsonl")
    assert len(tasks)==96 and len(rows)==864
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["task_id"],r["arm"]].append(r)
    files, baseline, strings = {}, {}, set()
    for task in tasks:
        relative = assets[task["project"]]["nodes"][task["target_uri"]]["path"]
        path = exp.DEFAULT_OUT / "projects" / task["project"] / relative
        content = path.read_text()
        prompt = audit.wrap(audit.answer_prompt(task["question"],content))
        key = f"{task['project']}/{relative}"
        files[key] = {"absolute_path":str(path),"sha256":exp.original.sha(path),"text":content}
        baseline[task["id"]] = {"file":key,"content":content,"answer_prompt":prompt}
        strings.update([content,prompt])
    for r in rows:
        strings.add(r["context"])
        strings.add(r["answer_call"]["request"]["prompt"])
        if r["selector"]:
            strings.add(r["selector"]["request"]["prompt"])
    model_sha = exp.original.sha(exp.original.MODEL)
    assert model_sha == exp.read(exp.DEFAULT_OUT / "environment.json")["fingerprint"]["model_sha256"]
    input_paths = [exp.DEFAULT_OUT/"tasks.json", exp.DEFAULT_OUT/"assets.json", exp.DEFAULT_OUT/"results.jsonl",
                   exp.DEFAULT_OUT/"summary.json", exp.DEFAULT_OUT/"verification.json",
                   exp.ab.DEFAULT_OUT/"results.jsonl", exp.ab.DEFAULT_OUT/"verification.json"]
    protocol = {"created_at_utc":exp.audited.now(),"questions":96,"observed_records":864,
                "baseline":"The entire UTF-8 source file containing the task's target symbol, verbatim, with trailing newline/imports/comments; no added filename/header; no truncation",
                "baseline_prompt":"Same answer instructions, question and chat wrapper as A/B/R0; file is assumed known and no selector is called",
                "scope":"Exact token counts only. Whole-file answers, accuracy, output tokens and latency were not measured.",
                "aggregation":"Each of 96 questions receives equal weight. For actual arms average three repeats per question (counts must be identical). Percent changes are ratios of summed tokens, not averages of question ratios.",
                "window":"8192 per call; input totals across separate calls are not one context window. Reserved output: answer128, selector96",
                "model_sha256":model_sha,"input_hashes":{str(p):exp.original.sha(p) for p in input_paths},
                "source_code_sha256":exp.original.sha(__file__)}
    exp.original.dump(out/"protocol.json",protocol)
    counts, tokenizer = audit.tokenize_many(sorted(strings),exp.original.MODEL)
    prior_tokenizer = exp.read(exp.DEFAULT_OUT/"offline_token_counts.json")["tokenizer"]
    assert tokenizer["binary_sha256"] == prior_tokenizer["binary_sha256"]
    exp.original.dump(out/"token_counts.json",{"counts":counts,"tokenizer":tokenizer,
                      "strings_sha256":exp.audited.digest(sorted(strings))})
    for r in rows:
        assert counts[r["context"]]==r["context_tokens"]
        ac=r["answer_call"]
        assert counts[ac["request"]["prompt"]]==ac["input_tokens"]
        sc=r["selector"]
        if sc:
            assert counts[sc["request"]["prompt"]]==sc["input_tokens"]
        assert r["input_tokens"]==ac["input_tokens"]+(sc["input_tokens"] if sc else 0)
    results=[]
    for task in tasks:
        base=baseline[task["id"]]
        full_input=counts[base["answer_prompt"]]
        full={"code_tokens":counts[base["content"]],"answer_input_tokens":full_input,"selector_input_tokens":0,
              "total_input_tokens":full_input,"peak_call_input_tokens":full_input,
              "peak_call_input_with_output_reserve":full_input+128}
        entry={"task_id":task["id"],"project":task["project"],"category":task["category"],"split":task["split"],
               "baseline_file":base["file"],"whole_file":full,"arms":{}}
        for arm in ["A","B","R0"]:
            group=grouped[task["id"],arm]
            assert len(group)==3 and {r["repeat"] for r in group}=={0,1,2}
            repeat_counts=[]
            for r in group:
                answer=r["answer_call"]["input_tokens"]
                selector=r["selector"]["input_tokens"] if r["selector"] else 0
                repeat_counts.append({"code_tokens":r["context_tokens"],"answer_input_tokens":answer,
                    "selector_input_tokens":selector,"total_input_tokens":answer+selector,
                    "peak_call_input_tokens":max(answer,selector),
                    "peak_call_input_with_output_reserve":max(answer+128,selector+96 if selector else 0)})
            assert repeat_counts[0]==repeat_counts[1]==repeat_counts[2]
            m=repeat_counts[0]
            m["code_change_vs_whole_file_pct"] = 100*(m["code_tokens"]/full["code_tokens"]-1)
            m["total_input_change_vs_whole_file_pct"] = 100*(m["total_input_tokens"]/full["total_input_tokens"]-1)
            entry["arms"][arm]=m
        results.append(entry)
    by_population={}
    for population in ["all96","original48","additional48"]:
        subset=results if population=="all96" else [r for r in results if r["split"]==population]
        f=aggregate([r["whole_file"] for r in subset])
        ms={}
        for arm in ["A","B","R0"]:
            m=aggregate([r["arms"][arm] for r in subset])
            for metric in ["code_tokens","answer_input_tokens","total_input_tokens","peak_call_input_tokens"]:
                m[f"{metric}_ratio_vs_whole_file"]=m[f"mean_{metric}"]/f[f"mean_{metric}"]
                m[f"{metric}_change_vs_whole_file_pct"]=100*(m[f"{metric}_ratio_vs_whole_file"]-1)
                m[f"questions_below_whole_file_{metric}"]=sum(r["arms"][arm][metric]<r["whole_file"][metric] for r in subset)
            ms[arm]=m
        by_population[population]={"whole_file":f,"arms":ms}
    per_file=[]
    for key,file in sorted(files.items()):
        per_file.append({"file":key,"sha256":file["sha256"],"code_tokens":counts[file["text"]],
                         "question_count":sum(r["baseline_file"]==key for r in results)})
    # Independent arithmetic review from raw per-question integer counts.
    checked=0
    for pop,data in by_population.items():
        subset=results if pop=="all96" else [r for r in results if r["split"]==pop]
        for arm in ["whole_file","A","B","R0"]:
            values=[r["whole_file"] if arm=="whole_file" else r["arms"][arm] for r in subset]
            m=data["whole_file"] if arm=="whole_file" else data["arms"][arm]
            for field in FIELDS:
                assert abs(sum(x[field] for x in values)/len(values)-m[f"mean_{field}"])<1e-10
                checked+=1
            if arm!="whole_file":
                for field in ["code_tokens","answer_input_tokens","total_input_tokens","peak_call_input_tokens"]:
                    ratio=sum(x[field] for x in values)/sum(r["whole_file"][field] for r in subset)
                    assert abs(ratio-m[f"{field}_ratio_vs_whole_file"])<1e-10
                    assert abs(100*(ratio-1)-m[f"{field}_change_vs_whole_file_pct"])<1e-10
                    checked+=2
    summary={"status":"PASS","created_at_utc":exp.audited.now(),"unique_questions":96,"observed_records_verified":len(rows),
             "distinct_strings":len(strings),"distinct_baseline_files":len(files),
             "baseline_file_counts":dict(Counter(x["baseline_file"].split('/')[-1] for x in results)),
             "by_population":by_population,"files":per_file,"questions":results,
             "checks":{"original_864_record_token_counts_reproduced":True,"same_model_and_tokenizer":True,
                       "three_repeat_counts_identical":True,"all_whole_file_inputs_fit_context":all(r["whole_file"]["peak_call_input_with_output_reserve"]<=8192 for r in results),
                       "independent_arithmetic_values_checked":checked},
             "protocol_sha256":exp.original.sha(out/"protocol.json"),"token_counts_sha256":exp.original.sha(out/"token_counts.json")}
    exp.original.dump(out/"summary.json",summary)
    print(json.dumps(summary["by_population"]["all96"],ensure_ascii=False,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=DEFAULT_OUT)
    run(p.parse_args().out)
