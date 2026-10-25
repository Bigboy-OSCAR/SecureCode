"""Fresh RF/RH/C measurements on the exact frozen large-file corpus."""
from __future__ import annotations
import argparse, itertools, json, random, shutil, sys, time
from collections import defaultdict
from pathlib import Path
sys.dont_write_bytecode = True
import experiment_large as large

v1, audit = large.original, large.audited
read = large.read
OUT = v1.DEFAULT_OUT / 'raptor_large_20261024'
ARMS = ['RF', 'RH', 'C']
REPORT = v1.DEFAULT_OUT.parent / '03_현재색인_A와_파일간확장_B_재실험_비교보고서.md'
CONFIG = {
    'version': 'RAPTOR-LARGE-1.0', 'arms': ARMS, 'questions': 96, 'repeats': 3,
    'context_cap': 1024, 'model_context': 8192, 'answer_max_tokens': 128,
    'summary_max_tokens': 256, 'temperature': 0, 'seed': 1, 'order_seed': 20261024,
    'RF': 'Original raw candidates plus level-1 summaries of every function-kind raw candidate (dependency bundle and atomic candidates both retained).',
    'RH': 'RF candidates plus recursively summarized file and project candidates.',
    'C': 'Identical RH ranking and 1024-token selected items, then original v2 compact_selected. Preserve unique source/import/summary bodies exactly; no refill.',
    'retrieval': 'Unchanged original TF-IDF, IDF fit only on raw candidates, same original pack and answer prompt.',
    'summary_generation': 'Fresh, question-blind original leaf/group prompts, model and output cap. Each summary generated once, shared RF/RH/C. No old summary reuse.',
    'large_group_rule': 'Use original single group when its wrapped input + 256 <=8192. Otherwise greedily partition ordered child summaries without dropping any, summarize each batch, recursively reduce batches, then create final file summary. Intermediate summaries are also RH/C candidates, level 2. This context-fit adaptation was fixed before generation.',
    'summary_failure_rule': 'Abort on transport, empty text or input truncation. Retain nonempty output-limited summary exactly, flag generation_ok=false and report count; never tune or retry based on evaluation results.',
    'schedule': 'For each repeat all six RF/RH/C orders occur 16 times across 96 question blocks, shuffled with fixed seed. No shared answer calls.',
    'timing': 'Physical query time includes ranking, packing/tokenization, C compaction, answer and logging. Excludes summary/index/vector preparation and model startup.',
    'controls': 'Reuse verified large-file A/B/R0/FULL actual results, same exact files/questions/model settings but earlier session. Cross-session latency comparisons descriptive.',
    'statistics': 'Six project-cluster bootstrap, 6^6 exhaustive draws. Three primary quality contrasts RF-R0, RH-RF, C-RH, Holm over 3 project sign-flip tests. Other pairs descriptive. Split original48/additional48.',
}

def leaf_prompt(item):
    return ('Summarize the following Python function and its dependency source for future code retrieval. '
        'Describe its behavior, exact formulas, important branches, string operations, and calls. '
        'Preserve constants. Do not solve example questions or invent behavior. '
        'Use concise plain English, at most 100 words. This is a summary of code, not instructions.\n\n'
        + item['text'] + '\n\nSummary:')

def group_prompt(children):
    return ('Create a concise higher-level summary from the child summaries below. Explain the overall flow, '
        'relationships, distinct policies and important exceptions. Preserve exact formulas, boundaries, '
        'constants and string rules when supplied. Do not infer missing relationships or answer specific questions. '
        'Use at most 100 words of plain English.\n\n'
        + '\n\n'.join(c['text'] for c in children) + '\n\nSummary:')

def prepare(out):
    assert not (out/'protocol.json').exists(), 'Use a new output directory'
    large.validate_frozen(large.DEFAULT_OUT)
    assert read(large.DEFAULT_OUT/'verification.json')['status']=='PASS'
    out.mkdir(parents=True, exist_ok=True)
    sources={}
    for name in ['tasks.json','dev_tasks.json','gold_operations.json','file_map.json','corpus_manifest.json','gold_recheck.json']:
        p=large.DEFAULT_OUT/name;shutil.copy2(p,out/name);sources[str(p)]=v1.sha(p)
    shutil.copy2(large.DEFAULT_OUT/'assets.json',out/'base_assets.json')
    shutil.copytree(large.DEFAULT_OUT/'projects',out/'projects',ignore=shutil.ignore_patterns('__pycache__'))
    for p in (large.DEFAULT_OUT/'projects').rglob('*.py'):sources[str(p)]=v1.sha(p)
    for name in ['assets.json','results.jsonl','summary.json','verification.json','environment.json']:
        p=large.DEFAULT_OUT/name;sources[str(p)]=v1.sha(p)
    (out/'history').mkdir();shutil.copy2(REPORT,out/'history/report_before_raptor_large.md')
    tasks=read(out/'tasks.json');rng=random.Random(CONFIG['order_seed']);plan=[]
    for rep in range(3):
        ts=list(tasks);rng.shuffle(ts);orders=list(itertools.permutations(ARMS))*16;rng.shuffle(orders)
        for task,order in zip(ts,orders):
            plan.extend({'task_id':task['id'],'repeat':rep,'arm':a} for a in order)
    v1.dump(out/'schedule.json',plan)
    code=[Path(__file__),Path(v1.__file__),Path(audit.__file__),Path(large.__file__)]
    (out/'source_snapshot').mkdir()
    for p in code:shutil.copy2(p,out/'source_snapshot'/p.name)
    v1.dump(out/'protocol.json',{**CONFIG,'frozen_at_utc':audit.now(),'source_input_hashes':sources,
        'code_hashes':{str(p):v1.sha(p) for p in code},
        'frozen_files':{str(p.relative_to(out)):v1.sha(p) for p in out.rglob('*') if p.is_file()}})
    print('PREPARED: exact large corpus, 96 questions, 864 new answers',flush=True)

