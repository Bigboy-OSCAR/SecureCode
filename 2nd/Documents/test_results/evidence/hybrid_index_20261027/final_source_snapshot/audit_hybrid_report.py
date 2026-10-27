"""Verify preservation and the new report's links, examples and numeric tables."""
from collections import Counter
import json
from pathlib import Path
import re
from statistics import mean
import sys
sys.dont_write_bytecode=True
import experiment_hybrid as exp
import report_hybrid as report


def main():
    out=exp.OUT
    exp.validate(out)
    s=exp.read(out/'summary.json');v=exp.read(out/'verification.json')
    checks=[]
    def check(name,ok,detail=None):
        assert ok,(name,detail)
        checks.append(dict(name=name,passed=True,detail=detail))
    check('verified_complete_evaluation',v['status']=='PASS' and v['summary_sha256']==exp.v1.sha(out/'summary.json') and v['records']==864)
    text=exp.REPORT.read_text();edits=exp.read(out/'report_edits.json')['edits']
    reverted=text
    for e in reversed(edits):
        assert reverted.count(e['new'])==1,e['new'][:80]
        reverted=reverted.replace(e['new'],e['old'],1)
    check('all_previous_report_content_recoverable_byte_for_byte',reverted==(out/'history'/exp.REPORT.name).read_text(),dict(edits=len(edits)))
    section=text.split('<a id="hybrid"></a>',1)[1].split('<a id="detail"></a>',1)[0]
    regenerated=report.sections(s).split('<a id="hybrid"></a>',1)[1]
    check('new_results_generated_from_verified_summary',section==regenerated)
    generation=exp.read(out/'report_generation.json')
    check('report_materials_unchanged',all(exp.v1.sha(out/p)==sha for p,sha in generation['materials'].items()))
    check('method_actors_search_storage_payload_and_cost_explained',all(word in text for word in [
        '### 1.11 H','TF-IDF 가중치나 원문 본문은 이 호출에 보내지 않는다',
        '그 묶음 전체가 자동으로 전달되는 것은 아니다','선택 호출과 답변 호출의 입력을 모두 합산',
        '목록에 이름만 나타난 것은 원문을 포함한 것으로 세지 않는다','이미 여러 번 살펴본 동일 문제',
        'UI 버튼이나 제품의 색인 갱신 기능을 구현한 것은 아니다']))
    check('historical_results_distinguished_from_fresh_controls',all(x in text for x in [
        '새로 실행한 B·R0·H 결과는 8절에 모았다','이 다섯 방식까지 이번 세션에서 다시 실행한 것은 아니며',
        '파일 전체 · 기존','B · 이번','R0 · 이번','H · 이번']))
    plain=[];inside=False;columns=None
    for line in text.splitlines():
        if line.startswith('```'):
            inside=not inside
            continue
        if inside:continue
        plain.append(line)
        if line.startswith('|'):
            n=len(re.split(r'(?<!\\)\|',line))-2
            if columns is None:columns=n
            assert columns==n,(line,n,columns)
        else:columns=None
    check('balanced_code_fences_and_table_columns',not inside)
    check('no_image_embeds',not re.search(r'!\[',text))
    links=[]
    anchors=set(re.findall(r'<a id="([^"]+)"',text))
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)','\n'.join(plain)):
        if target.startswith(('http://','https://')):continue
        if target.startswith('#'):
            assert target[1:] in anchors,target
            continue
        p=Path(re.sub(r':\d+$','',target.strip('<>').split('#')[0]))
        if not p.is_absolute():p=exp.REPORT.parent/p
        assert p.exists(),p
        links.append(str(p.resolve()))
    check('local_links_and_explicit_anchors_resolve',True,dict(links=len(links)))
    rows=exp.audit.rows(out/'results.jsonl')
    calls=exp.audit.rows(out/'model_calls.jsonl')
    check('new_call_accounting',len(calls)==1482 and Counter(c['purpose'] for c in calls)=={'warmup':2,'select':592,'answer':888})
    examples=exp.read(out/'report_examples.json')
    bykey={(r['task_id'],r['repeat'],r['arm']):r for r in rows}
    tasks={t['id']:t for t in exp.read(out/'tasks.json')}
    diag=exp.read(out/'diagnostics_posthoc.json')
    hs=[r for r in rows if r['arm']=='H']
    check('posthoc_diagnostics_uses_unchanged_complete_results',diag['results_sha256']==exp.v1.sha(out/'results.jsonl') and
          diag['analysis_type']=='post_hoc_descriptive')
    reasons=Counter();locations=Counter()
    for r in hs:
        obj=json.loads(re.sub(r'^```json\s*|\s*```$','',r['selector']['answer'].strip()))
        nums=obj['read']
        reason=('empty_selection' if not nums else 'more_than_eight_items' if len(nums)>8 else
                'unlisted_row' if any(n<1 or n>len(r['source_index']['items']) for n in nums) else 'valid')
        reasons[reason]+=1
        shown={x['uri'] for x in r['source_index']['items']}
        ranked=[x['uri'] for x in r['symbol_ranking']]
        for u in tasks[r['task_id']]['required_uris']:
            locations['shown' if u in shown else 'zero_score' if u not in ranked else
                      'outside_top_24' if ranked.index(u)>=24 else 'index_512_token_limit']+=1
    check('posthoc_failure_categories_and_index_omissions_recomputed',dict(reasons)==diag['selection_outcomes'] and
          dict(locations)==diag['required_index_locations'])
    check('eight_item_structural_limit_count',sum(len(set(t['required_uris']))>8 for t in tasks.values())==
          diag['questions_requiring_more_than_eight_items']==62)
    for label,pred in [('all',lambda r:True),('valid_selection',lambda r:r['selection_valid']),
                       ('invalid_selection',lambda r:not r['selection_valid'])]:
        subset=[r for r in hs if pred(r)];g=diag['groups'][label]
        assert len(subset)==g['query_executions'] and len({r['task_id'] for r in subset})==g['unique_questions']
        for a in ['H','R0','B']:
            linked=[bykey[(r['task_id'],r['repeat'],a)] for r in subset]
            assert abs(mean(r['input_tokens'] for r in linked)-g['arms'][a]['mean_total_input'])<1e-9
            assert abs(mean(r['correct'] for r in linked)-g['arms'][a]['accuracy'])<1e-9
    check('conditional_costs_recomputed_on_matched_questions',True)
    for label,title in [('all','전체'),('valid_selection','선택 규칙을 지킴'),('invalid_selection','선택 규칙 위반 또는 빈 선택')]:
        g=diag['groups'][label]
        line=f"| {title} | {g['query_executions']} | {g['arms']['H']['mean_total_input']:.1f} | {g['arms']['R0']['mean_total_input']:.1f} | {g['H_total_reduction_vs_matched_R0_pct']:.1f}% |"
        assert line in text,line
    check('conditional_cost_table_matches_records',True)
    for item in examples:
        tid=item['task_id'];task=tasks[tid]
        assert item['expected']==task['expected'] and item['question']==task['question']
        for arm,data in item['arms'].items():
            r=bykey[(tid,item['repeat'],arm)]
            for k,value in data.items():assert r[k]==value,(tid,arm,k)
        check('example_'+tid,True)
    exp.v1.dump(out/'report_audit.json',dict(status='PASS',checked_at_utc=exp.audit.now(),checks=checks,
        report_sha256=exp.v1.sha(exp.REPORT),summary_sha256=exp.v1.sha(out/'summary.json'),
        verification_sha256=exp.v1.sha(out/'verification.json'),audit_source_sha256=exp.v1.sha(__file__),
        note='Document review and numerical/source checks, not an external reader comprehension study.'))
    print(json.dumps(dict(status='PASS',checks=len(checks),local_links=len(links)),ensure_ascii=False))


if __name__=='__main__':main()
