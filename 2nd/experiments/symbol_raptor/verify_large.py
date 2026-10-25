"""Offline reconstruction of actual large-file inputs, token counts and results."""
from __future__ import annotations
import argparse, ast, json, math, sys
from collections import Counter
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_large as exp
import audit_v2 as independent
import verify_ab as check_ab


def verify(out):
    checks=[]
    def check(name,value,detail=None):
        assert value,(name,detail)
        checks.append({'name':name,'passed':True,'detail':detail})
    exp.validate_frozen(out)
    check('frozen_inputs_code_and_historical_results',True)
    records=exp.audited.rows(out/'results.jsonl');dev=exp.audited.rows(out/'results_dev.jsonl')
    tasks={t['id']:t for t in exp.read(out/'tasks.json')+exp.read(out/'dev_tasks.json')}
    assets=exp.read(out/'assets.json');file_map=exp.read(out/'file_map.json')
    check('1152_ordered_fresh_answers',len(records)==1152 and [{k:r[k] for k in ['task_id','repeat','arm']} for r in records]==exp.read(out/'schedule.json'))
    check('96_same_questions_three_repeats_four_arms',exp.read(out/'tasks.json')==exp.read(exp.ab.DEFAULT_OUT/'tasks.json') and Counter((r['task_id'],r['arm']) for r in records)=={(t['id'],a):3 for t in exp.read(out/'tasks.json') for a in exp.ARMS})
    check('development_separate',len(dev)==32 and not ({r['task_id'] for r in records}&{r['task_id'] for r in dev}))
    for project in {r['project'] for r in records}:
        for repeat in range(3):
            for position in range(4):
                assert Counter(r['arm'] for r in records[position::4] if r['project']==project and r['repeat']==repeat)=={a:4 for a in exp.ARMS}
    check('balanced_interleaved_orders',True)
    check('same_model_binary_settings',exp.read(out/'environment.json')['fingerprint']==exp.read(exp.ab.DEFAULT_OUT/'environment.json')['fingerprint'])
    calls=exp.audited.rows(out/'model_calls.jsonl');byid={c['call_id']:c for c in calls}
    check('1778_actual_unique_calls',len(calls)==len(byid)==1778 and Counter(c['purpose'] for c in calls)=={'answer':1184,'select':592,'warmup':2})
    used=[c for r in records+dev for c in [r['selector'],r['answer_call']] if c]
    check('no_shared_inference_exact_logs',len({c['call_id'] for c in used})==1776 and all(c==byid[c['call_id']] for c in used))
    check('fixed_parameters_no_cache_no_transport_errors',all(c['request']['temperature']==0 and c['request']['seed']==1 and c['request']['cache_prompt'] is False and c['timings'].get('cache_n')==0 and 'error' not in c and c['request']['n_predict']=={'warmup':32,'select':96,'answer':128}[c['purpose']] for c in calls))
    check('no_context_truncation',all(c['input_tokens']+c['max_output_tokens']<=8192 and not c['truncated'] for c in calls))
    check('call_time_nonoverlap',all(datetime.fromisoformat(a['ended_at_utc'])<=datetime.fromisoformat(b['started_at_utc']) for a,b in zip(calls,calls[1:])))
    check('physical_query_times',all(abs((datetime.fromisoformat(r['ended_at_utc'])-datetime.fromisoformat(r['started_at_utc'])).total_seconds()-r['query_seconds'])<.02 and 0<r['pre_answer_seconds']<r['query_seconds'] for r in records+dev))
    for r in records+dev:
        grade=check_ab.grade({**r,'selection_valid':r['selection_valid'] if r['arm'] in ['A','B'] else True},tasks[r['task_id']])
        assert grade[0]==r['correct'] and check_ab.equal(grade[1],r['parsed_answer']) and grade[2]==r['failure']
    check('independent_typed_grading',True)
    gold=exp.ab.verify_gold(out,exp.read(out/'tasks.json'),exp.read(out/'gold_operations.json'))
    check('all_96_gold_answers_reexecuted',gold['questions']==96 and gold['records']==exp.read(out/'gold_recheck.json')['records'])
    old_assets=exp.read(exp.ab.DEFAULT_OUT/'assets.json')
    for project,asset in assets.items():
        assert independent.source_graph(out/'projects'/project)==asset['nodes']
        assert independent.raw_from_nodes(asset['nodes'])==asset['raw']
        for uid,old in old_assets[project]['nodes'].items():
            for key in ['source','imports','deps','refs','kind']:assert old[key]==asset['nodes'][uid][key]
    check('independent_graph_raw_candidates_original_semantics_preserved',True)
    strings=set();ordered_cache={};query_strings={}
    for r in records+dev:
        t=tasks[r['task_id']];asset=assets[r['project']];arm=r['arm']
        c=r['answer_call']
        assert c['prompt']==independent.answer_prompt(t['question'],r['context'])
        assert c['request']['prompt']==independent.wrap(c['prompt'])
        local={c['request']['prompt']};key=(r['task_id'],arm,r['selected_uri'])
        if arm=='FULL':
            assert r['selector'] is None and r['provided_file']==file_map[t['id']]==asset['nodes'][t['target_uri']]['path']
            assert r['context']==(out/'projects'/t['project']/r['provided_file']).read_text()
            assert 4096<=r['context_tokens']<4500
            sources={u for u,n in asset['nodes'].items() if n['path']==r['provided_file']}
            assert r['chosen']==[{'id':'file://'+r['provided_file'],'level':0,'score':None,'source_uris':sorted(sources)}] and not r['rejected']
            local.add(r['context'])
        else:
            if arm in ['A','B']:
                outline=exp.original._candidate_symbol_outline(asset['index'],t['question'],24)
                assert r['selector']['prompt']==exp.original._selector_prompt(t['question'],outline)
                assert r['selector']['request']['prompt']==independent.wrap(r['selector']['prompt'])
                local.add(r['selector']['request']['prompt'])
                if key not in ordered_cache:
                    order,selected,valid=(exp.audited.baseline_ordered(asset,out/'projects'/t['project'],{'question':t['question']},r['selector']) if arm=='A' else exp.ab.b_ordered(asset,{'question':t['question']},r['selector']))
                    assert selected==r['selected_uri'] and valid==r['selection_valid']
                    ordered_cache[key]=order
            else:
                assert r['selector'] is None
                if key not in ordered_cache:ordered_cache[key]=independent.rank(t['question'],asset['raw'],asset['raw'])
            ordered=ordered_cache[key];selected={c['id']:c for c in r['chosen']}
            text='';sources=set()
            for score,item in ordered:
                if set(item['source_uris'])<=sources:continue
                candidate=text+('\n\n' if text else '')+item['text'];local.add(candidate)
                if item['id'] in selected:
                    assert selected[item['id']]['source_uris']==item['source_uris']
                    assert math.isclose(selected[item['id']]['score'],score,abs_tol=1e-12)
                    text=candidate;sources.update(item['source_uris'])
            assert text==r['context']
        assert len(local)==r['tokenize_http_calls'],(key,len(local),r['tokenize_http_calls'])
        query_strings[(r['task_id'],arm,r['repeat'])]=local
        strings.update(local);strings.add(r['context'])
        required=set(t['required_uris']);target_path=file_map[t['id']]
        assert r['all_raw_evidence']==(required<=sources)
        assert math.isclose(r['raw_evidence_recall'],len(required&sources)/len(required))
        assert r['unique_source_count']==len(sources)
        assert r['source_files']==sorted({asset['nodes'][u]['path'] for u in sources})
        assert r['cross_file_source_count']==sum(asset['nodes'][u]['path']!=target_path for u in sources)
    check('exact_full_files_and_unchanged_prompts_no_gold_in_retrieval',True)
    check('retrieval_reconstruction_and_source_coverage',True)
    text_list=sorted(strings);cache=out/'offline_token_counts.json'
    if cache.exists():
        saved=exp.read(cache);assert saved['strings_sha256']==exp.audited.digest(text_list)
        counts,tokenizer=saved['counts'],saved['tokenizer']
    else:
        counts,tokenizer=independent.tokenize_many(text_list,exp.original.MODEL)
        exp.original.dump(cache,{'strings_sha256':exp.audited.digest(text_list),'counts':counts,'tokenizer':tokenizer})
    for r in records+dev:
        if r['arm']!='FULL':
            key=(r['task_id'],r['arm'],r['selected_uri']);text='';sources=set();chosen=[];rejected=[]
            for score,item in ordered_cache[key]:
                if set(item['source_uris'])<=sources:continue
                candidate=text+('\n\n' if text else '')+item['text']
                if counts[candidate]<=1024:
                    chosen.append({'id':item['id'],'level':0,'score':score,'source_uris':item['source_uris']})
                    text=candidate;sources.update(item['source_uris'])
                else:rejected.append(item['id'])
            assert text==r['context'] and rejected==r['rejected'] and len(chosen)==len(r['chosen'])
            for left,right in zip(chosen,r['chosen']):
                assert {k:v for k,v in left.items() if k!='score'}=={k:v for k,v in right.items() if k!='score'}
                assert math.isclose(left['score'],right['score'],abs_tol=1e-12)
            assert r['context_tokens']<=1024
        assert counts[r['context']]==r['context_tokens']
        query_calls=[c for c in [r['selector'],r['answer_call']] if c]
        assert all(counts[c['request']['prompt']]==c['input_tokens']==c['timings']['prompt_n'] for c in query_calls)
        assert r['input_tokens']==sum(c['input_tokens'] for c in query_calls)
        assert r['output_tokens']==sum(c['output_tokens'] for c in query_calls)
    check('independent_offline_tokens_and_greedy_packing',True,{'distinct_strings':len(strings),'tokenizer':tokenizer})
    check('server_token_counts',all(c['input_tokens']==c['timings']['prompt_n'] and c['output_tokens']==c['timings']['predicted_n'] for c in calls))
    summary=exp.read(out/'summary.json');numeric=0
    def compare(a,b):
        nonlocal numeric
        if isinstance(a,dict):
            for key,value in a.items():compare(value,b[key])
        elif isinstance(a,list):
            assert len(a)==len(b)
            for left,right in zip(a,b):compare(left,right)
        else:
            assert math.isclose(a,b,abs_tol=1e-8,rel_tol=1e-9),(a,b)
            numeric+=1
    for pop in ['all96','original48','additional48']:
        group=records if pop=='all96' else [r for r in records if r['split']==pop]
        target=summary['by_population'][pop]
        for lower,higher in [('A','B'),('R0','FULL')]:
            pair=[{**r,'arm':'A' if r['arm']==lower else 'B','selector':r['selector'] or {'timings':{}}} for r in group if r['arm'] in [lower,higher]]
            computed=check_ab.independent_stats(pair)
            compare(computed['metrics']['A'],target['metrics'][lower]);compare(computed['metrics']['B'],target['metrics'][higher])
        for arm in exp.ARMS:
            rs=[r for r in group if r['arm']==arm];n=len(rs);m=target['token_metrics'][arm];full=target['token_metrics']['FULL']
            v={'code_tokens':sum(r['context_tokens'] for r in rs)/n,
               'selector_input_tokens':sum(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs)/n,
               'answer_input_tokens':sum(r['answer_call']['input_tokens'] for r in rs)/n,
               'total_input_tokens':sum(r['input_tokens'] for r in rs)/n,
               'peak_call_input_tokens':sum(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs)/n,
               'output_tokens':sum(r['output_tokens'] for r in rs)/n}
            compare(v,m)
            compare(100*(v['code_tokens']/full['code_tokens']-1),m['code_change_vs_full_pct'])
            compare(100*(v['total_input_tokens']/full['total_input_tokens']-1),m['total_input_change_vs_full_pct'])
            compare(100*(v['peak_call_input_tokens']/full['peak_call_input_tokens']-1),m['peak_input_change_vs_full_pct'])
            compare(100*v['peak_call_input_tokens']/8192,m['input_window_pct'])
    for key,target in summary['comparisons'].items():
        higher,lower=target['higher'],target['base']
        pair=[{**r,'arm':'A' if r['arm']==lower else 'B','selector':r['selector'] or {'timings':{}}} for r in records if r['arm'] in [lower,higher]]
        compare(check_ab.independent_stats(pair)['comparison_B_minus_A'],target)
    running=0
    for i,key in enumerate(sorted(summary['comparisons'],key=lambda k:summary['comparisons'][k]['unadjusted_project_signflip_p'])):
        target=summary['comparisons'][key];running=max(running,min(1,(6-i)*target['unadjusted_project_signflip_p']))
        compare(running,target['holm_p_six_quality_contrasts'])
    check('independent_primary_metrics_tokens_and_six_contrasts',True,{'numeric_fields':numeric})
    check('historical_small_results_preserved',summary['historical_small']==exp.read(exp.small.DEFAULT_OUT/'summary.json')['by_population']['all96'])
    for arm in exp.ARMS:
        old=summary['historical_small']['metrics'][arm];new=summary['by_population']['all96']['metrics'][arm];change=summary['small_to_large'][arm]
        compare(100*(new['accuracy']-old['accuracy']),change['accuracy_delta_pp'])
        compare(new['mean_context_tokens']/old['mean_context_tokens'],change['code_ratio'])
        compare(new['mean_input_tokens']/old['mean_input_tokens'],change['total_input_ratio'])
    check('small_to_large_descriptive_differences',True)
    exp.original.dump(out/'verification.json',{'status':'PASS','checked_at_utc':exp.audited.now(),'count':len(checks),'checks':checks,
        'evaluation_answers':len(records),'model_calls':len(calls),'generation_limit_calls':sum(not c['ok'] for c in calls),
        'source_hashes':{p.name:exp.original.sha(p) for p in [Path(__file__),out/'results.jsonl',out/'summary.json']},
        'limits':['Local consistency verification, not external certification.','Synthetic distractor growth; original functions remain short.','Large arms interleaved, historical small measured earlier.','FULL knows defining file; retrieval arms have 1024-token selected-code caps.']})
    print(json.dumps({'status':'PASS','checks':len(checks),'numeric_fields':numeric,'actual_answers':len(records)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=exp.DEFAULT_OUT);verify(p.parse_args().out)