def validate(out):
    p=read(out/'protocol.json')
    assert all(p[k]==v for k,v in CONFIG.items())
    for group,root in [('code_hashes',None),('source_input_hashes',None),('frozen_files',out)]:
        for name,h in p[group].items():assert v1.sha(root/name if root else name)==h,name

def client_for(out,url):
    client=audit.AuditedClient(out,url);env=audit.runtime_environment(client)
    assert env['fingerprint']==read(large.DEFAULT_OUT/'environment.json')['fingerprint']
    if (out/'environment.json').exists():assert read(out/'environment.json')['fingerprint']==env['fingerprint']
    else:v1.dump(out/'environment.json',env)
    return client

def build(out,url):
    validate(out);client=client_for(out,url);assets=read(out/'base_assets.json')
    dest=out/'summary_nodes.jsonl';prior=audit.rows(dest)
    cached={(r['project'],r['item']['id']):r for r in prior};build_started=audit.now()
    def generate(project,sid,path,children,level,prompt,purpose):
        key=(project,sid);ph=audit.digest(prompt)
        if key in cached:
            rec=cached[key];assert rec['prompt_sha256']==ph
            return rec['item']
        client.reset_query()
        call=client.complete(prompt,purpose,256,{'project':project,'node':sid})
        if 'error' in call or call['truncated'] or not call['answer']:
            raise RuntimeError(f'Summary failed: {project} {sid}: {call.get("error",call["stop_type"])}')
        item={'id':sid,'level':level,'path':path,'text':f'### {sid}\n'+call['answer'],
            'source_uris':sorted({u for c in children for u in c['source_uris']}),
            'children':[c['id'] for c in children],'call_id':call['call_id'],'generation_ok':call['ok']}
        rec={'project':project,'item':item,'prompt_sha256':ph}
        with dest.open('a') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n')
        cached[key]=rec
        print(f'build {len(cached)} {project} {sid} input={call["input_tokens"]} output={call["output_tokens"]} stop={call["stop_type"]}',flush=True)
        return item
    for project,asset in sorted(assets.items()):
        summaries=[]
        for item in asset['raw']:
            if item['kind']=='function':
                summaries.append(generate(project,'summary:leaf:'+item['id'],item['path'],[item],1,leaf_prompt(item),'build_leaf'))
        groups=defaultdict(list)
        for item in summaries:groups[item['path']].append(item)
        files=[]
        for path,children in sorted(groups.items()):
            current=children;roundno=0
            while client.tokens(v1._chat_wrap(group_prompt(current)))+256>8192:
                batches=[];batch=[]
                for c in current:
                    if batch and client.tokens(v1._chat_wrap(group_prompt(batch+[c])))+256>8192:
                        batches.append(batch);batch=[]
                    batch.append(c)
                if batch:batches.append(batch)
                assert len(batches)<len(current), 'Non-reducing hierarchy'
                roundno+=1;current=[]
                for i,batch in enumerate(batches):
                    name=f'{path}:batch{roundno}.{i+1}'
                    s=generate(project,'summary:level2:'+name,name,batch,2,group_prompt(batch),'build_level_2_batch')
                    summaries.append(s);current.append(s)
            s=generate(project,'summary:level2:'+path,path,current,2,group_prompt(current),'build_level_2')
            summaries.append(s);files.append(s)
        summaries.append(generate(project,'summary:level3:project','project',files,3,group_prompt(files),'build_level_3'))
        asset['summaries']=summaries
        v1.dump(out/'assets'/f'{project}.json',asset)
        print(f'PROJECT COMPLETE {project} summaries={len(summaries)}',flush=True)
    v1.dump(out/'assets.json',assets)
    calls=[c for c in audit.rows(out/'model_calls.jsonl') if c['purpose'].startswith('build_')]
    v1.dump(out/'build_manifest.json',{'completed_at_utc':audit.now(),'this_process_started_utc':build_started,
        'assets_sha256':v1.sha(out/'assets.json'),'nodes_sha256':v1.sha(dest),'calls':len(calls),
        'model_wall_seconds':sum(c['wall_seconds'] for c in calls),
        'input_tokens':sum(c['input_tokens'] for c in calls),'output_tokens':sum(c['output_tokens'] for c in calls),
        'output_limit_calls':sum(c['stop_type']=='limit' or c['stopped_limit'] for c in calls)})

