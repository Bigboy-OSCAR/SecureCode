"""Independent reconstruction of prompts, hierarchy, retrieval, compaction and statistics."""
from __future__ import annotations
import hashlib, json, math, sys
from collections import Counter, defaultdict
from datetime import datetime
sys.dont_write_bytecode=True
import experiment_raptor_large as exp
import audit_v2 as independent
import verify_ab as check_ab

def compact(asset,selection):
    lookup={x['id']:x for x in asset['raw']+asset['summaries']}
    codes={};imports={};summaries={};blocks=[]
    for chosen in selection:
        item=lookup[chosen['id']]
        if item['level']==0:
            for uid in item['source_uris']:
                node=asset['nodes'][uid]
                if uid in codes:continue
                content=f"# Code {node['path']}::{node['name']}\n"
                if node['path'] not in imports:
                    if node['imports']:content+=node['imports']+'\n'
                    imports[node['path']]=node['imports']
                content+=node['source'];codes[uid]=node['source'];blocks.append(content)
        else:
            if item['id'] in summaries:continue
            body=item['text'].split('\n',1)[1];summaries[item['id']]=body
            label=('Function summary '+item['id'].split('memory://symbol/',1)[1] if item['level']==1 else
                   'File summary '+item['path'] if item['level']==2 else 'Project summary')
            blocks.append('# '+label+'\n'+body)
    return '\n\n'.join(blocks),{'source':codes,'imports':imports,'summary':summaries}

