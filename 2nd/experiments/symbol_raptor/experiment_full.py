"""Actual whole-file reader experiment on the frozen 96 questions, three repeats."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import shutil
import sys
import time
sys.dont_write_bytecode = True
import experiment_r0 as r0

original, audited, ab = r0.original, r0.audited, r0.ab
DEFAULT_OUT = original.DEFAULT_OUT / "full_file_20261024"
CONFIG = {
    "version":"FULL-1.0", "arms":["FULL"], "repeats":3, "evidence_cap":1024,
    "answer_max_tokens":128,"temperature":0,"seed":1,"model_context":8192,"prompt_cache":False,
    "method":"Read the entire provided source file verbatim, including imports/comments/trailing newline; no selector, snippets, summaries, added headers, truncation, or dependency expansion",
    "provided_file":"During preparation, map each question's target symbol to its defining file. The inference reader is given this file path; file discovery is excluded and no gold answer is supplied to the reader.",
    "schedule":"Same 96 question-repeat blocks as the preserved A/B and R0 experiments",
    "timing":"Start before reading the provided local file; include file read, token count, answer HTTP and small call-log write; exclude model startup, prepared file map, grading and result-row write",
    "primary_quality":"Exact JSON value, type and requested list order",
    "primary_latency":"Across-question mean of within-question median of three query times",
    "comparison":"A/B same earlier session, R0 another earlier session, FULL new session. Same binary/model/settings fingerprint; latency differences are descriptive and session-confounded.",
    "inference":"Exploratory paired six-project cluster bootstrap; three new quality contrasts FULL-A, FULL-B, FULL-R0 with Holm-adjusted project sign-flip tests",
    "no_tuning":"No outcome-based retrieval, prompt, model, question or budget changes",
}


def read(path):
    return json.loads(Path(path).read_text())


def prepare(out):
    assert not (out/"protocol.json").exists(), "Choose a fresh output directory"
    r0.validate_frozen(r0.DEFAULT_OUT)
    ab.validate_frozen(ab.DEFAULT_OUT)
    out.mkdir(parents=True,exist_ok=True)
    inputs={}
    for name in ["tasks.json","dev_tasks.json","gold_operations.json"]:
        path=ab.DEFAULT_OUT/name
        shutil.copy2(path,out/name)
        inputs[str(path)]=original.sha(path)
    for directory in [ab.DEFAULT_OUT,r0.DEFAULT_OUT]:
        for name in ["results.jsonl","summary.json","verification.json","environment.json","protocol.json"]:
            inputs[str(directory/name)]=original.sha(directory/name)
    token_reference=original.DEFAULT_OUT/"file_tokens_20261024/summary.json"
    inputs[str(token_reference)]=original.sha(token_reference)
    shutil.copytree(ab.DEFAULT_OUT/"projects",out/"projects",dirs_exist_ok=True)
    tasks,dev=read(out/"tasks.json"),read(out/"dev_tasks.json")
    assets=read(r0.DEFAULT_OUT/"assets.json")
    nodes={p:asset["nodes"] for p,asset in assets.items()}
    file_map={t["id"]:nodes[t["project"]][t["target_uri"]]["path"] for t in tasks+dev}
    for p in sorted((out/"projects").rglob("*.py")):
        source=ab.DEFAULT_OUT/"projects"/p.relative_to(out/"projects")
        inputs[str(source)]=original.sha(source)
        assert original.sha(p)==original.sha(source)
    original.dump(out/"nodes.json",nodes)
    original.dump(out/"file_map.json",file_map)
    original.dump(out/"gold_recheck.json",ab.verify_gold(out,tasks,read(out/"gold_operations.json")))
    original.dump(out/"schedule.json",[{**e,"arm":"FULL"} for e in read(r0.DEFAULT_OUT/"schedule.json")])
    history=out/"history";history.mkdir(exist_ok=True)
    shutil.copy2(r0.REPORT,history/"report_before_full_file_run.md")
    for name in ["report_manifest.json","completion_audit.json"]:
        shutil.copy2(token_reference.parent/name,history/name)
    code=list(dict.fromkeys([Path(__file__),Path(r0.__file__),*ab.inputs()]))
    snapshot=out/"source_snapshot";snapshot.mkdir(exist_ok=True)
    for p in code:
        shutil.copy2(p,snapshot/p.name)
    original.dump(out/"protocol.json",{**CONFIG,"frozen_at_utc":audited.now(),
        "input_hashes":inputs,"code_hashes":{str(p):original.sha(p) for p in code},
        "frozen_files":{str(p.relative_to(out)):original.sha(p) for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({"status":"PREPARED","questions":96,"planned_answers":288,"gold_rechecked":96}),flush=True)


def validate_frozen(out):
    protocol=read(out/"protocol.json")
    assert all(protocol[k]==v for k,v in CONFIG.items())
    for category,root in [("input_hashes",None),("code_hashes",None),("frozen_files",out)]:
        for p,digest in protocol[category].items():
            assert original.sha(root/p if root else p)==digest,p


def run(out,url,dev=False):
    validate_frozen(out)
    client=audited.AuditedClient(out,url)
    environment=audited.runtime_environment(client)
    assert environment['fingerprint']==read(ab.DEFAULT_OUT/'environment.json')['fingerprint']
    if (out/'environment.json').exists():
        assert environment['fingerprint']==read(out/'environment.json')['fingerprint']
    else:
        original.dump(out/'environment.json',environment)
    tasks=read(out/('dev_tasks.json' if dev else 'tasks.json'))
    task_map={t['id']:t for t in tasks}
    file_map,nodes=read(out/'file_map.json'),read(out/'nodes.json')
    plan=([{'task_id':t['id'],'arm':'FULL','repeat':0} for t in tasks] if dev else read(out/'schedule.json'))
    result_path=out/('results_dev.jsonl' if dev else 'results.jsonl')
    prior=audited.rows(result_path)
    assert [{k:r[k] for k in ['task_id','arm','repeat']} for r in prior]==plan[:len(prior)]
    session_id=audited.digest([audited.now(),dev])[:20]
    original.dump(out/f'session_{session_id}.json',{'started_at_utc':audited.now(),'dev':dev,'resume_after_rows':len(prior),'environment':environment})
    client.reset_query()
    assert client.complete('Return only {"answer":0}.','warmup',32,{'session_id':session_id})['ok']
    for i,entry in enumerate(plan):
        if i<len(prior):continue
        task=task_map[entry['task_id']]
        provided_file=file_map[task['id']]
        client.reset_query()
        started,utc=time.perf_counter(),audited.now()
        context=(out/'projects'/task['project']/provided_file).read_text()
        retrieval_seconds=time.perf_counter()-started
        packing=time.perf_counter()
        tokens=client.tokens(context)
        assert tokens<=CONFIG['evidence_cap'], 'Do not truncate a full file; protocol must be revised before measurement'
        packing_seconds=time.perf_counter()-packing
        pre_answer_seconds=time.perf_counter()-started
        call=client.complete(original.answer_prompt(task['question'],context),'answer',128,{**entry,'dev':dev,'session_id':session_id})
        seconds,ended=time.perf_counter()-started,audited.now()
        correct,parsed,failure=original.evaluate_answer(call,task['expected'])
        # Coverage diagnostics occur after timing and never enter the model input.
        sources=sorted(u for u,n in nodes[task['project']].items() if n['path']==provided_file)
        required=set(task['required_uris'])
        row={**entry,'session_id':session_id,'split':task.get('split','development'),
             'project':task['project'],'category':task['category'],'question':task['question'],
             'expected':task['expected'],'correct':correct,'parsed_answer':parsed,'failure':failure,
             'provided_file':provided_file,'selector':None,'selected_uri':None,'selection_valid':None,'selection_correct':None,
             'answer_call':call,'context':context,'context_tokens':tokens,'selected_context_tokens':tokens,
             'chosen':[{'id':f'file://{provided_file}','level':0,'score':None,'source_uris':sources}], 'rejected':[],
             'query_seconds':seconds,'retrieval_seconds':retrieval_seconds,'select_seconds':0,'expansion_seconds':0,
             'packing_seconds':packing_seconds,'pre_answer_seconds':pre_answer_seconds,
             'started_at_utc':utc,'ended_at_utc':ended,'tokenize_http_calls':client.token_http_count,'tokenize_seconds':client.token_seconds,
             'input_tokens':call['input_tokens'],'output_tokens':call['output_tokens'] or 0,
             'raw_evidence_recall':len(required&set(sources))/len(required),'all_raw_evidence':required<=set(sources),
             'unique_source_count':len(sources),'cross_file_source_count':0,'source_files':[provided_file],'compaction_seconds':0}
        with result_path.open('a') as handle:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(f"{'dev' if dev else 'eval'} {i+1}/{len(plan)} {entry['task_id']} FULL r{entry['repeat']} correct={int(correct)} tokens={tokens} seconds={seconds:.3f}",flush=True)
    original.dump(out/f"completed_{'dev' if dev else 'eval'}.json",{'completed_at_utc':audited.now(),'rows':len(plan),'results_sha256':original.sha(result_path),'session_id':session_id})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','dev','run'])
    p.add_argument('--out',type=Path,default=DEFAULT_OUT);p.add_argument('--url',default='http://127.0.0.1:8766')
    args=p.parse_args()
    if args.phase=='prepare':prepare(args.out)
    else:run(args.out,args.url,args.phase=='dev')
