"""Prespecified analysis of fresh RF/RH/C and preserved large controls."""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from statistics import mean, median
sys.dont_write_bytecode=True
import experiment_raptor_large as exp
import analyze_v2 as stats
import analyze_r0, analyze_ab

ALL_ARMS=['A','B','R0','RF','RH','C','FULL']
CONTRASTS=[('RF','R0'),('RH','RF'),('C','RH')]

def population(rows):
    metrics={};tokens={}
    for arm in ALL_ARMS:
        rs=[r for r in rows if r['arm']==arm]
        m=analyze_ab.metrics(rs) if arm in ['A','B'] else analyze_r0.metrics(rs)
        m['question_equivalent_correct']=m['accuracy']*m['unique_questions']
        m['output_limit_calls']=sum(r['answer_call']['stop_type']=='limit' or r['answer_call']['stopped_limit'] for r in rs)
        m['selected_levels']=dict(Counter(str(c['level']) for r in rs for c in r['chosen']))
        m['questions_with_summary']=len({r['task_id'] for r in rs if any(c['level']>0 for c in r['chosen'])})
        m['questions_with_higher_summary']=len({r['task_id'] for r in rs if any(c['level']>1 for c in r['chosen'])})
        metrics[arm]=m
        tokens[arm]={'context':mean(r['context_tokens'] for r in rs),
            'selected_before_compaction':mean(r['selected_context_tokens'] for r in rs),
            'selector':mean(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs),
            'answer':mean(r['answer_call']['input_tokens'] for r in rs),
            'total':mean(r['input_tokens'] for r in rs),
            'peak':mean(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs)}
    for t in tokens.values():
        t['saving_total_vs_full_pct']=100*(1-t['total']/tokens['FULL']['total'])
        t['saving_context_vs_full_pct']=100*(1-t['context']/tokens['FULL']['context'])
        t['window_pct']=100*t['peak']/8192
    return {'questions':len({r['task_id'] for r in rows}),'metrics':metrics,'tokens':tokens}

