"""Offline integrity verification for the v2 frozen latency remeasurement.

No model generation or server calls. --partial permits an in-progress prefix;
final mode requires all 24 development + 432 new + 144 regression rows.
Only integrity_v2.json is written. Tokenizer checks use a vocab-only executable.
"""
from __future__ import annotations
import argparse, ast, importlib, itertools, json, math, random, re, shlex, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
import audit_v2 as audit
HERE=Path(__file__).resolve().parent
BASE=audit.BASE
ARMS=['A','RH','C']

def digest(value):return audit.textsha(json.dumps(value,sort_keys=True,ensure_ascii=False))
def dt(s):return datetime.fromisoformat(s)
def read_rows(path,partial=False):
    if not path.exists():return []
    lines=path.read_text().splitlines();out=[]
    for i,line in enumerate(lines):
        try:out.append(json.loads(line))
        except ValueError:
            if partial and i==len(lines)-1:break
            raise
    return out

def make_schedule(tasks,repeats,seed):
    rng=random.Random(seed);plan=[];perms=list(itertools.permutations(ARMS))
    for repeat in range(repeats):
        ts=list(tasks);rng.shuffle(ts);orders=list(perms);rng.shuffle(orders)
        for i,t in enumerate(ts):
            plan.extend({'task_id':t['id'],'repeat':repeat,'arm':a} for a in orders[i%6])
    return plan

