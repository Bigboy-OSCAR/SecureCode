"""Verify actual whole-file requests, outputs, time records, tokens and statistics."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import math
import sys
sys.dont_write_bytecode=True
import experiment_full as exp
import audit_v2 as independent
import verify_ab as prior_check


def run(out):
    checks=[]
    def check(name,ok,detail=None):
        assert ok,(name,detail)
        checks.append({'name':name,'passed':True,'detail':detail})
    exp.validate_frozen(out)
    check('frozen_inputs_code_and_prior_results',True)
    records,dev=exp.audited.rows(out/'results.jsonl'),exp.audited.rows(out/'results_dev.jsonl')
    tasks={t['id']:t for t in exp.read(out/'tasks.json')+exp.read(out/'dev_tasks.json')}
    check('288_ordered_fresh_actual_answers',len(records)==288 and [{k:r[k] for k in ['task_id','arm','repeat']} for r in records]==exp.read(out/'schedule.json'))
    check('same_96_questions_three_repeats',exp.read(out/'tasks.json')==exp.read(exp.r0.DEFAULT_OUT/'tasks.json') and
        Counter(r['task_id'] for r in records)=={t['id']:3 for t in exp.read(out/'tasks.json')})
    check('development_separate',len(dev)==8 and not ({r['task_id'] for r in dev}&{r['task_id'] for r in records}))
    check('same_model_binary_and_settings',exp.read(out/'environment.json')['fingerprint']==exp.read(exp.ab.DEFAULT_OUT/'environment.json')['fingerprint'])
    calls=exp.audited.rows(out/'model_calls.jsonl');byid={c['call_id']:c for c in calls}
    check('actual_calls_no_reused_answers',len(byid)==len(calls)==298 and Counter(c['purpose'] for c in calls)=={'answer':296,'warmup':2} and len({r['answer_call']['call_id'] for r in records+dev})==296)
    check('matching_request_response_logs',all(r['answer_call']==byid[r['answer_call']['call_id']] and r['selector'] is None for r in records+dev))
    check('fixed_parameters_and_no_cache',all(c['request']['temperature']==0 and c['request']['seed']==1 and c['request']['cache_prompt'] is False and c['timings'].get('cache_n')==0 and c['request']['n_predict']==(32 if c['purpose']=='warmup' else 128) for c in calls))
    check('no_transport_errors',all('error' not in c for c in calls))
    check('call_time_nonoverlap',all(datetime.fromisoformat(a['ended_at_utc'])<=datetime.fromisoformat(b['started_at_utc']) for a,b in zip(calls,calls[1:])))
    check('query_time_consistency',all(abs((datetime.fromisoformat(r['ended_at_utc'])-datetime.fromisoformat(r['started_at_utc'])).total_seconds()-r['query_seconds'])<.02 and 0<r['retrieval_seconds']+r['packing_seconds']<=r['pre_answer_seconds']<r['query_seconds'] for r in records+dev))
    check('independent_exact_grading',all((lambda g:g[0]==r['correct'] and prior_check.equal(g[1],r['parsed_answer']) and g[2]==r['failure'])(prior_check.grade({**r,'selection_valid':True},tasks[r['task_id']])) for r in records+dev))
    check('gold_reexecuted_and_preserved',exp.read(out/'gold_recheck.json')['status']=='PASS' and exp.read(out/'gold_recheck.json')['questions']==96 and all(prior_check.equal(r['expected'],tasks[r['task_id']]['expected']) for r in records+dev))
    nodes={p:independent.source_graph(out/'projects'/p) for p in {t['project'] for t in tasks.values()}}
    check('independent_source_graph',nodes==exp.read(out/'nodes.json'))
    strings=set();file_map=exp.read(out/'file_map.json')
    token_reference=exp.read(exp.original.DEFAULT_OUT/'file_tokens_20261024/summary.json')
    old_tokens={q['task_id']:q['whole_file'] for q in token_reference['questions']}
    for r in records+dev:
        task=tasks[r['task_id']]
        path=nodes[r['project']][task['target_uri']]['path']
        assert path==r['provided_file']==file_map[r['task_id']]
        source=(out/'projects'/r['project']/path).read_text()
        assert source==r['context']
        call=r['answer_call']
        assert call['prompt']==independent.answer_prompt(task['question'],source)
        assert call['request']['prompt']==independent.wrap(call['prompt'])
        assert r['tokenize_http_calls']==2
        strings.update([source,call['request']['prompt']])
        included={u for u,n in nodes[r['project']].items() if n['path']==path}
        assert len(r['chosen'])==1 and set(r['chosen'][0]['source_uris'])==included
        required=set(task['required_uris'])
        assert r['all_raw_evidence']==(required<=included)
        assert math.isclose(r['raw_evidence_recall'],len(included&required)/len(required))
        assert r['unique_source_count']==len(included) and r['cross_file_source_count']==0 and r['source_files']==[path]
        assert r['context_tokens']<=1024 and call['input_tokens']+128<=8192 and r['rejected']==[]
        if r['task_id'] in old_tokens:
            assert old_tokens[r['task_id']]['code_tokens']==r['context_tokens']
            assert old_tokens[r['task_id']]['total_input_tokens']==r['input_tokens']
    check('exact_entire_file_sent_no_truncation_or_extra_files',True)
    check('same_prompts_file_mapping_and_source_coverage',True)
    check('actual_tokens_match_prior_count_only_reference',True)
    counts,tokenizer=independent.tokenize_many(sorted(strings),exp.original.MODEL)
    exp.original.dump(out/'offline_token_counts.json',{'counts':counts,'tokenizer':tokenizer})
    check('offline_tokens_equal_actual_server_requests',all(counts[r['context']]==r['context_tokens'] and counts[r['answer_call']['request']['prompt']]==r['input_tokens']==r['answer_call']['input_tokens']==r['answer_call']['timings']['prompt_n'] and r['output_tokens']==r['answer_call']['output_tokens']==r['answer_call']['timings']['predicted_n'] for r in records+dev),{'strings':len(strings),'tokenizer':tokenizer})
    summary=exp.read(out/'summary.json')
    previous=exp.read(exp.r0.DEFAULT_OUT/'summary.json')
    old=exp.audited.rows(exp.ab.DEFAULT_OUT/'results.jsonl')+exp.audited.rows(exp.r0.DEFAULT_OUT/'results.jsonl')
    number_checks=0
    def compare(a,b):
        nonlocal number_checks
        if isinstance(a,dict):
            for key,value in a.items():compare(value,b[key])
        elif isinstance(a,list):
            assert len(a)==len(b)
            for x,y in zip(a,b):compare(x,y)
        else:
            assert math.isclose(a,b,abs_tol=1e-9,rel_tol=1e-9),(a,b)
            number_checks+=1
    for pop in ['all96','original48','additional48']:
        target=summary['by_population'][pop]
        assert all(target['metrics'][a]==previous['by_population'][pop]['metrics'][a] for a in ['A','B','R0'])
        assert all(target['comparisons'][key]==c for key,c in previous['by_population'][pop]['comparisons'].items())
        group=[r for r in old+records if pop=='all96' or r['split']==pop]
        for base in ['A','B','R0']:
            pair=[{**r,'arm':'B' if r['arm']=='FULL' else 'A','selector':r['selector'] or {'timings':{}}} for r in group if r['arm'] in [base,'FULL']]
            computed=prior_check.independent_stats(pair)
            compare(computed['metrics']['A'],target['metrics'][base])
            compare(computed['metrics']['B'],target['metrics']['FULL'])
            compare(computed['comparison_B_minus_A'],target['comparisons'][f'FULL-{base}'])
        running=0
        for i,key in enumerate(sorted(['FULL-A','FULL-B','FULL-R0'],key=lambda k:target['comparisons'][k]['unadjusted_project_signflip_p'])):
            running=max(running,min(1,(3-i)*target['comparisons'][key]['unadjusted_project_signflip_p']))
            compare(running,target['comparisons'][key]['holm_p_three_new_quality_contrasts'])
        for arm in ['A','B','R0','FULL']:
            rs=[r for r in group if r['arm']==arm]
            n=len(rs)
            m=target['token_metrics'][arm]
            values={'code_tokens':sum(r['context_tokens'] for r in rs)/n,
                    'selector_input_tokens':sum(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs)/n,
                    'answer_input_tokens':sum(r['answer_call']['input_tokens'] for r in rs)/n,
                    'total_input_tokens':sum(r['input_tokens'] for r in rs)/n,
                    'peak_call_input_tokens':sum(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs)/n,
                    'output_tokens':sum(r['output_tokens'] for r in rs)/n}
            compare(values,m)
            f=target['token_metrics']['FULL']
            compare(100*(values['code_tokens']/f['code_tokens']-1),m['code_change_vs_full_pct'])
            compare(100*(values['total_input_tokens']/f['total_input_tokens']-1),m['total_input_change_vs_full_pct'])
            compare(100*(values['peak_call_input_tokens']/f['peak_call_input_tokens']-1),m['peak_input_change_vs_full_pct'])
            compare(100*values['peak_call_input_tokens']/8192,m['input_window_pct'])
    check('prior_AB_R0_results_preserved',True)
    check('independent_statistics_and_input_accounting',True,{'numeric_fields':number_checks})
    exp.original.dump(out/'verification.json',{'status':'PASS','checked_at_utc':exp.audited.now(),'count':len(checks),'checks':checks,
        'actual_eval_answers':len(records),'model_calls':len(calls),'generation_limit_calls':sum(not c['ok'] for c in calls),
        'source_hashes':{p.name:exp.original.sha(p) for p in [Path(__file__),out/'results.jsonl',out/'summary.json']},
        'limits':['Whole-file reader receives target file path in advance; no file discovery measured.','Separate execution session; timing not a controlled causal contrast.','Local consistency review, not external certification.']})
    print(json.dumps({'status':'PASS','checks':len(checks),'numeric_fields':number_checks}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=exp.DEFAULT_OUT);run(p.parse_args().out)
