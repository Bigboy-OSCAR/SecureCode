"""Four actual experimental arms, preserving previous A/B/R0 observations."""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
from statistics import mean,median
import json
import sys
sys.dont_write_bytecode=True
import experiment_full as exp
import analyze_r0
import analyze_v2 as stats


def run(out):
    exp.validate_frozen(out)
    fresh=exp.audited.rows(out/'results.jsonl')
    old=exp.audited.rows(exp.ab.DEFAULT_OUT/'results.jsonl')+exp.audited.rows(exp.r0.DEFAULT_OUT/'results.jsonl')
    assert len(fresh)==288 and len(old)==864
    assert [{k:r[k] for k in ['task_id','arm','repeat']} for r in fresh]==exp.read(out/'schedule.json')
    previous=exp.read(exp.r0.DEFAULT_OUT/'summary.json')
    summary={'status':'COMPLETE','created_at_utc':exp.audited.now(),'unique_questions':96,'repeats':3,
        'arms':['A','B','R0','FULL'],'new_actual_answers':288,'preserved_actual_answers':864,'total_actual_answers':1152,
        'whole_file_condition':'Target file provided in advance; no discovery, no cross-file expansion; entire file actually sent to model',
        'latency_limitation':'Separate FULL session; differences from old arms are descriptive, not controlled causal speed effects',
        'by_population':{},'inputs':{str(p):exp.original.sha(p) for p in [out/'results.jsonl',out/'protocol.json',out/'environment.json',exp.r0.DEFAULT_OUT/'summary.json']}}
    records=old+fresh
    for pop in ['all96','original48','additional48']:
        group=records if pop=='all96' else [r for r in records if r['split']==pop]
        oldpop=previous['by_population'][pop]
        ms={**oldpop['metrics'],'FULL':analyze_r0.metrics([r for r in group if r['arm']=='FULL'])}
        comparisons={**oldpop['comparisons'],**{f'FULL-{arm}':stats.comparison(group,'FULL',arm) for arm in ['A','B','R0']}}
        running=0
        for i,key in enumerate(sorted(['FULL-A','FULL-B','FULL-R0'],key=lambda k:comparisons[k]['unadjusted_project_signflip_p'])):
            running=max(running,min(1,(3-i)*comparisons[key]['unadjusted_project_signflip_p']))
            comparisons[key]['holm_p_three_new_quality_contrasts']=running
            comparisons[key]['latency_interpretation']='Different sessions; conditional intervals omit session drift'
        token_metrics={}
        for arm in ['A','B','R0','FULL']:
            rs=[r for r in group if r['arm']==arm]
            token_metrics[arm]={
                'code_tokens':mean(r['context_tokens'] for r in rs),
                'selector_input_tokens':mean(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs),
                'answer_input_tokens':mean(r['answer_call']['input_tokens'] for r in rs),
                'total_input_tokens':mean(r['input_tokens'] for r in rs),
                'peak_call_input_tokens':mean(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs),
                'output_tokens':mean(r['output_tokens'] for r in rs),
            }
        for arm,m in token_metrics.items():
            m['code_change_vs_full_pct']=100*(m['code_tokens']/token_metrics['FULL']['code_tokens']-1)
            m['total_input_change_vs_full_pct']=100*(m['total_input_tokens']/token_metrics['FULL']['total_input_tokens']-1)
            m['peak_input_change_vs_full_pct']=100*(m['peak_call_input_tokens']/token_metrics['FULL']['peak_call_input_tokens']-1)
            m['input_window_pct']=100*m['peak_call_input_tokens']/8192
        summary['by_population'][pop]={'questions':oldpop['questions'],'metrics':ms,'comparisons':comparisons,'token_metrics':token_metrics}
    groups=defaultdict(lambda:defaultdict(list))
    for r in records:groups[r['task_id']][r['arm']].append(r)
    summary['questions']=[]
    for tid,arms in sorted(groups.items()):
        q={k:arms['FULL'][0][k] for k in ['task_id','project','category','question','expected','provided_file']}
        q['arms']={arm:{'score':mean(r['correct'] for r in rows),'seconds':median(r['query_seconds'] for r in rows),
            'answer':rows[0]['parsed_answer'],'context_tokens':rows[0]['context_tokens'],'source_files':rows[0]['source_files'],
            'sources':sorted({u for c in rows[0]['chosen'] for u in c['source_uris']})} for arm,rows in arms.items()}
        summary['questions'].append(q)
    exp.original.dump(out/'summary.json',summary)
    print(json.dumps(summary['by_population']['all96'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=exp.DEFAULT_OUT);run(p.parse_args().out)