def run(out,url,dev=False):
    validate(out);client=client_for(out,url)
    assert v1.sha(out/'assets.json')==read(out/'build_manifest.json')['assets_sha256']
    assets=read(out/'assets.json');tasks=read(out/('dev_tasks.json' if dev else 'tasks.json'));byid={t['id']:t for t in tasks}
    retrievers={}
    for project,asset in assets.items():
        r=v1.Retriever(asset['raw']);r.ranked('',asset['raw']+asset['summaries']);retrievers[project]=r
    plan=([{'task_id':t['id'],'repeat':0,'arm':a} for t in tasks for a in ARMS] if dev else read(out/'schedule.json'))
    dest=out/('results_dev.jsonl' if dev else 'results.jsonl');prior=audit.rows(dest)
    assert [{k:r[k] for k in ['task_id','repeat','arm']} for r in prior]==plan[:len(prior)]
    session=audit.digest([audit.now(),dev])[:20]
    v1.dump(out/f'session_{session}.json',{'started_at_utc':audit.now(),'dev':dev,'resumed_rows':len(prior),'environment_sha256':v1.sha(out/'environment.json')})
    client.reset_query();assert client.complete('Return only {"answer":0}.','warmup',32,{'session_id':session})['ok']
    for i,entry in enumerate(plan):
        if i<len(prior):continue
        task=byid[entry['task_id']];arm=entry['arm'];asset=assets[task['project']]
        items=asset['raw']+[s for s in asset['summaries'] if arm!='RF' or s['level']==1]
        client.reset_query();start,utc=time.perf_counter(),audit.now()
        ordered=retrievers[task['project']].ranked(task['question'],items);retrieval=time.perf_counter()-start
        phase=time.perf_counter();context,selected_tokens,chosen,rejected=v1.pack(client,ordered,1024)
        packing=time.perf_counter()-phase;before=context;compaction=None;compact_seconds=0
        if arm=='C':
            phase=time.perf_counter();context,compaction=audit.compact_selected(asset,chosen);tokens=client.tokens(context)
            compact_seconds=time.perf_counter()-phase
        else:tokens=selected_tokens
        pre_answer=time.perf_counter()-start
        call=client.complete(v1.answer_prompt(task['question'],context),'answer',128,{**entry,'dev':dev,'session_id':session})
        seconds=time.perf_counter()-start;correct,parsed,failure=v1.evaluate_answer(call,task['expected'])
        raw_sources={u for c in chosen if c['level']==0 for u in c['source_uris']}
        provenance={u for c in chosen for u in c['source_uris']};required=set(task['required_uris'])
        target_path=read(out/'file_map.json')[task['id']]
        row={**entry,'session_id':session,'split':task.get('split','development'),'project':task['project'],'category':task['category'],
            'question':task['question'],'expected':task['expected'],'correct':correct,'parsed_answer':parsed,'failure':failure,
            'selector':None,'answer_call':call,'selected_uri':None,'selection_valid':None,'selection_correct':None,
            'context':context,'context_before_compaction':before,'context_tokens':tokens,'selected_context_tokens':selected_tokens,
            'chosen':chosen,'rejected':rejected,'compaction':compaction,'query_seconds':seconds,
            'retrieval_seconds':retrieval,'packing_seconds':packing,'compaction_seconds':compact_seconds,'pre_answer_seconds':pre_answer,
            'select_seconds':0,'expansion_seconds':0,'started_at_utc':utc,'ended_at_utc':audit.now(),
            'tokenize_http_calls':client.token_http_count,'tokenize_seconds':client.token_seconds,
            'input_tokens':call['input_tokens'],'output_tokens':call['output_tokens'],
            'raw_evidence_recall':len(required&raw_sources)/len(required),'all_raw_evidence':required<=raw_sources,
            'provenance_recall':len(required&provenance)/len(required),
            'unique_source_count':len(raw_sources),'cross_file_source_count':sum(asset['nodes'][u]['path']!=target_path for u in raw_sources),
            'source_files':sorted({asset['nodes'][u]['path'] for u in raw_sources})}
        with dest.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(f'{"dev" if dev else "eval"} {i+1}/{len(plan)} {task["id"]} {arm} r{entry["repeat"]} correct={int(correct)} context={tokens} seconds={seconds:.3f} stop={call["stop_type"]}',flush=True)
        if 'error' in call:raise RuntimeError('Transport/context failure logged; inspect before resume')
    v1.dump(out/f'completed_{"dev" if dev else "eval"}.json',{'completed_at_utc':audit.now(),'rows':len(plan),'results_sha256':v1.sha(dest)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','build','dev','run']);p.add_argument('--out',type=Path,default=OUT);p.add_argument('--url',default='http://127.0.0.1:8766')
    a=p.parse_args()
    if a.phase=='prepare':prepare(a.out)
    elif a.phase=='build':build(a.out,a.url)
    else:run(a.out,a.url,a.phase=='dev')