def main():
    out=exp.OUT;checks=[]
    def check(name,value,detail=None):
        assert value,(name,detail);checks.append({'name':name,'passed':True,'detail':detail})
        print('PASS',name,flush=True)
    exp.validate(out);check('frozen_source_protocol_and_historical_data',True)
    fresh=exp.audit.rows(out/'results.jsonl');dev=exp.audit.rows(out/'results_dev.jsonl');allrows=fresh+dev
    old=exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl');tasks={t['id']:t for t in exp.read(out/'tasks.json')+exp.read(out/'dev_tasks.json')}
    assets=exp.read(out/'assets.json');base=exp.read(out/'base_assets.json');nodes=exp.audit.rows(out/'summary_nodes.jsonl')
    calls=exp.audit.rows(out/'model_calls.jsonl');byid={c['call_id']:c for c in calls}
    check('864_fresh_answers_in_frozen_order',len(fresh)==864 and [{k:r[k] for k in ['task_id','repeat','arm']} for r in fresh]==exp.read(out/'schedule.json'))
    check('96_exact_questions_three_repeats',Counter((r['task_id'],r['arm']) for r in fresh)=={(t['id'],a):3 for t in exp.read(out/'tasks.json') for a in exp.ARMS} and exp.read(out/'tasks.json')==exp.read(exp.large.DEFAULT_OUT/'tasks.json'))
    check('24_development_answers_separate',len(dev)==24 and not ({r['task_id'] for r in dev}&{r['task_id'] for r in fresh}))
    for rep in range(3):
        block=[r for r in fresh if r['repeat']==rep]
        assert set(Counter(tuple(r['arm'] for r in block[i:i+3]) for i in range(0,288,3)).values())=={16}
    check('six_orders_balanced_each_repeat',True)
    check('same_model_and_server_configuration',exp.read(out/'environment.json')['fingerprint']==exp.read(exp.large.DEFAULT_OUT/'environment.json')['fingerprint'])
    check('unique_actual_model_calls',len(byid)==len(calls) and len({r['answer_call']['call_id'] for r in allrows})==888 and all(byid[r['answer_call']['call_id']]==r['answer_call'] for r in allrows))
    check('fixed_parameters_and_no_input_truncation_or_transport_errors',all(c['request']['temperature']==0 and c['request']['seed']==1 and c['request']['cache_prompt'] is False and c['timings'].get('cache_n')==0 and 'error' not in c and not c['truncated'] and c['input_tokens']+c['max_output_tokens']<=8192 and c['max_output_tokens']==(256 if c['purpose'].startswith('build_') else 128 if c['purpose']=='answer' else 32) for c in calls))
    check('limit_detection_uses_both_server_fields',all(c['ok']==(not c['truncated'] and not c['stopped_limit'] and c['stop_type']!='limit') for c in calls))
    check('sequential_calls_and_physical_query_times',all(datetime.fromisoformat(a['ended_at_utc'])<=datetime.fromisoformat(b['started_at_utc']) for a,b in zip(calls,calls[1:])) and all(abs((datetime.fromisoformat(r['ended_at_utc'])-datetime.fromisoformat(r['started_at_utc'])).total_seconds()-r['query_seconds'])<.025 for r in allrows))
    check('summaries_frozen_before_development_and_evaluation',max(c['ended_at_utc'] for c in calls if c['purpose'].startswith('build_'))<min(c['started_at_utc'] for c in calls if c['purpose']=='answer') and exp.v1.sha(out/'assets.json')==exp.read(out/'build_manifest.json')['assets_sha256'])
    for r in allrows:
        grade=check_ab.grade({**r,'selection_valid':True},tasks[r['task_id']])
        assert grade[0]==r['correct'] and check_ab.equal(grade[1],r['parsed_answer']) and grade[2]==r['failure']
    check('independent_typed_json_grading',True)
    gold=exp.large.ab.verify_gold(out,exp.read(out/'tasks.json'),exp.read(out/'gold_operations.json'))
    check('all_96_gold_answers_reexecuted',gold['questions']==96 and gold['records']==exp.read(out/'gold_recheck.json')['records'])
    strings=set(c['request']['prompt'] for c in calls)
    for project,asset in assets.items():
        assert {k:asset[k] for k in base[project]}==base[project]
        assert independent.source_graph(out/'projects'/project)==asset['nodes']
        assert independent.raw_from_nodes(asset['nodes'])==asset['raw']
        lookup={i['id']:i for i in asset['raw']};leaves=[]
        for s in asset['summaries']:
            call=byid[s['call_id']];children=[lookup[k] for k in s['children']]
            prompt=independent.leaf_prompt(children[0]['text']) if s['level']==1 else independent.group_prompt(children)
            assert call['prompt']==prompt and call['request']['prompt']==independent.wrap(prompt)
            assert call['meta']=={'project':project,'node':s['id']}
            assert s['text']=='### '+s['id']+'\n'+call['answer'] and s['generation_ok']==call['ok']
            assert s['source_uris']==sorted({u for c in children for u in c['source_uris']})
            if s['level']==1:leaves.extend(s['children'])
            lookup[s['id']]=s
        assert set(leaves)=={x['id'] for x in asset['raw'] if x['kind']=='function'} and len(leaves)==len(set(leaves))
        def descendants(s):
            if s['level']==1:return {s['id']}
            return set().union(*(descendants(lookup[c]) for c in s['children']))
        roots=[s for s in asset['summaries'] if s['level']==3]
        assert len(roots)==1 and descendants(roots[0])=={s['id'] for s in asset['summaries'] if s['level']==1}
        for path in {s['path'] for s in asset['summaries'] if s['level']==1}:
            s=lookup['summary:level2:'+path]
            assert descendants(s)=={c['id'] for c in asset['summaries'] if c['level']==1 and c['path']==path}
    check('complete_question_blind_summary_hierarchy_exact_prompts',len(nodes)==sum(len(a['summaries']) for a in assets.values()))
    orders={};local_strings={}
    for r in allrows:
        key=(r['task_id'],'RF' if r['arm']=='RF' else 'RH');asset=assets[r['project']];t=tasks[r['task_id']]
        if key not in orders:
            items=asset['raw']+[s for s in asset['summaries'] if key[1]!='RF' or s['level']==1]
            orders[key]=independent.rank(t['question'],asset['raw'],items)
        local={r['answer_call']['request']['prompt']};selected={c['id']:c for c in r['chosen']};text='';seen=set()
        for score,item in orders[key]:
            if item['level']==0 and set(item['source_uris'])<=seen:continue
            candidate=text+('\n\n' if text else '')+item['text'];local.add(candidate)
            if item['id'] in selected:
                text=candidate
                assert math.isclose(score,selected[item['id']]['score'],abs_tol=1e-12)
                if item['level']==0:seen.update(item['source_uris'])
        assert text==r['context_before_compaction']
        if r['arm']=='C':
            content,payload=compact(asset,r['chosen']);assert content==r['context']
            d=exp.audit.digest(payload);assert d==r['compaction']['selected_payload_sha256']==r['compaction']['emitted_payload_sha256']
            local.add(content)
        else:assert text==r['context']
        assert len(local)==r['tokenize_http_calls']
        strings.update(local);strings.add(r['context']);strings.add(text)
        assert r['answer_call']['prompt']==independent.answer_prompt(t['question'],r['context'])
        assert r['answer_call']['request']['prompt']==independent.wrap(r['answer_call']['prompt'])
        required=set(t['required_uris']);assert r['all_raw_evidence']==(required<=seen)
        assert math.isclose(r['raw_evidence_recall'],len(required&seen)/len(required))
    check('independent_tfidf_order_prompts_and_compaction',True)
    texts=sorted(strings);cache=out/'offline_token_counts.json'
    if cache.exists():
        saved=exp.read(cache);assert saved['strings_sha256']==exp.audit.digest(texts);counts=dict(zip(texts,saved['lengths']))
    else:
        counts,meta=independent.tokenize_many(texts,exp.v1.MODEL)
        exp.v1.dump(cache,{'strings_sha256':exp.audit.digest(texts),'lengths':[counts[t] for t in texts],'tokenizer':meta})
    for r in allrows:
        key=(r['task_id'],'RF' if r['arm']=='RF' else 'RH');text='';seen=set();selected=[];rejected=[]
        for score,item in orders[key]:
            if item['level']==0 and set(item['source_uris'])<=seen:continue
            candidate=text+('\n\n' if text else '')+item['text']
            if counts[candidate]<=1024:
                selected.append(item['id']);text=candidate
                if item['level']==0:seen.update(item['source_uris'])
            else:rejected.append(item['id'])
        assert selected==[c['id'] for c in r['chosen']] and rejected==r['rejected']
        assert counts[text]==r['selected_context_tokens']<=1024 and counts[r['context']]==r['context_tokens']
        assert r['input_tokens']==r['answer_call']['input_tokens'] and r['output_tokens']==r['answer_call']['output_tokens']
    check('independent_offline_tokenization_and_1024_token_packing',True,{'distinct_strings':len(texts)})
    check('actual_server_token_counts_match_offline',all(counts[c['request']['prompt']]==c['input_tokens']==c['timings']['prompt_n'] and c['output_tokens']==c['timings']['predicted_n'] for c in calls))
    pairs=defaultdict(dict)
    for r in fresh:pairs[(r['task_id'],r['repeat'])][r['arm']]=r
    check('all_288_RH_C_pairs_same_selected_payload',all(p['RH']['chosen']==p['C']['chosen'] and p['RH']['context']==p['C']['context_before_compaction'] for p in pairs.values()))
    summary=exp.read(out/'summary.json');numeric=0
    def compare(a,b):
        nonlocal numeric
        if isinstance(a,dict):
            for k,v in a.items():compare(v,b[k])
        elif isinstance(a,list):
            assert len(a)==len(b)
            for x,y in zip(a,b):compare(x,y)
        else:
            assert math.isclose(a,b,abs_tol=1e-8,rel_tol=1e-9),(a,b);numeric+=1
    for pop in ['all96','original48','additional48']:
        group=old+fresh if pop=='all96' else [r for r in old+fresh if r['split']==pop]
        for lower,higher in [('A','B'),('R0','RF'),('RH','C'),('FULL','C')]:
            rs=[{**r,'arm':'A' if r['arm']==lower else 'B','selector':r['selector'] or {'timings':{}}} for r in group if r['arm'] in [lower,higher]]
            m=check_ab.independent_stats(rs)
            compare(m['metrics']['A'],summary['populations'][pop]['metrics'][lower]);compare(m['metrics']['B'],summary['populations'][pop]['metrics'][higher])
    for target in summary['comparisons'].values():
        h,b=target['higher'],target['base']
        rs=[{**r,'arm':'A' if r['arm']==b else 'B','selector':r['selector'] or {'timings':{}}} for r in old+fresh if r['arm'] in [h,b]]
        compare(check_ab.independent_stats(rs)['comparison_B_minus_A'],target)
    running=0
    for i,key in enumerate(sorted(summary['comparisons'],key=lambda k:summary['comparisons'][k]['unadjusted_project_signflip_p'])):
        c=summary['comparisons'][key];running=max(running,min(1,(3-i)*c['unadjusted_project_signflip_p']))
        compare(running,c['holm_p_three_quality_contrasts'])
    check('independent_statistics',True,{'numeric_fields':numeric})
    exp.v1.dump(out/'verification.json',{'status':'PASS','completed_at_utc':exp.audit.now(),'checks':checks,
        'fresh_eval_answers':len(fresh),'dev_answers':len(dev),'model_calls':len(calls),'numeric_fields':numeric,
        'summary_sha256':exp.v1.sha(out/'summary.json'),'results_sha256':exp.v1.sha(out/'results.jsonl')})

if __name__=='__main__':main()
