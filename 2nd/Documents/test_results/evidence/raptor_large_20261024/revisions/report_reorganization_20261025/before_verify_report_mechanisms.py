"""Check the new post-hoc claims and preservation of the published measurements."""
from __future__ import annotations
import json,math,re,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_raptor_large as exp
from analyze_report_mechanisms import REV,ARMS

def main():
    checks=[]
    def check(name,ok,detail=None):
        assert ok,(name,detail)
        checks.append({'name':name,'passed':True,'detail':detail})
    facts=exp.read(REV/'mechanism_facts.json')
    exp.validate(exp.OUT);exp.large.validate_frozen(exp.large.DEFAULT_OUT)
    check('frozen_measurements_and_inspected_source_files_unchanged',all(exp.v1.sha(p)==h for p,h in facts['source_hashes'].items()))
    allrows=exp.audit.rows(exp.OUT/'results.jsonl')+exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl')
    tasks={t['id']:t for t in exp.read(exp.OUT/'tasks.json')};assets=exp.read(exp.OUT/'assets.json')
    first={a:{r['task_id']:r for r in allrows if r['repeat']==0 and r['arm']==a} for a in ARMS}
    check('2016_preserved_answers_and_96_questions_per_method',len(allrows)==2016 and all(len(rs)==96 for rs in first.values()))
    for a,rs in first.items():
        m=facts['arms'][a];coverage=[];complete=[]
        for tid,r in rs.items():
            required=set(tasks[tid]['required_uris'])
            got=set().union(*(set(c['source_uris']) for c in r['chosen'] if c['level']==0))
            coverage.append(len(got&required)/len(required));complete.append(required<=got)
        assert math.isclose(100*sum(coverage)/96,m['raw_inclusion_pct'])
        assert sum(complete)==m['all_raw_questions']
        assert sum(ok and not r['correct'] for ok,r in zip(complete,rs.values()))==m['wrong_with_all_raw']
        assert sum(r['correct'] for r in rs.values())==m['correct']
        assert dict(Counter(r['failure'] for r in rs.values() if not r['correct']))==m['failures_by_question']
        assert sum(r['answer_call']['stop_type']=='limit' or r['answer_call']['stopped_limit'] for r in rs.values())==m['output_limit_questions']
        if a in ['A','B']:
            assert sum(r['selected_uri']==tasks[t]['target_uri'] for t,r in rs.items())==m['selector_matches_designated_target']
    check('all_seven_accuracy_coverage_selector_and_error_claims_recounted',True)
    for pair,data in facts['pairs'].items():
        base,arm=pair.split('->')
        assert set(data['wins'])=={t for t in tasks if first[arm][t]['correct'] and not first[base][t]['correct']}
        assert set(data['losses'])=={t for t in tasks if first[base][t]['correct'] and not first[arm][t]['correct']}
    check('all_paired_improvements_and_regressions_recounted',True)
    check('A_B_function_selection_identical_on_96_questions',all(first['A'][t]['selected_uri']==first['B'][t]['selected_uri'] for t in tasks))
    missing=packing=cap=matches=0
    for tid,r in first['B'].items():
        if r['selected_uri']!=tasks[tid]['target_uri']:continue
        matches+=1;nodes=assets[r['project']]['nodes'];required=set(tasks[tid]['required_uris'])
        emitted={u for c in r['chosen'] for u in c['source_uris']}
        assert all(uid in nodes for uid in r['rejected'])
        # B logs each pre-packing fragment by its exact source URI; no production traversal is called here.
        available=emitted|set(r['rejected'])
        missing+=bool(required-available);packing+=bool((required&available)-emitted)
        cap+=sum(nodes[u]['kind']=='function' for u in available)==8
    b=facts['B_expansion_diagnostic']
    check('B_pre_packing_gap_verified_from_saved_selected_and_rejected_records',
        (matches,missing,packing,cap)==(b['target_matches'],b['missing_required_before_packing'],b['required_lost_during_packing'],b['eight_function_cap_reached']),
        {'target_matches':matches,'missing_before_packing':missing,'lost_during_packing':packing,'eight_function_cap_reached':cap})
    for a in ['RF','RH','C']:
        aux=leaves=0;fileq=set();projectq=set()
        for tid,r in first[a].items():
            lookup={s['id']:s for s in assets[r['project']]['summaries']}
            for c in r['chosen']:
                if c['level']==1:
                    leaves+=1;child=lookup[c['id']]['children'][0]
                    aux+=assets[r['project']]['nodes'][child]['name'].startswith('aux_')
                if c['level']==2:fileq.add(tid)
                if c['level']==3:projectq.add(tid)
        f=facts['arms'][a]
        assert (aux,leaves,len(fileq),len(projectq))==(f['auxiliary_leaf_selections_one_repeat'],f['leaf_selections_one_repeat'],f['questions_with_file_summary'],f['questions_with_project_summary'])
    check('helper_summary_and_hierarchy_usage_checked_through_child_source_nodes',True)
    term=re.compile(r'(?i)(?<![a-z0-9])function(?![a-z0-9])')
    for project,d in facts['lexical_diagnostic']['projects'].items():
        asset=assets[project];leaves=[s for s in asset['summaries'] if s['level']==1]
        assert sum(bool(term.search(x['text'])) for x in asset['raw'])==d['function_document_frequency_raw']==0
        assert sum(bool(term.search(x['text'])) for x in leaves)==d['function_document_frequency_leaf']==len(leaves)
        assert math.isclose(math.log(1+len(asset['raw']))+1,d['function_idf'])
    check('function_word_frequency_and_unseen_word_weight_recomputed',
        sum(bool(term.search(t['question'])) for t in tasks.values())==facts['lexical_diagnostic']['questions_containing_term'])
    expiry='eval_authorization__expiry';key='eval_cache__canonical_key'
    check('expiry_counterexample_has_complete_raw_evidence_in_both_methods',
        all(first[a][expiry]['all_raw_evidence'] for a in ['R0','RF']) and first['R0'][expiry]['parsed_answer'] is False and first['RF'][expiry]['parsed_answer'] is True)
    higher=[c['id'] for c in first['RH'][key]['chosen'] if c['level']>1]
    body=next(s['text'] for s in assets['eval_cache']['summaries'] if s['id']==higher[0])
    check('only_RH_gain_and_actual_file_summary_are_traceable',facts['pairs']['RF->RH']['wins']==[key] and higher==['summary:level2:service.py'] and body.count('aux_service_')>=4)
    current=exp.REPORT.read_text();previous=(REV/exp.REPORT.name).read_text()
    start='## 2. 작은 파일:';end='### 9.7 같은 질문의 실제 답변'
    check('all_previous_measurement_sections_2_through_9_6_preserved',current[current.index(start):current.index(end)]==previous[previous.index(start):previous.index(end)])
    start='### 먼저, 원본 파일은 이렇게 생겼다';end='## 2. 작은 파일:'
    check('previous_source_index_and_summary_examples_preserved',current[current.index(start):current.index(end)]==previous[previous.index(start):previous.index(end)])
    section=current[current.index('### 색인·요약은 누가'):current.index('### 먼저, 원본 파일')]
    labels=['A — 현재 색인','B — 파일 간 확장','R0 — 원문 검색','RF — 함수 요약','RH — 계층 요약','C — 계층 요약 정리','파일 전체']
    check('construction_explanation_covers_every_method',all('| **'+label+'** |' in section for label in labels))
    check('construction_roles_and_actual_summary_settings_are_explicit',all(x in section for x in ['ast.parse','AST(','모든 방식의 최종 답변은 LLM','원문 후보만으로 단어의 희소성','영어 100단어','256토큰','하위 요약을 입력','일반 프로그램 처리','대상 파일 경로를 미리 제공']))
    section=current[current.index('### 9.8'):];section=section[:section.index('### 확인 자료')]
    check('all_seven_accuracy_explanations_separate_observations_from_hypotheses',all('**'+a+' — ' in section for a in ['A','B','R0','RF','RH','C','파일 전체']) and section.count('확인:')==7 and section.count('**추측:**')==8)
    check('posthoc_scope_and_unperformed_causal_checks_are_disclosed',all(x in section for x in ['사후 분석','추가 실험을 수행한 결과는 아니다','후속 검증 제안','이번에 실행한 실험 목록에 포함하지 않았다','기존 정답률이나 평가 기준은 바꾸지 않았다']))
    prior_audit=exp.read(exp.OUT/'completion_audit.json')
    check('report_numeric_and_markdown_audit_current',prior_audit['status']=='PASS' and prior_audit['report_sha256']==exp.v1.sha(exp.REPORT))
    result={'status':'PASS','completed_at_utc':exp.audit.now(),'checks':checks,'report_sha256':exp.v1.sha(exp.REPORT),
        'facts_sha256':exp.v1.sha(REV/'mechanism_facts.json'),'existing_answers':2016,'new_model_calls':0,
        'limitations':'Presence checks verify coverage, not causal truth. Hypotheses were manually reviewed against the inspected source and actual contexts, and remain labelled hypotheses.'}
    exp.v1.dump(REV/'verification.json',result)
    print(json.dumps({'status':'PASS','checks':len(checks),'new_model_calls':0,'report_sha256':result['report_sha256']},ensure_ascii=False))

if __name__=='__main__':main()
