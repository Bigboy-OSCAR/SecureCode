"""Post-hoc construction and error diagnostics; no model calls or new scoring rules."""
from __future__ import annotations
import json, sys
from collections import Counter, deque
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_raptor_large as exp

REV=exp.OUT/'revisions/methods_and_interpretation_20261025'
ARMS=['A','B','R0','RF','RH','C','FULL']

def main():
    exp.validate(exp.OUT);exp.large.validate_frozen(exp.large.DEFAULT_OUT)
    old=exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl')
    fresh=exp.audit.rows(exp.OUT/'results.jsonl');rows=old+fresh
    assert len(old)==1152 and len(fresh)==864
    tasks={t['id']:t for t in exp.read(exp.OUT/'tasks.json')}
    assets=exp.read(exp.OUT/'assets.json');summary=exp.read(exp.OUT/'summary.json')
    grouped={a:{t:[r for r in rows if r['arm']==a and r['task_id']==t] for t in tasks} for a in ARMS}
    for arm,bytask in grouped.items():
        for tid,rs in bytask.items():
            assert len(rs)==3 and {r['repeat'] for r in rs}=={0,1,2}
            for field in ['correct','failure','context','chosen','selection_correct','selected_uri']:
                assert all(exp.audit.digest(r[field])==exp.audit.digest(rs[0][field]) for r in rs), (arm,tid,field)
    first={a:{t:next(r for r in rs if r['repeat']==0) for t,rs in bytask.items()} for a,bytask in grouped.items()}
    facts={'created_at_utc':exp.audit.now(),'analysis_type':'Post-hoc inspection; no new model generation or causal ablation.',
        'questions':96,'actual_existing_answers':len(rows),'repeats_identical_for_report_diagnostics':True,'arms':{},'pairs':{}}
    for arm,bytask in first.items():
        rs=list(bytask.values());leaves=[c for r in rs for c in r['chosen'] if c['level']==1]
        auxiliary=[c for c in leaves if '::aux_' in c['id']]
        errors=Counter(r['failure'] for r in rs if not r['correct'])
        assert sum(r['correct'] for r in rs)+sum(errors.values())==96
        coverage=[];full=[]
        for r in rs:
            required=set(tasks[r['task_id']]['required_uris'])
            actual={u for c in r['chosen'] if c['level']==0 for u in c['source_uris']}
            coverage.append(len(required&actual)/len(required));full.append(required<=actual)
            assert abs(coverage[-1]-r['raw_evidence_recall'])<1e-12 and full[-1]==r['all_raw_evidence']
        m=summary['populations']['all96']['metrics'][arm]
        assert sum(r['correct'] for r in rs)==m['question_equivalent_correct']
        facts['arms'][arm]={
            'correct':sum(r['correct'] for r in rs),'accuracy_pct':100*sum(r['correct'] for r in rs)/96,
            'raw_inclusion_pct':100*sum(coverage)/96,'all_raw_questions':sum(full),
            'correct_with_all_raw':sum(r['correct'] and complete for r,complete in zip(rs,full)),
            'wrong_with_all_raw':sum(not r['correct'] and complete for r,complete in zip(rs,full)),
            'selector_valid':sum(r['selection_valid'] is True for r in rs) if arm in ['A','B'] else None,
            'selector_matches_designated_target':sum(r['selection_correct'] is True for r in rs) if arm in ['A','B'] else None,
            'failures_by_question':dict(errors),
            'output_limit_questions':sum(r['answer_call']['stop_type']=='limit' or r['answer_call']['stopped_limit'] for r in rs),
            'leaf_selections_one_repeat':len(leaves),'auxiliary_leaf_selections_one_repeat':len(auxiliary),
            'auxiliary_leaf_selection_pct':100*len(auxiliary)/len(leaves) if leaves else 0,
            'questions_with_auxiliary_summary':sum(any(c['level']==1 and '::aux_' in c['id'] for c in r['chosen']) for r in rs),
            'questions_with_file_summary':sum(any(c['level']==2 for c in r['chosen']) for r in rs),
            'questions_with_project_summary':sum(any(c['level']==3 for c in r['chosen']) for r in rs),
        }
    assert not any('::aux_' in u for t in tasks.values() for u in t['required_uris'])
    for base,arm in [('A','B'),('R0','RF'),('RF','RH'),('RH','C')]:
        wins=[t for t in tasks if first[arm][t]['correct'] and not first[base][t]['correct']]
        losses=[t for t in tasks if first[base][t]['correct'] and not first[arm][t]['correct']]
        facts['pairs'][base+'->'+arm]={'wins':wins,'losses':losses,'ties':96-len(wins)-len(losses)}
    facts['AB_same_selected_function_questions']=sum(first['A'][t]['selected_uri']==first['B'][t]['selected_uri'] for t in tasks)
    diag={'target_matches':0,'missing_required_before_packing':0,'required_lost_during_packing':0,'eight_function_cap_reached':0}
    distances=Counter()
    for r in first['B'].values():
        if not r['selection_correct']:continue
        nodes=assets[r['project']]['nodes'];members=set(exp.v1.baseline_cross_file_members(nodes,r['selected_uri'],r['question']))
        emitted={u for c in r['chosen'] for u in c['source_uris']};required=set(tasks[r['task_id']]['required_uris'])
        diag['target_matches']+=1
        if required-members:
            diag['missing_required_before_packing']+=1
            queue=deque([r['selected_uri']]);dist={r['selected_uri']:0}
            while queue:
                node=queue.popleft()
                for dep in nodes[node]['deps']:
                    if dep not in dist:dist[dep]=dist[node]+1;queue.append(dep)
            distances.update(str(dist.get(u,'unreachable_from_primary')) for u in required-members)
        diag['required_lost_during_packing']+=bool((required&members)-emitted)
        diag['eight_function_cap_reached']+=sum(nodes[u]['kind']=='function' for u in members)==8
    facts['B_expansion_diagnostic']={**diag,'missing_source_distance_occurrences':dict(distances)}
    lexical={}
    for project in sorted({t['project'] for t in tasks.values()}):
        asset=assets[project];leaves=[s for s in asset['summaries'] if s['level']==1];retriever=exp.v1.Retriever(asset['raw'])
        lexical[project]={'raw_candidates':len(asset['raw']),'leaf_summaries':len(leaves),
            'function_document_frequency_raw':sum('function' in set(exp.v1.words(x['text'])) for x in asset['raw']),
            'function_document_frequency_leaf':sum('function' in set(exp.v1.words(x['text'])) for x in leaves),
            'function_idf':retriever.idf.get('function',retriever.unseen_idf),'unseen_word_idf':retriever.unseen_idf}
    facts['lexical_diagnostic']={'term':'function','idf_fitted_on':'raw candidates only',
        'questions_containing_term':sum('function' in set(exp.v1.words(t['question'])) for t in tasks.values()),'projects':lexical}
    caseids=['eval_authorization__expiry','eval_pricing__v2_negative_unit_price','eval_cache__canonical_key',
             'eval_inventory__v2_order_cap_intervention','eval_authorization__own_write']
    facts['cases']={}
    for tid in caseids:
        case={'question':tasks[tid]['question'],'expected':tasks[tid]['expected'],'arms':{}}
        for arm in ['A','B','R0','RF','RH','C','FULL']:
            r=first[arm][tid];case['arms'][arm]={k:r[k] for k in ['correct','parsed_answer','failure','raw_evidence_recall','all_raw_evidence','chosen']}
        facts['cases'][tid]=case
    facts['preparation']=summary['build']['evaluation']
    facts['compaction']=summary['compaction']
    source_files=[exp.OUT/'results.jsonl',exp.large.DEFAULT_OUT/'results.jsonl',exp.OUT/'tasks.json',exp.OUT/'assets.json',
        exp.OUT/'model_calls.jsonl',exp.OUT/'summary.json',exp.OUT/'verification.json',Path(__file__),
        Path(exp.v1.__file__),Path(exp.audit.__file__),Path(exp.large.__file__),
        Path(__file__).with_name('experiment_ab.py'),Path(exp.__file__),
        exp.v1.REPO/'1st/symbol_test/symbol_bench/indexer.py',exp.v1.REPO/'1st/symbol_test/symbol_bench/run_benchmark.py']
    facts['source_hashes']={str(p.resolve()):exp.v1.sha(p) for p in source_files}
    exp.v1.dump(REV/'mechanism_facts.json',facts)
    print(json.dumps({'status':'PASS','questions':96,'existing_answers':len(rows),'new_model_calls':0,
        'B_expansion_diagnostic':diag,'RF_auxiliary_summary_selection_pct':facts['arms']['RF']['auxiliary_leaf_selection_pct']},ensure_ascii=False))

if __name__=='__main__':main()
