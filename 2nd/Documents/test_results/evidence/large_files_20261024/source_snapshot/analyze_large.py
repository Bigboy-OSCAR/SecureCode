"""Summarize the prespecified four-arm large-file experiment."""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
sys.dont_write_bytecode=True
import experiment_large as exp
import analyze_ab, analyze_r0, analyze_v2

CONTRASTS=[('B','A'),('R0','A'),('R0','B'),('A','FULL'),('B','FULL'),('R0','FULL')]


def summarize(rows):
    metrics={}
    tokens={}
    for arm in exp.ARMS:
        rs=[r for r in rows if r['arm']==arm]
        m=(analyze_ab.metrics(rs) if arm in ['A','B'] else analyze_r0.metrics(rs))
        m['mean_retrieval_seconds']=mean(r['retrieval_seconds'] for r in rs)
        m['mean_select_seconds']=mean(r['select_seconds'] for r in rs)
        m['mean_expansion_seconds']=mean(r['expansion_seconds'] for r in rs)
        metrics[arm]=m
        tokens[arm]={
            'code_tokens':mean(r['context_tokens'] for r in rs),
            'selector_input_tokens':mean(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs),
            'answer_input_tokens':mean(r['answer_call']['input_tokens'] for r in rs),
            'total_input_tokens':mean(r['input_tokens'] for r in rs),
            'peak_call_input_tokens':mean(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs),
            'output_tokens':mean(r['output_tokens'] for r in rs),
        }
    full=tokens['FULL']
    for arm,t in tokens.items():
        t['code_change_vs_full_pct']=100*(t['code_tokens']/full['code_tokens']-1)
        t['total_input_change_vs_full_pct']=100*(t['total_input_tokens']/full['total_input_tokens']-1)
        t['peak_input_change_vs_full_pct']=100*(t['peak_call_input_tokens']/full['peak_call_input_tokens']-1)
        t['input_window_pct']=100*t['peak_call_input_tokens']/8192
    return {'questions':len({r['task_id'] for r in rows}),'metrics':metrics,'token_metrics':tokens}


def analyze(out):
    exp.validate_frozen(out)
    rows=exp.audited.rows(out/'results.jsonl')
    assert len(rows)==1152
    assert [{k:r[k] for k in ['task_id','repeat','arm']} for r in rows]==exp.read(out/'schedule.json')
    old=exp.read(exp.small.DEFAULT_OUT/'summary.json')
    result={'status':'COMPLETE','created_at_utc':exp.audited.now(),'unique_questions':96,'repeats':3,
        'evaluation_answers':1152,'historical_small_actual_answers':1152,'arms':exp.ARMS,
        'by_population':{},'comparisons':{},'historical_small':old['by_population']['all96'],
        'small_to_large':{},'corpus':exp.read(out/'corpus_manifest.json'),
        'inputs':{str(p):exp.original.sha(p) for p in [out/'results.jsonl',out/'protocol.json',out/'environment.json',exp.small.DEFAULT_OUT/'summary.json']}}
    for population in ['all96','original48','additional48']:
        group=rows if population=='all96' else [r for r in rows if r['split']==population]
        result['by_population'][population]=summarize(group)
    for higher,base in CONTRASTS:
        result['comparisons'][higher+'-'+base]=analyze_v2.comparison(rows,higher,base)
    running=0
    for i,key in enumerate(sorted(result['comparisons'],key=lambda k:result['comparisons'][k]['unadjusted_project_signflip_p'])):
        running=max(running,min(1,(6-i)*result['comparisons'][key]['unadjusted_project_signflip_p']))
        result['comparisons'][key]['holm_p_six_quality_contrasts']=running
    for arm in exp.ARMS:
        new=result['by_population']['all96']['metrics'][arm];previous=old['by_population']['all96']['metrics'][arm]
        result['small_to_large'][arm]={
            'accuracy_delta_pp':100*(new['accuracy']-previous['accuracy']),
            'code_ratio':new['mean_context_tokens']/previous['mean_context_tokens'],
            'total_input_ratio':new['mean_input_tokens']/previous['mean_input_tokens'],
            'latency_ratio_descriptive':new['mean_query_seconds']/previous['mean_query_seconds'],
            'interpretation':'Historical small and fresh large data are different sessions; file size, extra distractors and candidate counts change together.'}
    grouped=defaultdict(lambda:defaultdict(list))
    for r in rows:grouped[r['task_id']][r['arm']].append(r)
    result['questions']=[]
    for tid,arms in sorted(grouped.items()):
        first=arms['FULL'][0]
        q={k:first[k] for k in ['task_id','project','category','question','expected','provided_file']}
        q['arms']={}
        for arm,rs in arms.items():
            r=next(r for r in rs if r['repeat']==0)
            q['arms'][arm]={'score':mean(r['correct'] for r in rs),'seconds':median(r['query_seconds'] for r in rs),
                'answer':r['parsed_answer'],'context_tokens':r['context_tokens'],'input_tokens':r['input_tokens'],
                'selected_uri':r['selected_uri'],'source_files':r['source_files'],'sources':sorted({u for c in r['chosen'] for u in c['source_uris']})}
        result['questions'].append(q)
    result['order_diagnostics']={arm:{str(pos+1):{'n':sum(r['arm']==arm for r in rows[pos::4]),
        'mean_seconds':mean(r['query_seconds'] for r in rows[pos::4] if r['arm']==arm)} for pos in range(4)} for arm in exp.ARMS}
    pairs=defaultdict(dict)
    for r in rows:pairs[(r['task_id'],r['repeat'])][r['arm']]=r
    result['selector_diagnostics']={'same_A_B_selected_uri_pairs':sum(g['A']['selected_uri']==g['B']['selected_uri'] for g in pairs.values()),
        'pairs':len(pairs),'note':'A and B selector calls are separately generated, not shared.'}
    exp.original.dump(out/'summary.json',result)
    print(json.dumps({arm:{k:m[k] for k in ['accuracy','mean_query_seconds','mean_context_tokens','mean_input_tokens','raw_evidence_recall','different_output_questions']} for arm,m in result['by_population']['all96']['metrics'].items()},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=exp.DEFAULT_OUT);analyze(p.parse_args().out)