def main():
    out=exp.OUT;exp.validate(out)
    fresh=exp.audit.rows(out/'results.jsonl');old=exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl')
    assert len(fresh)==864 and len(old)==1152
    rows=old+fresh;calls=exp.audit.rows(out/'model_calls.jsonl');assets=exp.read(out/'assets.json')
    result={'status':'COMPLETE','created_at_utc':exp.audit.now(),'fresh_answers':864,'preserved_answers':1152,
        'unique_questions':96,'repeats':3,'arms':ALL_ARMS,'populations':{},'comparisons':{},
        'inputs':{str(p):exp.v1.sha(p) for p in [out/'protocol.json',out/'assets.json',out/'results.jsonl',exp.large.DEFAULT_OUT/'results.jsonl']}}
    for pop in ['all96','original48','additional48']:
        rs=rows if pop=='all96' else [r for r in rows if r['split']==pop]
        result['populations'][pop]=population(rs)
    for h,b in CONTRASTS:
        c=stats.comparison(rows,h,b)
        c['latency_interpretation']='same interleaved session' if b in exp.ARMS else 'separate historical session; descriptive'
        result['comparisons'][h+'-'+b]=c
    running=0
    for i,key in enumerate(sorted(result['comparisons'],key=lambda k:result['comparisons'][k]['unadjusted_project_signflip_p'])):
        c=result['comparisons'][key];running=max(running,min(1,(3-i)*c['unadjusted_project_signflip_p']))
        c['holm_p_three_quality_contrasts']=running
    grouped=defaultdict(dict)
    for r in rows:
        if r['repeat']==0:grouped[r['task_id']][r['arm']]=r
    result['questions']=[]
    for tid,g in sorted(grouped.items()):
        row={k:g['A'][k] for k in ['task_id','project','category','split','question','expected']}
        row['arms']={a:{k:g[a][k] for k in ['correct','parsed_answer','failure','context_tokens','input_tokens','chosen','raw_evidence_recall']} for a in ALL_ARMS}
        result['questions'].append(row)
    pairs=defaultdict(dict)
    for r in fresh:pairs[(r['task_id'],r['repeat'])][r['arm']]=r
    result['compaction']={
        'pairs':len(pairs),'same_RH_C_selection':sum(p['RH']['chosen']==p['C']['chosen'] and p['RH']['context']==p['C']['context_before_compaction'] for p in pairs.values()),
        'payload_preserved_calls':sum(p['C']['compaction']['payload_preserved'] for p in pairs.values()),
        'context_reduction_pct':100*(1-result['populations']['all96']['tokens']['C']['context']/result['populations']['all96']['tokens']['RH']['context']),
        'input_reduction_pct':100*(1-result['populations']['all96']['tokens']['C']['total']/result['populations']['all96']['tokens']['RH']['total'])}
    projects={t['project'] for t in exp.read(out/'tasks.json')}
    result['build']={}
    for split,ps in [('evaluation',projects),('development',set(assets)-projects),('all',set(assets))]:
        cs=[c for c in calls if c['purpose'].startswith('build_') and c['meta']['project'] in ps]
        result['build'][split]={'projects':len(ps),'summary_calls':len(cs),'input_tokens':sum(c['input_tokens'] for c in cs),
            'output_tokens':sum(c['output_tokens'] for c in cs),'model_wall_seconds':sum(c['wall_seconds'] for c in cs),
            'output_limit_calls':sum(c['stop_type']=='limit' or c['stopped_limit'] for c in cs),
            'by_purpose':{p:{'calls':sum(c['purpose']==p for c in cs),'input_tokens':sum(c['input_tokens'] for c in cs if c['purpose']==p),
                'output_tokens':sum(c['output_tokens'] for c in cs if c['purpose']==p),'model_wall_seconds':sum(c['wall_seconds'] for c in cs if c['purpose']==p)} for p in sorted({c['purpose'] for c in cs})},
            'levels':dict(Counter(str(s['level']) for p in ps for s in assets[p]['summaries']))}
    result['build']['note']='RF needs leaf summaries only; RH/C share those and all higher summaries. These one-time costs are excluded from per-query inputs and times.'
    original=exp.audit.rows(exp.v1.DEFAULT_OUT/'results_eval_main.jsonl')
    revision_new=exp.audit.rows(exp.v1.DEFAULT_OUT/'revision_v2/results_new.jsonl')
    revision_old=exp.audit.rows(exp.v1.DEFAULT_OUT/'revision_v2/results_old.jsonl')
    result['historical_matched_questions']={}
    for pop,source,arms in [('original48',original,['A','B','R0','RF','RH']),('additional48',revision_new,['A','RH','C']),('original48_C',revision_old,['C'])]:
        data={}
        for arm in arms:
            rs=[r for r in source if r['arm']==arm];now=[r for r in rows if r['arm']==arm and r['split']==pop.replace('_C','')]
            assert {r['task_id'] for r in rs}=={r['task_id'] for r in now}
            assert all(exp.audit.digest(r['expected'])==exp.audit.digest(next(n['expected'] for n in now if n['task_id']==r['task_id'])) for r in rs)
            data[arm]={'old_correct':mean(r['correct'] for r in rs)*48,'large_correct':mean(r['correct'] for r in now)*48,
                'old_repeats':len(rs)//48,'old_records':len(rs),'large_records':len(now)}
        result['historical_matched_questions'][pop]=data
    result['repeat_stability']={a:{'different_raw_output_questions':sum(len({r['answer_call']['answer'] for r in fresh if r['arm']==a and r['task_id']==tid})>1 for tid in grouped)} for a in exp.ARMS}
    exp.v1.dump(out/'summary.json',result)
    print(json.dumps({a:{k:m[k] for k in ['question_equivalent_correct','accuracy','mean_query_seconds','mean_context_tokens','mean_input_tokens','output_limit_calls']} for a,m in result['populations']['all96']['metrics'].items()},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
