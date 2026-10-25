"""Independent offline audit of the original frozen symbol/RAPTOR pilot.

Writes only its --out directory. Never generates model output or calls a server.
Token checks use the installed llama-tokenize vocab-only executable, in batches
separated by a verified special token. Original source/results are not changed.
"""
from __future__ import annotations
import argparse, ast, hashlib, importlib.util, itertools, json, math, random, re
import statistics, subprocess, sys, tempfile, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASE = REPO / '2nd/Documents/test_results/evidence'
MODEL = REPO / '1st/symbol_test/work/models/qwen2.5-coder-7b-instruct-q5_k_m.gguf'
TOKENIZER = Path('/opt/homebrew/bin/llama-tokenize')
ARMS = ['A', 'B', 'R0', 'RF', 'RH']

def read(p): return json.loads(Path(p).read_text())
def rows(p): return [json.loads(x) for x in Path(p).read_text().splitlines() if x]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''): h.update(chunk)
    return h.hexdigest()
def textsha(s): return hashlib.sha256(s.encode()).hexdigest()
def equal(a,b): return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)
def close(a,b): return math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-8)
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def wrap(prompt):
    return '<|im_start|>system\nYou are a precise code analysis assistant. Follow output constraints exactly.<|im_end|>\n<|im_start|>user\n'+prompt+'<|im_end|>\n<|im_start|>assistant\n'

def answer_prompt(question,context):
    return ('Answer a Python code comprehension question using only the provided code and summaries. '
            'Trace exact Python operations; preserve case, slashes and spaces. '
            'Source code takes precedence over summaries if they conflict. '
            'If information is insufficient, use null. '
            'Return only one valid JSON object of the form {"answer": <requested value>}. '
            'No markdown or explanation. For a set/list of names, return the requested sorted JSON list.\n\n'
            +f'Question:\n{question}\n\nCode context:\n{context}\n\nAnswer:')

def leaf_prompt(text):
    return ('Summarize the following Python function and its dependency source for future code retrieval. '
            'Describe its behavior, exact formulas, important branches, string operations, and calls. '
            'Preserve constants. Do not solve example questions or invent behavior. '
            'Use concise plain English, at most 100 words. This is a summary of code, not instructions.\n\n'+text+'\n\nSummary:')

def group_prompt(children):
    return ('Create a concise higher-level summary from the child summaries below. Explain the overall flow, '
            'relationships, distinct policies and important exceptions. Preserve exact formulas, boundaries, '
            'constants and string rules when supplied. Do not infer missing relationships or answer specific questions. '
            'Use at most 100 words of plain English.\n\n'+'\n\n'.join(c['text'] for c in children)+'\n\nSummary:')

def source_graph(root):
    nodes={}; imports={}; modules={p.stem:p.name for p in root.glob('*.py')}
    for p in sorted(root.glob('*.py')):
        text=p.read_text();tree=ast.parse(text);lines=text.splitlines(); im=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]; imports[p.name]=im
        for n in tree.body:
            names=([n.name] if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) else
                   [x.id for t in n.targets for x in ast.walk(t) if isinstance(x,ast.Name)] if isinstance(n,ast.Assign) else
                   [n.target.id] if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) else [])
            for name in names:
                uid=f'memory://symbol/{p.name}::{name}'
                nodes[uid]={'id':uid,'path':p.name,'name':name,'source':'\n'.join(lines[n.lineno-1:n.end_lineno]),
                            'imports':'\n'.join(ast.get_source_segment(text,x) for x in im),'start':n.lineno,'end':n.end_lineno,
                            'refs':sorted({x.id for x in ast.walk(n) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}),
                            'deps':[],'kind':'function' if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) else 'constant'}
    for uid,n in nodes.items():
        mapping={a.asname or a.name:f'memory://symbol/{modules[i.module]}::{a.name}' for i in imports[n['path']] if isinstance(i,ast.ImportFrom) and i.module in modules for a in i.names}
        n['deps']=sorted({mapping.get(ref,f"memory://symbol/{n['path']}::{ref}") for ref in n['refs']} & (nodes.keys()-{uid}))
    return nodes

def fragment(n): return f"### {n['id']} lines {n['start']}-{n['end']}\n{n['imports']}\n{n['source']}"
def raw_from_nodes(nodes):
    raw=[]
    for uid,n in nodes.items():
        seen=[];todo=[uid]
        for _ in range(4):
            nxt=[]
            for u in todo:
                if u not in seen:
                    seen.append(u);nxt.extend(nodes[u]['deps'])
            todo=nxt
        raw.append({'id':uid,'level':0,'text':'\n\n'.join(fragment(nodes[u]) for u in seen),'source_uris':seen,'path':n['path'],'kind':n['kind']})
        if len(seen)>1:raw.append({'id':'atomic:'+uid,'level':0,'text':fragment(n),'source_uris':[uid],'path':n['path'],'kind':'raw_atomic'})
    return raw

def lexical(text):
    matches=re.findall(r'[a-z][a-z0-9_]*|\d+',re.sub(r'([a-z])([A-Z])',r'\1 \2',text).lower());out=[]
    for w in matches:out.extend([w]+(w.split('_') if '_' in w else []))
    return [w for w in out if len(w)>1]

