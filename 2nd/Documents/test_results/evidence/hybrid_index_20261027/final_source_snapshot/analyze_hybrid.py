"""Prespecified paired analysis; fresh controls remain separate from history."""
from collections import Counter, defaultdict
from statistics import mean
import itertools, json, sys
sys.dont_write_bytecode = True
import experiment_hybrid as exp
import analyze_v2 as stats


def tokens(rows):
    return {
        'context': mean(r['context_tokens'] for r in rows),
        'index': mean(r['source_index']['tokens'] if r.get('source_index') else 0 for r in rows),
        'selector': mean(r['selector']['input_tokens'] if r['selector'] else 0 for r in rows),
        'answer': mean(r['answer_call']['input_tokens'] for r in rows),
        'total': mean(r['input_tokens'] for r in rows),
        'peak': mean(max(c['input_tokens'] for c in stats.calls(r)) for r in rows),
        'output': mean(r['output_tokens'] for r in rows),
    }


def cost_comparison(rows, base):
    projects = sorted({r['project'] for r in rows}); pairs = []
    for project in projects:
        arms = {a: tokens([r for r in rows if r['project'] == project and r['arm'] == a])
                for a in ['H', base]}
        pairs.append(arms)
    result = {}
    for field in ['total', 'peak', 'context']:
        reductions = []
        for draw in itertools.product(range(len(projects)), repeat=len(projects)):
            h = sum(pairs[i]['H'][field] for i in draw)
            b = sum(pairs[i][base][field] for i in draw)
            reductions.append(100 * (1-h/b))
        result[field] = {
            'reduction_pct': 100*(1-sum(p['H'][field] for p in pairs)/sum(p[base][field] for p in pairs)),
            'ci95_pct': [stats.old_analysis.quantile(reductions, p) for p in [.025, .975]],
        }
    return result