def compact_expected(asset,chosen):
    """Construct unique bodies from the actual selected items, independent of v2."""
    items={x['id']:x for x in asset['raw']+asset['summaries']};payload={'source':{},'imports':{},'summary':{}};blocks=[];paths=set();occurrences=0
    for itemref in chosen:
        item=items[itemref['id']]
        if item['level']==0:
            for u in item['source_uris']:
                n=asset['nodes'][u];occurrences+=1
                if u in payload['source']:continue
                lines=[f"# Code {n['path']}::{n['name']}"]
                if n['path'] not in paths:
                    if n['imports']:lines.append(n['imports'])
                    paths.add(n['path']);payload['imports'][n['path']]=n['imports']
                lines.append(n['source']);payload['source'][u]=n['source'];blocks.append('\n'.join(lines))
        else:
            body=item['text'].split('\n',1)[1]
            if item['id'] in payload['summary']:continue
            payload['summary'][item['id']]=body
            label=(f"# Function summary {item['id'].split('memory://symbol/',1)[1]}" if item['level']==1 else f"# File summary {item['path']}" if item['level']==2 else '# Project summary')
            blocks.append(label+'\n'+body)
    return '\n\n'.join(blocks),payload,occurrences

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=BASE/'revision_v2');ap.add_argument('--partial',action='store_true');ap.add_argument('--skip-tokenizer',action='store_true');ap.add_argument('--skip-model-hash',action='store_true');args=ap.parse_args();out=args.out.resolve()
    checks=[];pending=[]
    def check(name,ok,detail=None):checks.append({'check':name,'passed':bool(ok),'detail':detail})
    protocol=audit.read(out/'protocol.json');env=audit.read(out/'environment.json');fp=env['fingerprint'];fph=digest(fp)
    source=(HERE/'experiment_v2.py').read_text();tree=ast.parse(source)
    config=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets))
    check('protocol_code_config',all(protocol.get(k)==v for k,v in config.items()) and protocol['experiment_v2_sha256']==audit.sha(HERE/'experiment_v2.py'))
    check('v1_dependency_fingerprints',protocol['dependency_hashes']=={'experiment_v1':audit.sha(HERE/'experiment.py'),'baseline_indexer':audit.sha(audit.REPO/'1st/symbol_test/symbol_bench/indexer.py'),'baseline_runner':audit.sha(audit.REPO/'1st/symbol_test/symbol_bench/run_benchmark.py')})
    check('holdout_artifacts_frozen',protocol['task_artifact_hashes']=={n:audit.sha(out/'holdout'/n) for n in ('eval_tasks.json','manifest.json','gold_validation.json')} and protocol['holdout_generator_sha256']==audit.sha(HERE/'holdout_v2.py'))
    assethashes={p.name:audit.sha(p) for p in sorted((BASE/'assets').glob('*.json'))};assets={p.stem:audit.read(p) for p in (BASE/'assets').glob('*.json')}
    check('frozen_original_summaries',assethashes==protocol['source_snapshot'])
    check('environment_fingerprint',fph==env['fingerprint_sha256'] and fp['server_properties']=={k:env['server_props'][k] for k in fp['server_properties']})
    check('server_context_and_slots',fp['server_properties']['default_generation_settings']['n_ctx']==8192 and fp['server_properties']['total_slots']==1)
    check('binary_fingerprint',fp['server_binary_sha256']==audit.sha(env['server_command'][0]))
    if not args.skip_model_hash:check('model_fingerprint',fp['model_sha256']==audit.sha(fp['server_properties']['model_path']))
    else:pending.append('Current model file hash intentionally not reread in partial mode; frozen original hash and runtime fingerprint still checked.')
    launch=audit.read(out/'server_launch_observation.json')
    check('observed_launch_command',shlex.split(launch['observed_command'])==env['server_command'] and (out/launch['server_log']).exists())
    props=env['server_props'];check('model_path_matches_launch',str(Path(props['model_path']).resolve())==str(Path(env['server_command'][env['server_command'].index('-m')+1]).resolve()))
    check('tokenizer_reset_policy_in_frozen_code','client.reset_query()\n        started, started_utc' in source and 'self.token_cache.clear()' in source)
    calls=read_rows(out/'model_calls.jsonl',args.partial);byid={c['call_id']:c for c in calls};check('unique_call_ids',len(byid)==len(calls),{'calls':len(calls),'purposes':dict(Counter(c['purpose'] for c in calls))})
    call_errors=[]
    for c in calls:
        expectedrequest={'prompt':audit.wrap(c['prompt']),'n_predict':c['max_output_tokens'],'temperature':0,'seed':1,'cache_prompt':False,'id_slot':0,'stop':['<|im_end|>','<|im_start|>'],'stream':False}
        errors=[]
        if c['request']!=expectedrequest:errors.append('exact_request')
        if c['call_id']!=digest([c['request'],c['purpose'],c['meta'],c['started_at_utc']])[:20]:errors.append('call_id')
        if not c['ok'] or c.get('truncated') or c.get('stopped_limit') or c.get('stop_type')=='limit':errors.append('execution_or_limit')
        if c['input_tokens']!=c['timings'].get('prompt_n') or c['output_tokens']!=c['timings'].get('predicted_n'):errors.append('server_tokens')
        if c['timings'].get('cache_n')!=0:errors.append('KV_cache_reuse')
        if not 0<=c['output_tokens']<=c['max_output_tokens'] or c['input_tokens']+c['max_output_tokens']>8192:errors.append('token_cap')
        utc_elapsed=(dt(c['ended_at_utc'])-dt(c['started_at_utc'])).total_seconds()
        if abs(utc_elapsed-c['wall_seconds'])>.05:errors.append('UTC_wall_mismatch')
        if dt(c['started_at_utc'])<dt(protocol['frozen_at_utc']):errors.append('before_freeze')
        if errors:call_errors.append({'call_id':c['call_id'],'errors':errors})
    check('call_request_response_timing_reconstruction',not call_errors,call_errors)
    check('sequential_calls_do_not_overlap',all(dt(a['ended_at_utc'])<=dt(b['started_at_utc']) for a,b in zip(calls,calls[1:])))
    preparations={}
    for p in out.glob('preparation_*.json'):
        prep=audit.read(p);preparations[prep['session_id']]=prep
        check('preparation_'+prep['session_id'],prep['runtime_fingerprint_sha256']==fph and all(v>0 for v in prep['document_vector_build_seconds'].values()))
    warmups={}
    for c in calls:
        if c['purpose']=='warmup':warmups.setdefault(c['meta']['session_id'],[]).append(c)
    check('warmup_per_preparation',set(warmups)==set(preparations) and all(len(cs)==1 and cs[0]['prompt']=='Return only {"answer":0}.' for cs in warmups.values()))
    sys.path.insert(0,str(audit.REPO/'1st'));import symbol_test.symbol_bench
    indexer=audit.load_module('symbol_test.symbol_bench.indexer',BASE/'source_snapshot/baseline_indexer.py')
    baseline=audit.load_module('symbol_test.symbol_bench.audit_v2_runner',BASE/'source_snapshot/baseline_run_benchmark.py')
    resultrows=[];usedcalls=set();rowerrors=[];allpairs=[];tokenstrings=set();originals={};completion={}
    for split,repeats,offset,taskpath in [('dev',1,200,BASE/'dataset/dev_tasks.json'),('new',3,0,out/'holdout/eval_tasks.json'),('old',1,100,BASE/'dataset/eval_tasks.json')]:
        tasks=audit.read(taskpath);taskmap={t['id']:t for t in tasks};rs=read_rows(out/f'results_{split}.jsonl',args.partial);completion[split]={'actual':len(rs),'expected':len(tasks)*repeats*3};plan=make_schedule(tasks,repeats,20261021+offset)
        actual=[{k:r[k] for k in ('task_id','repeat','arm')} for r in rs];unique={(x['task_id'],x['repeat'],x['arm']) for x in actual}
        check('unique_and_schedule_prefix_'+split,len(unique)==len(actual) and actual==plan[:len(actual)])
        if args.partial and len(rs)<len(plan):pending.append(f'{split}: {len(rs)}/{len(plan)} rows, final completeness pending')
        else:check('complete_'+split,len(rs)==len(plan))
        ip=out/f'identity_{split}.json'
        if ip.exists():
            ident=audit.read(ip);check('identity_'+split,ident['config']==config and ident['code_sha256']==protocol['experiment_v2_sha256'] and ident['v1_code_sha256']==protocol['dependency_hashes']['experiment_v1'] and ident['task_sha256']==audit.sha(taskpath) and ident['protocol_sha256']==audit.sha(out/'protocol.json') and ident['asset_sha256']==assethashes and ident['runtime_fingerprint_sha256']==fph and ident['environment_sha256']==audit.sha(out/'environment.json') and ident['schedule']==plan and ident['split']==split)
        elif args.partial:pending.append('Missing identity_'+split+' while run is incomplete')
        else:check('identity_'+split,False,'missing')
        for repeat in range(repeats):
            orders=Counter(tuple(x['arm'] for x in plan[i:i+3]) for i in range(0,len(plan),3) if plan[i]['repeat']==repeat)
            check(f'arm_permutations_{split}_{repeat}',len(orders)==6 and max(orders.values())-min(orders.values())<=1,dict((str(k),v) for k,v in orders.items()))
        pairs=defaultdict(dict)
        for r in rs:
            task=taskmap[r['task_id']];asset=assets[r['project']];c=r['answer_call'];sel=r['selector'];errors=[];usedcalls.add(c['call_id']);items={x['id']:x for x in asset['raw']+asset['summaries']}
            if c!=byid.get(c['call_id']):errors.append('answer_log_link')
            expectedmeta={'split':split,**{k:r[k] for k in ('task_id','repeat','arm')}}
            if c['meta']!=expectedmeta or c['purpose']!='answer' or c['max_output_tokens']!=128:errors.append('answer_metadata')
            if r['question']!=task['question'] or not audit.equal(r['expected'],task['expected']) or r['category']!=task['category']:errors.append('task_link')
            if c['prompt']!=audit.answer_prompt(task['question'],r['context']):errors.append('answer_prompt')
            valid=True
            if r['arm']=='A':
                if sel is None:errors.append('missing_selector')
                else:
                    usedcalls.add(sel['call_id'])
                    if sel!=byid.get(sel['call_id']) or sel['meta']!=expectedmeta or sel['max_output_tokens']!=96:errors.append('selector_link')
                    if sel['prompt']!=baseline._selector_prompt(task['question'],baseline._candidate_symbol_outline(asset['index'],task['question'],24)):errors.append('selector_prompt')
                    match=baseline.URI_RE.search(sel['answer']) if sel['ok'] else None;uid=match.group(0) if match else None;valid=uid in asset['nodes'] and uid in {x['uri'] for x in asset['index']['symbols']}
                    if r['selected_uri']!=uid:errors.append('selector_uri')
                    if valid:
                        bundle=indexer.expand_symbol_context(BASE/'dataset/projects'/r['project'],asset['index'],uid,question=task['question'],numbered=False,dependency_depth=1,max_symbols=8)
                        native=re.split(r'\n\n(?=### )',bundle['context']);original='\n\n'.join(native[int(x['id'].split(':')[1])] for x in r['chosen'])
                    else:original=''
            else:
                if sel is not None:errors.append('unexpected_selector')
                original='\n\n'.join(items[x['id']]['text'] for x in r['chosen'])
            if audit.textsha(original)!=r['selected_context_sha256']:errors.append('selected_context_hash')
            originals[(split,r['task_id'],r['repeat'],r['arm'])]=original;tokenstrings.update([original,r['context'],c['request']['prompt']])
            if sel:tokenstrings.add(sel['request']['prompt'])
            if r['arm']=='C':
                expectedcontext,payload,occurrences=compact_expected(asset,r['chosen'])
                if expectedcontext!=r['context']:errors.append('actual_compacted_payload_text')
                cp=r['compaction'];expectedstats={'payload_preserved':True,'selected_payload_sha256':digest(payload),'emitted_payload_sha256':digest(payload),'unique_raw_symbols':len(payload['source']),'raw_occurrences_before':occurrences,'unique_import_blocks':len(payload['imports']),'summary_bodies':len(payload['summary'])}
                if not all(cp.get(k)==v for k,v in expectedstats.items()):errors.append('compaction_metadata')
                if r['context_tokens']>r['selected_context_tokens']:errors.append('compaction_expanded_tokens')
            elif original!=r['context'] or r['context_tokens']!=r['selected_context_tokens'] or r['compaction'] is not None or r['compaction_seconds']!=0:errors.append('uncompacted_context')
            correct,parsed,failure=audit.grade(c,task['expected'])
            if not valid:correct=False;failure='selector_invalid'
            if (correct,failure)!=(r['correct'],r['failure']) or not audit.equal(parsed,r['parsed_answer']):errors.append('grade')
            if r['input_tokens']!=c['input_tokens']+(sel['input_tokens'] if sel else 0) or r['output_tokens']!=c['output_tokens']+(sel['output_tokens'] if sel else 0):errors.append('token_sum')
            rawseen={u for x in r['chosen'] if x['level']==0 for u in x['source_uris']};required=set(task['required_uris'])
            if not audit.close(r['raw_evidence_recall'],len(rawseen&required)/len(required)) or r['all_raw_evidence']!=(required<=rawseen):errors.append('raw_recall')
            if not 0<=r['context_tokens']<=1024 or not 0<=r['selected_context_tokens']<=1024:errors.append('context_cap')
            residual=r['query_seconds']-r['pre_answer_seconds']-c['wall_seconds']
            if residual<-.001 or residual>.1:errors.append('physical_time_sum')
            if not 0<=r['compaction_seconds']<=r['pre_answer_seconds'] or not 0<=r['tokenize_seconds']<=r['query_seconds'] or r['tokenize_http_calls']<1:errors.append('nested_stage_bounds')
            if sel and r['pre_answer_seconds']<sel['wall_seconds']:errors.append('selector_not_in_preanswer')
            if abs((dt(r['ended_at_utc'])-dt(r['started_at_utc'])).total_seconds()-r['query_seconds'])>.05:errors.append('query_UTC_wall')
            if not dt(r['started_at_utc'])<=dt(c['started_at_utc'])<=dt(c['ended_at_utc'])<=dt(r['ended_at_utc']):errors.append('answer_within_query')
            sid=r['session_id']
            if sid not in warmups or len(warmups[sid])!=1 or dt(warmups[sid][0]['ended_at_utc'])>dt(r['started_at_utc']):errors.append('warmup_precedes_query')
            if errors:rowerrors.append({'split':split,'task_id':r['task_id'],'repeat':r['repeat'],'arm':r['arm'],'errors':errors})
            if r['arm'] in ('RH','C'):pairs[(r['task_id'],r['repeat'])][r['arm']]=r
        for key,pair in pairs.items():
            if set(pair)!={'RH','C'}:
                if args.partial:pending.append(f'Unfinished RH/C pair: {split} {key}')
                else:check('paired_'+split+str(key),False,'missing arm')
                continue
            rh,c=pair['RH'],pair['C'];same=all(audit.equal(rh[k],c[k]) for k in ('chosen','rejected','selected_context_tokens','selected_context_sha256'))
            allpairs.append({'split':split,'task_id':key[0],'repeat':key[1],'identical_selected_evidence':same,'original_tokens':rh['context_tokens'],'compacted_tokens':c['context_tokens']})
        resultrows+=rs
    check('all_result_row_links_and_payloads',not rowerrors,rowerrors)
    check('RH_C_identical_selected_evidence',all(x['identical_selected_evidence'] for x in allpairs),{'pairs':len(allpairs)})
    selectors=[r['selector']['call_id'] for r in resultrows if r['selector']]
    check('no_selector_sharing',len(selectors)==len(set(selectors)))
    extra=set(byid)-usedcalls-{c['call_id'] for c in calls if c['purpose']=='warmup'}
    if extra and args.partial:pending.append(f'{len(extra)} logged calls not yet attached to completed rows')
    else:check('no_unmapped_model_calls',not extra,sorted(extra))
    tokenreport={'status':'skipped'}
    if not args.skip_tokenizer:
        counts,metadata=audit.tokenize_many(sorted(tokenstrings),Path(fp['server_properties']['model_path']));bad=[]
        for r in resultrows:
            key=(r['split'],r['task_id'],r['repeat'],r['arm'])
            if counts[r['context']]!=r['context_tokens'] or counts[originals[key]]!=r['selected_context_tokens']:bad.append(list(key)+['context_count'])
            for c in [r['answer_call']]+([r['selector']] if r['selector'] else []):
                if counts[c['request']['prompt']]!=c['input_tokens']:bad.append(list(key)+['prompt_count'])
        check('vocab_only_actual_context_and_input_counts',not bad,bad)
        tokenreport={'status':'completed','distinct_strings':len(counts),'method':metadata}
    else:pending.append('Independent tokenizer skipped in this partial snapshot.')
    failed=[c for c in checks if not c['passed']];complete=not args.partial and not pending and not failed
    result={'version':2,'created_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'partial_snapshot' if args.partial else 'final','status':'PASS' if complete else 'FAIL' if failed else 'PENDING_FINAL','checks':checks,'failed_checks':failed,'pending':pending,'completion':completion,'model_calls':len(calls),'rows':len(resultrows),'paired_evidence':allpairs,'tokenizer':tokenreport,'timing_definition':'query_seconds is observed physical wall. pre_answer_seconds includes selector/packing/compaction; answer_call.wall_seconds plus small logging overhead completes query. tokenize_seconds is nested across these phases, and compaction_seconds includes its tokenizer work: neither is added again.','evidence_limits':['Protocol/UTC logs are local mutable evidence, not externally signed preregistration.','Frozen code clears token-count cache at each query; original per-tokenize HTTP payloads/responses are not individually logged, so cache-reset behavior is supported by code and per-query request counts, not a complete tokenization wire trace.','Complete HTTP request payloads and selected response timing fields are saved; full raw server responses are not retained.','C preserves unique raw/import/summary body strings. It changes headers, repetition, grouping and positional presentation; equivalent reasoning behavior is not guaranteed.','New questions reuse six original synthetic projects and summaries. Old questions are explicitly exploratory regression; this is not validation on independent real repositories.'],'input_fingerprints':{'protocol':audit.sha(out/'protocol.json'),'environment':audit.sha(out/'environment.json'),'experiment_v2':audit.sha(HERE/'experiment_v2.py'),'runtime_fingerprint':fph}}
    (out/'integrity_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'failed':failed,'rows':len(resultrows),'completion':completion,'output':str(out/'integrity_v2.json')},ensure_ascii=False,indent=2));return 1 if failed else 0

if __name__=='__main__':raise SystemExit(main())