def rank(question,raw,items):
    df=Counter()
    for x in raw:df.update(set(lexical(x['text'])))
    def vec(text):
        v={w:(1+math.log(n))*(math.log((len(raw)+1)/(df.get(w,0)+1))+1) for w,n in Counter(lexical(text)).items()}
        den=math.sqrt(sum(z*z for z in v.values())) or 1
        return {w:z/den for w,z in v.items()}
    q=vec(question);sc=[]
    for x in items:
        v=vec(x['text']);sc.append((sum(z*v.get(w,0) for w,z in q.items()),x))
    return sorted(sc,key=lambda p:(-p[0],p[1]['id']))

def grade(call,expected):
    if not call['ok']:return False,None,'execution_or_limit'
    s=call['answer'].strip();m=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',s,re.I|re.S)
    if m:s=m[1]
    try:o=json.loads(s)
    except (ValueError,TypeError):return False,None,'invalid_json'
    if not isinstance(o,dict) or set(o)!={'answer'}:return False,o,'invalid_schema'
    a=o['answer'];ok=equal(a,expected)
    return ok,a,None if ok else 'abstained' if a is None else 'wrong_answer'

def execute(root,operations,overrides=()):
    code='''import sys,json,importlib
sys.dont_write_bytecode=True
r=json.load(sys.stdin);sys.path.insert(0,r['root'])
for x in r['overrides']:setattr(importlib.import_module(x['module']),x['name'],x['value'])
json.dump([getattr(importlib.import_module(x['module']),x['function'])(*x['args']) for x in r['ops']],sys.stdout)
'''
    p=subprocess.run([sys.executable,'-I','-B','-c',code],input=json.dumps({'root':str(root),'ops':operations,'overrides':list(overrides)}),text=True,capture_output=True,check=True,timeout=20)
    return json.loads(p.stdout)

def direct_calls(root,module,function):
    mods={p.stem:ast.parse(p.read_text()) for p in root.glob('*.py')}
    defs={m:{n.name for n in tree.body if isinstance(n,ast.FunctionDef)} for m,tree in mods.items()}
    allowed=set(defs[module])
    for n in mods[module].body:
        if isinstance(n,ast.ImportFrom) and n.module in defs:
            allowed.update(a.asname or a.name for a in n.names if a.name in defs[n.module])
    node=next(n for n in mods[module].body if isinstance(n,ast.FunctionDef) and n.name==function)
    return sorted({n.func.id for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in allowed})