def main():
    out = exp.OUT; exp.validate(out)
    rows = exp.audit.rows(out/'results.jsonl'); dev = exp.audit.rows(out/'results_dev.jsonl')
    assert len(rows) == 864 and len(dev) == 24
    assert [{k:r[k] for k in ['task_id','repeat','arm']} for r in rows] == exp.read(out/'schedule.json')
    calls = exp.audit.rows(out/'model_calls.jsonl')
    historical = exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl')
    historical += exp.audit.rows(exp.v1.DEFAULT_OUT/'raptor_large_20261024/results.jsonl')
    result = {'status':'COMPLETE', 'created_at_utc': exp.audit.now(), 'populations':{},
        'fresh_answers':len(rows), 'development_answers':len(dev), 'new_model_calls':len(calls),
        'comparisons':{}, 'historical':{}, 'history_comparison_is_descriptive':True,
        'inputs':{str(out/n):exp.v1.sha(out/n) for n in ['protocol.json','results.jsonl','model_calls.jsonl','analysis_plan.json']}}
    for split in ['all96','original48','additional48']:
        subset = rows if split == 'all96' else [r for r in rows if r['split'] == split]
        data = {}
        for arm in exp.ARMS:
            rs = [r for r in subset if r['arm'] == arm]; m = stats.metrics(rs)
            m['question_equivalent_correct'] = m['accuracy'] * m['unique_questions']
            m['answer_limit_calls'] = sum(r['answer_call']['stopped_limit'] or r['answer_call']['stop_type']=='limit' for r in rs)
            m['selector_limit_calls'] = sum(bool(r['selector']) and (r['selector']['stopped_limit'] or r['selector']['stop_type']=='limit') for r in rs)
            data[arm] = {'metrics':m, 'tokens':tokens(rs)}
        result['populations'][split] = data
    for base in ['R0','B']:
        c = stats.comparison(rows,'H',base); c['cost'] = cost_comparison(rows,base)
        result['comparisons']['H-'+base] = c
    previous = 0
    for rank,key in enumerate(sorted(result['comparisons'], key=lambda k:result['comparisons'][k]['unadjusted_project_signflip_p'])):
        c = result['comparisons'][key]
        previous = max(previous,min(1,(2-rank)*c['unadjusted_project_signflip_p']))
        c['holm_p_two_quality_contrasts'] = previous
    for arm in ['A','B','R0','RF','RH','C','FULL']:
        rs = [r for r in historical if r['arm']==arm]
        m = stats.metrics(rs);m['question_equivalent_correct']=m['accuracy']*m['unique_questions']
        result['historical'][arm] = {'metrics':m,'tokens':tokens(rs)}
    tasks = {t['id']:t for t in exp.read(out/'tasks.json')}
    hs = [r for r in rows if r['arm']=='H']
    result['hybrid_diagnostics'] = {
        'mean_index_items':mean(len(r['source_index']['items']) for r in hs),
        'mean_index_tokens':mean(r['source_index']['tokens'] for r in hs),
        'mean_requested_symbols':mean(len(r['requested_uris']) for r in hs),
        'mean_delivered_symbols':mean(len(r['chosen']) for r in hs),
        'invalid_selection_calls':sum(not r['selection_valid'] for r in hs),
        'index_required_recall':mean(r['index_required_recall'] for r in hs),
        'index_all_required_calls':sum(r['index_has_all_required'] for r in hs),
        'requested_required_recall':mean(len(set(r['requested_uris'])&set(tasks[r['task_id']]['required_uris']))/len(tasks[r['task_id']]['required_uris']) for r in hs),
        'raw_required_recall':mean(r['raw_evidence_recall'] for r in hs),
        'raw_all_required_calls':sum(r['all_raw_evidence'] for r in hs),
        'source_budget_rejected_calls':sum(bool(r['rejected']) for r in hs),
        'index_budget_rejected_calls':sum(bool(r['source_index']['rejected']) for r in hs),
        'correct_with_all_raw':sum(r['correct'] and r['all_raw_evidence'] for r in hs),
    }
    result['historical_control_reproduction'] = {}
    prior={(r['task_id'],r['repeat'],r['arm']):r for r in historical}
    for arm in ['B','R0']:
        rs=[r for r in rows if r['arm']==arm]
        result['historical_control_reproduction'][arm] = {
            'pairs':len(rs), 'same_context':sum(r['context']==prior[(r['task_id'],r['repeat'],arm)]['context'] for r in rs),
            'same_answer_prompt':sum(r['answer_call']['request']['prompt']==prior[(r['task_id'],r['repeat'],arm)]['answer_call']['request']['prompt'] for r in rs),
            'same_answer':sum(r['answer_call']['answer']==prior[(r['task_id'],r['repeat'],arm)]['answer_call']['answer'] for r in rs),
        }
    first=defaultdict(dict)
    for r in rows:
        if r['repeat']==0:first[r['task_id']][r['arm']]=r
    result['examples']=[]
    for label,pred in [('H_gain_R0',lambda g:g['H']['correct'] and not g['R0']['correct']),
                       ('H_loss_R0',lambda g:not g['H']['correct'] and g['R0']['correct']),
                       ('H_gain_B',lambda g:g['H']['correct'] and not g['B']['correct']),
                       ('H_missing_raw',lambda g:not g['H']['all_raw_evidence'])]:
        choices=[(tid,g) for tid,g in sorted(first.items()) if pred(g)]
        if choices:
            tid,g=choices[0]
            result['examples'].append({'kind':label,'task_id':tid,'question':g['H']['question'],
                'expected':g['H']['expected'],'arms':{a:{k:r[k] for k in ['correct','parsed_answer','context_tokens','input_tokens','raw_evidence_recall','chosen']} for a,r in g.items()},
                'index':g['H']['source_index'],'selector_answer':g['H']['selector']['answer'],
                'requested_uris':g['H']['requested_uris'],'context':g['H']['context']})
    exp.v1.dump(out/'summary.json',result)
    print(json.dumps({a:{'correct':x['metrics']['question_equivalent_correct'],**x['tokens']} for a,x in result['populations']['all96'].items()},indent=2))


if __name__=='__main__': main()