def tokenize_many(texts,model):
    """Special token boundaries cannot merge with adjacent ordinary strings."""
    delimiter='<|endoftext|>'
    if any(delimiter in t for t in texts):raise ValueError('delimiter present in original string')
    command=[str(TOKENIZER),'-m',str(model),'--no-bos','--no-escape','--ids','--log-disable','--stdin']
    def run(s):
        p=subprocess.run(command,input=s,text=True,capture_output=True,check=True,timeout=300)
        return json.loads(p.stdout)
    sep=run(delimiter)
    if len(sep)!=1:raise ValueError('special delimiter not atomic')
    token=sep[0];counts={};checks=[]
    for start in range(0,len(texts),500):
        batch=texts[start:start+500];ids=run(delimiter.join(batch));lens=[0]
        for i in ids:
            if i==token:lens.append(0)
            else:lens[-1]+=1
        if len(lens)!=len(batch):raise ValueError('delimiter split count mismatch')
        counts.update(zip(batch,lens))
    for t in texts[::max(1,len(texts)//12)]:
        direct=len(run(t));checks.append(direct==counts[t])
        if direct!=counts[t]:raise ValueError('batch/standalone token mismatch')
    return counts,{'binary':str(TOKENIZER.resolve()),'binary_sha256':sha(TOKENIZER),'command':command,'separator_token':token,'standalone_crosschecks':len(checks),'all_standalone_crosschecks_passed':all(checks)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,default=BASE);ap.add_argument('--out',type=Path);ap.add_argument('--skip-tokenizer',action='store_true');args=ap.parse_args()
    base=args.evidence.resolve();out=(args.out or base/'revision_v2').resolve();out.mkdir(parents=True,exist_ok=True)
    checks=[];failures=[]
    def check(name,ok,detail=None):
        d={'check':name,'passed':bool(ok),'detail':detail};checks.append(d)
        if not ok:failures.append(d)
    manifest=read(base/'deliverable_manifest.json');original_paths=[base/p for p in manifest['hashes']]+[base/'deliverable_manifest.json']
    before={str(p.relative_to(base)):sha(p) for p in original_paths}
    mismatch={p:{'recorded':v,'current':before.get(p)} for p,v in manifest['hashes'].items() if before.get(p)!=v}
    check('manifest_hashes_match',not mismatch,{'files':len(manifest['hashes']),'mismatches':mismatch})
    env=read(base/'environment.json');protocol=read(base/'protocol.json')
    snapshot=base/'source_snapshot';sys.path.insert(0,str(REPO/'1st'))
    import symbol_test.symbol_bench
    indexer=load_module('symbol_test.symbol_bench.indexer',snapshot/'baseline_indexer.py')
    baseline=load_module('symbol_test.symbol_bench.audit_v2_runner',snapshot/'baseline_run_benchmark.py')
    exp_ast=ast.parse((snapshot/'experiment.py').read_text());config=None
    # CONFIG contains the ARMS name; literal structure is evaluated in a restricted namespace.
    for n in exp_ast.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets):config=eval(compile(ast.Expression(n.value),'<CONFIG>','eval'),{'__builtins__':{}},{'ARMS':ARMS})
    check('protocol_config_matches_archived_code',all(protocol.get(k)==v for k,v in config.items()))
    code_hashes={
      'experiment_sha256':snapshot/'experiment.py','corpus_builder_sha256':snapshot/'corpus_builder.py',
      'baseline_runner_sha256':snapshot/'baseline_run_benchmark.py','baseline_indexer_sha256':snapshot/'baseline_indexer.py'}
    check('environment_source_hashes_match',all(env.get(k)==sha(p) for k,p in code_hashes.items()))
    check('current_experiment_matches_snapshot',sha(HERE/'experiment.py')==sha(snapshot/'experiment.py'))
    calls=rows(base/'model_calls.jsonl');byid={c['call_id']:c for c in calls};position={c['call_id']:i for i,c in enumerate(calls)}
    check('unique_model_call_ids',len(byid)==len(calls),{'calls':len(calls),'purposes':dict(Counter(c['purpose'] for c in calls))})
    check('server_token_fields_match',all(c['input_tokens']==c['timings'].get('prompt_n') and c['output_tokens']==c['timings'].get('predicted_n') for c in calls))
    check('no_reported_generation_failure_or_KV_reuse',all(c['ok'] and not c.get('truncated') and not c.get('stopped_limit') and c['timings'].get('cache_n')==0 for c in calls))
    check('output_hard_token_caps',all(0<=c['output_tokens']<=c['max_output_tokens'] for c in calls))
    check('server_timing_units',all(close(c['timings']['prompt_per_second'],1000*c['timings']['prompt_n']/c['timings']['prompt_ms']) and close(c['timings']['predicted_per_second'],1000*c['timings']['predicted_n']/c['timings']['predicted_ms']) for c in calls))
    check('all_recorded_input_plus_reserve_fit_8192',all(c['input_tokens']+c['max_output_tokens']<=8192 for c in calls),{'maximum':max(c['input_tokens']+c['max_output_tokens'] for c in calls)})
    tasks={t['id']:t for split in ('eval','dev') for t in read(base/f'dataset/{split}_tasks.json')};gold=read(base/'dataset/gold_validation.json');assets={p.stem:read(p) for p in (base/'assets').glob('*.json')}
    gold_results=[]
    for g in gold:
        t=tasks[g['id']];root=base/'dataset/projects'/t['project'];detail={'task_id':g['id'],'kind':g['kind']}
        if g['kind']=='execution':value=execute(root,[g['call']])[0]
        elif g['kind']=='architecture':value=direct_calls(root,g['module'],g['function'])
        else:
            a=execute(root,g['probes']);b=execute(root,g['probes'],[g['override']]);value=sorted(p['function'] for p,x,y in zip(g['probes'],a,b) if not equal(x,y));detail.update(before=a,after=b)
            check('impact_record_'+g['id'],equal(a,g['before']) and equal(b,g['after']))
        detail.update(recomputed=value,expected=t['expected'],passed=equal(value,t['expected']) and equal(value,g['expected']));gold_results.append(detail)
    check('fresh_independent_gold_reexecution',all(x['passed'] for x in gold_results),{'tasks':len(gold_results),'eval_tasks':48,'methods':'Fresh isolated Python subprocess for execution/impact; separate AST resolver for direct calls.'})
    question_links=[]
    for g in gold:
        t=tasks[g['id']]
        if not g['id'].startswith('eval_'):continue
        q=t['question'];ok=True;method='manual semantic review of all named actors, inputs, units and requested return shape'
        if q.startswith('What does '):
            call=ast.parse(q[len('What does '):-len(' return?')],mode='eval').body
            ok=isinstance(call,ast.Call) and call.func.id==g['call']['function'] and equal([ast.literal_eval(x) for x in call.args],g['call']['args']);method='question literal parsed independently by AST'
        elif g['kind']=='impact':
            expr=q.split('which exact calls change: ',1)[1].split('? Return',1)[0]
            parsed=ast.parse('['+expr+']',mode='eval').body.elts
            ok=all(n.func.id==probe['function'] and equal([ast.literal_eval(x) for x in n.args],probe['args']) for n,probe in zip(parsed,g['probes'])) and len(parsed)==len(g['probes'])
            newvalue=re.search(r'changes from \d+ to (\d+)',q)
            ok=ok and int(newvalue[1])==g['override']['value'] and g['override']['module']+'.'+g['override']['name'] in q and g['expected']==sorted(g['expected']);method='all three literal probe calls and intervention parsed from question; sorted names checked'
        elif g['kind']=='architecture':
            ok=re.search(r'directly called by (\w+)',q)[1]==g['function'] and g['expected']==sorted(g['expected']);method='explicit direct-call target and sorted names matched'
        question_links.append({'task_id':t['id'],'passed':ok,'method':method})
    check('question_operation_semantics_review',all(x['passed'] for x in question_links),{'tasks':48,'literal_execution':24,'fixed_probe_impact':6,'direct_call_architecture':6,'semantic_manual_review':12,'limitations':'Manual semantic review is judgment, not a machine proof; impact scope is the listed input probes, and direct calls are syntactic, not a specific execution path.'})
    summary_records=[];summary_mismatches=[];all_build_ids=[]
    for project,asset in sorted(assets.items()):
        root=base/'dataset/projects'/project;nodes=source_graph(root);raw=raw_from_nodes(nodes)
        check('source_and_dependency_graph_'+project,equal(nodes,asset['nodes']) and equal(raw,asset['raw']))
        check('source_hashes_'+project,{p.name:sha(p) for p in sorted(root.glob('*.py'))}==asset['source_sha256'])
        check('baseline_index_'+project,equal(indexer.build_index(root),asset['index']))
        items={x['id']:x for x in asset['raw']+asset['summaries']};ids=[]
        for s in asset['summaries']:
            c=byid[s['call_id']];ids.append(c['call_id']);children=[items[x] for x in s['children']]
            p=leaf_prompt(children[0]['text']) if s['level']==1 else group_prompt(children)
            provenance=children[0]['source_uris'] if s['level']==1 else sorted({u for x in children for u in x['source_uris']})
            ok=c['prompt']==p and s['text']=='### '+s['id']+'\n'+c['answer'] and s['source_uris']==provenance and c['meta']['project']==project
            ok=ok and all(position[x['call_id']]<position[c['call_id']] for x in children if 'call_id' in x)
            if not ok:summary_mismatches.append({'project':project,'summary':s['id']})
            summary_records.append({'project':project,'id':s['id'],'call_id':c['call_id'],'level':s['level'],'prompt_sha256':textsha(p),'answer_sha256':textsha(c['answer']),'word_count':len(c['answer'].split()),'output_tokens':c['output_tokens'],'source_and_children_reconstructed':ok})
        check('summary_aggregate_'+project,ids==asset['build_call_ids'] and sum(byid[x]['input_tokens'] for x in ids)==asset['build_input_tokens'] and sum(byid[x]['output_tokens'] for x in ids)==asset['build_output_tokens'] and close(sum(byid[x]['wall_seconds'] for x in ids),asset['build_model_seconds']) and asset['build_seconds']>=asset['build_model_seconds'])
        all_build_ids.extend(ids)
    check('summary_prompts_outputs_ancestry_reconstructed',not summary_mismatches,{'summaries':len(summary_records),'mismatches':summary_mismatches})
    check('all_build_calls_accounted_for',set(all_build_ids)=={c['call_id'] for c in calls if c['purpose'].startswith('build')})
    firsteval=min(i for i,c in enumerate(calls) if c['purpose']=='answer' and c['meta'].get('task','').startswith('eval_'))
    check('append_order_build_before_eval',max(position[x] for x in all_build_ids)<firsteval,{'last_build_log_line':max(position[x] for x in all_build_ids)+1,'first_eval_answer_log_line':firsteval+1,'limitation':'Append order is internally consistent; logs are mutable and have no absolute call timestamps.'})
    sets=[('eval_main','eval',3,1024,ARMS),('eval_budget512','eval',1,512,['R0','RH']),('dev_main','dev',1,1024,ARMS)]
    current=[];all_answerids=[];allselectorids=[];row_audits=[];token_texts={wrap(c['prompt']) for c in calls};pack_attempts=[];schedules=[]
    for name,split,repeats,budget,arms in sets:
        rs=rows(base/f'results_{name}.jsonl');current+=rs;ts=read(base/f'dataset/{split}_tasks.json');identity=read(base/f'run_identity_{name}.json')
        expected={(t['id'],a,k) for t in ts for a in arms for k in range(repeats)};actual=[(r['task_id'],r['arm'],r['repeat']) for r in rs]
        check('complete_unique_'+name,len(actual)==len(set(actual)) and set(actual)==expected,{'rows':len(rs),'expected':len(expected)})
        check('run_identity_'+name,identity['config']==config and identity['experiment_sha256']==sha(snapshot/'experiment.py') and identity['task_sha256']==sha(base/f'dataset/{split}_tasks.json') and identity['asset_hashes']=={p.name:sha(p) for p in sorted((base/'assets').glob('*.json'))} and identity['budget']==budget and identity['repeats']==repeats and identity['arms']==arms)
        schedule=[(t['id'],a,k) for k in range(repeats) for t in ts for a in arms];random.Random(20261020).shuffle(schedule)
        check('schedule_'+name,actual==schedule)
        pairsel=defaultdict(list)
        for r in rs:
            t=tasks[r['task_id']];a=assets[r['project']];c=r['answer_call'];sel=r['selector'];all_answerids.append(c['call_id']);errs=[]
            if c!=byid.get(c['call_id']):errs.append('answer_call_log_mismatch')
            if c['prompt']!=answer_prompt(t['question'],r['context']):errs.append('answer_prompt_mismatch')
            if not equal(r['expected'],t['expected']):errs.append('gold_mismatch')
            if c['max_output_tokens']!=128:errs.append('answer_cap')
            if sel:
                allselectorids.append(sel['call_id']);pairsel[(r['task_id'],r['repeat'])].append(sel)
                if {k:v for k,v in sel.items() if k!='selector_pipeline_seconds'}!=byid.get(sel['call_id']):errs.append('selector_call_log_mismatch')
                outline=baseline._candidate_symbol_outline(a['index'],t['question'],24)
                if sel['prompt']!=baseline._selector_prompt(t['question'],outline):errs.append('selector_prompt_mismatch')
                match=baseline.URI_RE.search(sel['answer']) if sel['ok'] else None;u=match.group(0) if match else None
                valid=u in {s['uri'] for s in a['index']['symbols']} and u in a['nodes']
                if u!=r['selected_uri']:errs.append('selected_uri')
            else:valid=True
            correct,parsed,failure=grade(c,t['expected'])
            if not valid:correct=False;failure='selector_invalid'
            if (correct,failure)!=(r['correct'],r['failure']) or not equal(parsed,r['parsed_answer']):errs.append('grading')
            expectedinput=c['input_tokens']+(sel['input_tokens'] if sel else 0);expectedoutput=c['output_tokens']+(sel['output_tokens'] if sel else 0)
            if (expectedinput,expectedoutput)!=(r['input_tokens'],r['output_tokens']):errs.append('charged_tokens')
            if not close(r['model_seconds'],c['wall_seconds']+(sel['wall_seconds'] if sel else 0)):errs.append('model_seconds')
            if not close(r['query_seconds'],r['retrieval_seconds']+c['wall_seconds']+(sel['selector_pipeline_seconds'] if sel else 0)):errs.append('query_seconds')
            if r['retrieval_seconds']<0 or r['loop_wall_seconds']+1e-7<r['pre_answer_seconds_observed']+c['wall_seconds']:errs.append('timing_sign_or_physical_bounds')
            if r['context_tokens']>budget:errs.append('recorded_context_budget')
            if r['arm']=='A' and valid:
                b=indexer.expand_symbol_context(base/'dataset/projects'/r['project'],a['index'],r['selected_uri'],question=t['question'],numbered=False,dependency_depth=1,max_symbols=8);ordered=[]
                for i,text in enumerate(re.split(r'\n\n(?=### )',b['context'])):
                    header=text.split('```',1)[0];uris=baseline.URI_RE.findall(header)
                    for ass in b.get('bundle_assignments',[]):
                        if ass['path'] in header and f"L{ass['start_line']}-L{ass['end_line']}" in header:uris.extend(f"memory://symbol/{ass['path']}::{n}" for n in ass['names'])
                    ordered.append((0,{'id':f'native:{i}','level':0,'text':text,'source_uris':sorted(set(uris))}))
            elif r['arm']=='B' and valid:
                nodes=a['nodes'];start=r['selected_uri'];funcs=[start];const=[]
                for u,n in nodes.items():
                    if n['kind']=='function' and n['path']==nodes[start]['path'] and n['name'].lower() in t['question'].lower() and u not in funcs and len(funcs)<8:funcs.append(u)
                frontier=[start]
                for _ in range(2):
                    nxt=[]
                    for u in frontier:
                        for dep in nodes[u]['deps']:
                            if nodes[dep]['kind']=='constant':
                                if dep not in const:const.append(dep)
                            elif dep not in funcs and len(funcs)<8:funcs.append(dep);nxt.append(dep)
                    frontier=nxt
                ordered=[(0,{'id':u,'level':0,'text':fragment(nodes[u]),'source_uris':[u]}) for u in funcs+const]
            elif r['arm'] in ('A','B'):ordered=[]
            else:
                items=a['raw']+([x for x in a['summaries'] if x['level']==1] if r['arm']=='RF' else a['summaries'] if r['arm']=='RH' else [])
                ordered=rank(t['question'],a['raw'],items)
            chosenids={x['id'] for x in r['chosen']};context='';seen=set();attempts=[];rechosen=[];rejected=[]
            for score,item in ordered:
                if item['level']==0 and set(item['source_uris'])<=seen:continue
                candidate=context+('\n\n' if context else '')+item['text'];token_texts.add(candidate)
                accepted=item['id'] in chosenids;attempts.append({'text':candidate,'id':item['id'],'accepted':accepted})
                if accepted:
                    rechosen.append({'id':item['id'],'level':item['level'],'score':score,'source_uris':item['source_uris']});context=candidate
                    if item['level']==0:seen.update(item['source_uris'])
                else:rejected.append(item['id'])
            if context!=r['context']:errs.append('context_reconstruction')
            if len(rechosen)!=len(r['chosen']) or any(x['id']!=y['id'] or x['level']!=y['level'] or x['source_uris']!=y['source_uris'] or not close(x['score'],y['score']) for x,y in zip(rechosen,r['chosen'])):errs.append('ranking_chosen')
            if rejected!=r['rejected']:errs.append('rejected_order')
            required=set(t['required_uris']);cited={u for x in rechosen for u in x['source_uris']}
            if not close(len(seen&required)/len(required),r['raw_evidence_recall']) or not close(len(cited&required)/len(required),r['provenance_recall_not_content_recall']) or (required<=seen)!=r['all_raw_evidence']:errs.append('recall_metadata')
            token_texts.add(r['context']);pack_attempts.append((r,attempts));row_audits.append({'set':name,'task_id':r['task_id'],'arm':r['arm'],'repeat':r['repeat'],'errors':errs})
        check('selector_shared_pairs_'+name,all(len(v)==2 and equal(v[0],v[1]) for v in pairsel.values()),{'unique_pairs':len(pairsel)})
    check('all_current_rows_reconstructed',not any(x['errors'] for x in row_audits),{'rows':len(row_audits),'failures':[x for x in row_audits if x['errors']]})
    initial=rows(base/'development_calibration/initial_results_dev_main.jsonl')
    check('archived_initial_dev_call_linkage',all(r['answer_call']==byid.get(r['answer_call']['call_id']) for r in initial),{'rows':len(initial),'limitation':'Archived initial development used earlier interface/grader; excluded from current primary metrics.'})
    all_answerids += [r['answer_call']['call_id'] for r in initial]
    check('all_answer_calls_accounted_for',len(all_answerids)==len(set(all_answerids)) and set(all_answerids)=={c['call_id'] for c in calls if c['purpose']=='answer'})
    allselectorids += [r['selector']['call_id'] for r in initial if r['selector']]
    check('all_selector_calls_accounted_for',set(allselectorids)=={c['call_id'] for c in calls if c['purpose']=='select'})
    tokenreport={'status':'not_run'}
    if not args.skip_tokenizer:
        print('Offline tokenizer: reconstructing',len(token_texts),'distinct strings',flush=True)
        counts,tokmeta=tokenize_many(sorted(token_texts),Path(env['model_path']))
        badcalls=[{'call_id':c['call_id'],'recorded':c['input_tokens'],'recomputed':counts[wrap(c['prompt'])]} for c in calls if counts[wrap(c['prompt'])]!=c['input_tokens']]
        badcontexts=[];badpacking=[]
        for r,attempts in pack_attempts:
            key={k:r[k] for k in ('task_id','arm','repeat','budget')}
            if counts[r['context']]!=r['context_tokens']:badcontexts.append(key|{'recorded':r['context_tokens'],'recomputed':counts[r['context']]})
            for x in attempts:
                if (counts[x['text']]<=r['budget'])!=x['accepted']:badpacking.append(key|{'node':x['id'],'tokens':counts[x['text']],'accepted':x['accepted']})
        check('independent_tokenizer_all_call_inputs',not badcalls,{'calls':len(calls),'mismatches':badcalls})
        check('independent_tokenizer_all_saved_contexts',not badcontexts,{'rows':len(pack_attempts),'mismatches':badcontexts})
        check('independent_pack_fit_decisions',not badpacking,{'attempts':sum(len(a) for _,a in pack_attempts),'mismatches':badpacking[:30]})
        tokenreport={'status':'completed','distinct_strings':len(counts),'distinct_wrapped_prompts':len({wrap(c['prompt']) for c in calls}),'distinct_contexts':len({r['context'] for r in current}),'method':tokmeta,'model_sha256_matches_environment':sha(env['model_path'])==env['model_sha256'],'output_token_note':'Generated output token counts match server predicted_n. Stripped text cannot independently recover hidden EOS or stripped whitespace token counts.'}
        (out/'tokenizer_counts.json').write_text(json.dumps({'metadata':tokenreport,'counts_by_text_sha256':{textsha(t):n for t,n in counts.items()}},indent=2)+'\n')
    mainrows=rows(base/'results_eval_main.jsonl');analysis=read(base/'analysis.json');metrics={};latency={};diagnostic={}
    for arm in ARMS:
        rs=[r for r in mainrows if r['arm']==arm];questions=defaultdict(list)
        for r in rs:questions[r['task_id']].append(r)
        m={'correct':sum(r['correct'] for r in rs),'total':len(rs),'accuracy':statistics.mean(r['correct'] for r in rs),'mean_query_seconds':statistics.mean(statistics.median(x['query_seconds'] for x in v) for v in questions.values()),'mean_input_tokens':statistics.mean(r['input_tokens'] for r in rs),'mean_output_tokens':statistics.mean(r['output_tokens'] for r in rs)};metrics[arm]=m
        check('metrics_'+arm,all(close(value,analysis['metrics_by_arm'][arm][k]) for k,value in m.items()))
        latency[arm]={'mean_retrieval_seconds':statistics.mean(r['retrieval_seconds'] for r in rs),'median_retrieval_seconds':statistics.median(r['retrieval_seconds'] for r in rs),'mean_physical_loop_seconds':statistics.mean(r['loop_wall_seconds'] for r in rs),'mean_charged_query_seconds':statistics.mean(r['query_seconds'] for r in rs),'mean_answer_wall_minus_server_compute_seconds':statistics.mean(r['answer_call']['wall_seconds']-(r['answer_call']['timings']['prompt_ms']+r['answer_call']['timings']['predicted_ms'])/1000 for r in rs),'unique_answer_prompts':len({r['answer_call']['prompt'] for r in rs})}
        order=[r for r in rs if not r['correct'] and isinstance(r['parsed_answer'],list) and isinstance(r['expected'],list) and all(type(x)is str for x in r['parsed_answer']+r['expected']) and len(set(r['parsed_answer']))==len(r['parsed_answer']) and len(set(r['expected']))==len(r['expected']) and set(r['parsed_answer'])==set(r['expected'])]
        diagnostic[arm]={'strict_correct':m['correct'],'order_only_wrong':len(order),'order_tolerant_correct_secondary':m['correct']+len(order)}
    # Recompute six-cluster bootstrap and sign flips without importing the analysis code.
    comparisons={}
    for comparison in ('RH-A','RH-R0','RH-RF'):
        h,b=comparison.split('-');projects=sorted({r['project'] for r in mainrows});ds=[]
        for p in projects:ds.append(statistics.mean(r['correct'] for r in mainrows if r['project']==p and r['arm']==h)-statistics.mean(r['correct'] for r in mainrows if r['project']==p and r['arm']==b))
        boot=sorted(sum(ds[i] for i in sample)/6 for sample in itertools.product(range(6),repeat=6))
        def q(p):
            x=(len(boot)-1)*p;lo=math.floor(x);hi=math.ceil(x);return (boot[lo]+(boot[hi]-boot[lo])*(x-lo))*100
        delta=statistics.mean(ds);p=sum(abs(sum(x*s for x,s in zip(ds,signs))/6)>=abs(delta)-1e-12 for signs in itertools.product((-1,1),repeat=6))/64
        comp={'delta_pp':100*delta,'ci95_pp':[q(.025),q(.975)],'p_value':p};comparisons[comparison]=comp;saved=analysis['comparisons'][comparison]
        check('comparison_'+comparison,close(comp['delta_pp'],saved['delta_pp']) and all(close(x,y) for x,y in zip(comp['ci95_pp'],saved['ci95_pp'])) and close(p,saved['p_value']))
    nonstandard=[]
    def strictpairs(pairs):
        keys=[k for k,v in pairs]
        if len(keys)!=len(set(keys)):raise ValueError('duplicate object key')
        return dict(pairs)
    for c in calls:
        if c['purpose']!='answer':continue
        s=c['answer'].strip();m=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',s,re.I|re.S)
        if m:s=m[1]
        try:json.loads(s)
        except ValueError:continue
        try:json.loads(s,object_pairs_hook=strictpairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
        except ValueError:nonstandard.append(c['call_id'])
    check('no_observed_duplicate_JSON_keys_or_nonfinite_values',not nonstandard,nonstandard)
    over100=[r for r in summary_records if r['word_count']>100]
    cache_repeated=Counter(wrap(c['prompt']) for c in calls)
    cache_source=assets['eval_cache']['nodes']['memory://symbol/rules.py::canonical_query']['source']
    cache_summary=next(s for s in assets['eval_cache']['summaries'] if s['id']=='summary:leaf:memory://symbol/rules.py::canonical_query')
    cache_probe=execute(base/'dataset/projects/eval_cache',[{'module':'rules','function':'canonical_query','args':[{'a b':'x&y'}]}])[0]
    summary_factual_example={'project':'eval_cache','node':'memory://symbol/rules.py::canonical_query','summary_call_id':cache_summary['call_id'],'summary':cache_summary['text'],'raw_source':cache_source,'audit_only_probe':{'query':{'a b':'x&y'},'actual_return':cache_probe},'observation':'The summary says URL-encoded format, but source concatenates str(key), equals, and str(value), without percent-encoding spaces or ampersands.','caution':'This audit-only probe is not added to the frozen benchmark. Existing evaluated query keys do not isolate this defect, so it is not evidence that this error caused a scored failure.'}
    findings=[
      {'severity':'observed_summary_error','id':'summary_factuality','finding':'At least one frozen leaf summary makes an unsupported URL-encoding claim. Exact prompt/output reconstruction validates lineage but cannot certify all summary facts.','evidence':summary_factual_example,'implication':'Treat summaries as fallible derived context. This known error has no established causal link to an evaluated failure; all 141 summaries were not semantically certified.'},
      {'severity':'material_interpretation','id':'latency_cache_and_charging','finding':'Original query_seconds is reconstructed per-arm charged latency. A and B reuse one selector result per task/repeat but each is charged its full recorded selector pipeline time. Client.token_cache is shared across all arms and repeats within one process; it is not disabled by cache_prompt=False.','evidence':['source_snapshot/experiment.py:Client.tokens','source_snapshot/experiment.py:run_eval','results_eval_main.jsonl'],'implication':'Do not label this cold independent end-to-end latency. Tiny RH-R0 differences are not established speed improvements. New query-level cache policy and phase timestamps are needed.'},
      {'severity':'missing_evidence','id':'effective_runtime','finding':'Original model_calls retain unwrapped prompts and selected response fields, not exact HTTP payloads, full responses, an executed server startup log/properties, effective runtime settings, or absolute call times. reproduce.txt contains a suggested startup command but is not an execution record. environment.llama_version is empty.','implication':'Saved code supports intended temperature/seed/cache/context settings; actual original server configuration and chronology cannot be independently proven. A matching model file today does not prove original server loaded it.'},
      {'severity':'missing_evidence','id':'preregistration','finding':'Protocol states multiple freeze/refinement times and initial development records are archived, but protocol and run identities are mutable local files. The manifest hashes were created after evaluation.','implication':'Hashes prove current internal consistency, not that no post-result changes occurred. Internal append order does support build-before-eval, without tamper-evident chronological proof.'},
      {'severity':'scope','id':'RAPTOR_adaptation','finding':'R0/RF/RH use source-derived lexical TF-IDF cosine and AST dependency/per-file/project grouping; no SBERT embedding, UMAP reduction, or GMM clustering.','implication':'Results apply to this RAPTOR-inspired code adaptation, not original RAPTOR generally. RH-A changes selector, cross-file reach, candidate pool and context usage together; RH-R0 is the cleaner added-summary comparison.'},
      {'severity':'scope','id':'gold_and_recall','finding':'Gold execution, interventions and AST direct calls are reproducible. required_uris are conservative metadata dependencies, not proof every symbol is necessary. Summary ancestry recall does not establish information retained accurately.','implication':'Use raw_evidence_recall as source inclusion; do not equate it or ancestor coverage with factual sufficiency.'},
      {'severity':'scope','id':'small_correlated_pilot','finding':'48 questions in six small synthetic projects; three identical deterministic repeats yielded identical outcomes per question/arm. Projects share file scaffold and ancillary functions.','implication':'Six project clusters, not 144 independent trials per arm. Cluster intervals and sign flips remain exploratory with six heterogeneous clusters; no production generalization or causal proof from examples.'},
      {'severity':'minor_protocol_deviation','id':'summary_word_limit','finding':'Five generated summaries exceed the requested 100 English words, though all satisfy the 256-token hard output cap. Four belong to evaluation projects.','evidence':over100,'implication':'Report requested natural-language length as guidance, not a verified enforced maximum. Context token caps are separately audited.'},
      {'severity':'implementation_limit','id':'asset_cache_guard','finding':'Asset reuse checks source hashes only; model/prompt/build configuration are not part of the cache guard. Current assets are linked exactly to saved build calls.','implication':'A future run after changing model or summarizer could reuse stale summaries unless an explicit build identity is added.'},
      {'severity':'implementation_limit','id':'pack_partial_duplicate','finding':'Packing skips a raw candidate only if all its source URIs were seen. Partial overlap preserves duplicate fragments.','implication':'Token caps are respected but available information per token may fall, affecting the experimental policy itself.'},
      {'severity':'grading_definition','id':'strict_sorted_lists','finding':'Primary scoring includes sorted-list order and JSON/schema compliance; a secondary order-tolerant diagnostic recovers same-set lists only.','evidence':diagnostic,'implication':'Primary accuracy is exact structured-answer success, not pure semantic correctness. Do not substitute the posthoc diagnostic for the fixed primary score.'},
      {'severity':'implementation_limit','id':'json_parser','finding':'Python json.loads accepts duplicate object keys and nonfinite constants unless configured otherwise; none observed in saved parseable answer outputs.','implication':'No observed scoring effect, but future strict-JSON claims should use a standards-strict parser.'},
      {'severity':'missing_evidence','id':'preprocessing_measurement_boundary','finding':'preprocessing_costs.json contains 18 small A/raw index measurements, but no corresponding measurement script is archived. RH raw+summary vectors are computed before query timers and are not included in build_assets build_seconds.','implication':'Preprocessing numbers can be aggregated, but their measured boundary cannot be independently reconstructed. Setup extrapolations omit a small unmeasured vector construction phase and are not verified complete cold-start costs.'},
      {'severity':'cost_definition','id':'setup_and_units','finding':'Server prompt_ms/predicted_ms are milliseconds. Per-call wall_seconds includes tokenizer lookup/HTTP/processing overhead. Build wall includes source/index/summary work; retrieval document vectors are constructed outside query timing.','implication':'Do not call model_seconds pure inference or compare token totals with milliseconds. Dataset-specific build-cost amortization is conditional on stable corpus and workload.'}
    ]
    unchanged={p:sha(base/p) for p in before};check('original_files_unchanged_by_audit',unchanged==before)
    report={'audit_version':2,'audited_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS_WITH_MATERIAL_LIMITATIONS' if not failures else 'FAIL_INTERNAL_CHECKS','scope':'Original frozen pilot only; no generation or server requests. Independent parser/graph/gold/grade/ranking/packing/token/metric reconstruction. Native baseline expansion is re-executed from its archived implementation.','checks':checks,'failed_checks':failures,'summary':{'checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),'current_result_rows':len(current),'model_calls':len(calls),'summary_calls':len(summary_records),'original_files_sha256_verified':len(before)},'findings':findings,'tokenizer':tokenreport,'recomputed_main_metrics':metrics,'recomputed_comparisons':comparisons,'latency_diagnostics':latency,'secondary_order_diagnostics':diagnostic,'call_prompt_cache_diagnostic':{'distinct_wrapped_prompts':len(cache_repeated),'repeated_call_prompt_instances':sum(n-1 for n in cache_repeated.values()),'caution':'Exact cache state per original run and per packing tokenization is not logged; repeats illustrate potential reuse, not per-request hit reconstruction.'},'gold_reexecution':gold_results,'question_operation_review':question_links,'summary_factual_example':summary_factual_example,'summary_reconstruction':summary_records,'original_hashes_before_and_after':before,'recommendation':'Retain original accuracy as internally reproducible pilot evidence with explicit limitations. Re-measure latency with exact requests/runtime identity, UTC timestamps, observed phase durations, explicit tokenizer cache policy, isolated selector accounting, frozen summary hashes, and a pre-result protocol hash. Do not claim original RAPTOR superiority.'}
    (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'passed':report['summary']['checks_passed'],'total':len(checks),'failed':failures,'out':str(out/'audit.json')},ensure_ascii=False,indent=2))
    return 0 if not failures else 1

if __name__=='__main__':raise SystemExit(main())
