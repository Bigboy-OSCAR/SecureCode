"""Final numerical, example, link and preservation checks for the Markdown report."""
from __future__ import annotations
import json, math, re, sys
from collections import Counter,defaultdict
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_raptor_large as exp

def main():
    out=exp.OUT;checks=[]
    def check(name,value,detail=None):
        assert value,(name,detail);checks.append({'name':name,'passed':True,'detail':detail})
    exp.validate(out);exp.large.validate_frozen(exp.large.DEFAULT_OUT)
    check('new_and_previous_experiment_inputs_unchanged',True)
    for path,h in exp.read(out/'historical_reference_manifest.json')['source_hashes'].items():assert exp.v1.sha(path)==h,path
    check('report01_historical_reference_records_unchanged',True)
    for path,h in exp.read(out/'analysis_plan.json')['files'].items():assert exp.v1.sha(path)==h,path
    check('analysis_and_independent_verification_sources_preserved',True)
    rows=exp.audit.rows(out/'results.jsonl')+exp.audit.rows(exp.large.DEFAULT_OUT/'results.jsonl')
    summary=exp.read(out/'summary.json');verification=exp.read(out/'verification.json');numeric=0
    check('independent_verification_pass',verification['status']=='PASS' and verification['summary_sha256']==exp.v1.sha(out/'summary.json'),len(verification['checks']))
    def equal(a,b):
        nonlocal numeric
        assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-8),(a,b);numeric+=1
    for pop,target in summary['populations'].items():
        group=rows if pop=='all96' else [r for r in rows if r['split']==pop]
        expected={}
        for arm in summary['arms']:
            rs=[r for r in group if r['arm']==arm];n=len(rs)
            expected[arm]={'context':sum(r['context_tokens'] for r in rs)/n,
                'selected_before_compaction':sum(r['selected_context_tokens'] for r in rs)/n,
                'selector':sum(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs)/n,
                'answer':sum(r['answer_call']['input_tokens'] for r in rs)/n,
                'total':sum(r['input_tokens'] for r in rs)/n,
                'peak':sum(max(r['answer_call']['input_tokens'],r['selector']['input_tokens'] if r['selector'] else 0) for r in rs)/n}
        for arm,e in expected.items():
            e['saving_total_vs_full_pct']=100*(1-e['total']/expected['FULL']['total'])
            e['saving_context_vs_full_pct']=100*(1-e['context']/expected['FULL']['context'])
            e['window_pct']=100*e['peak']/8192
            for key,value in e.items():equal(value,target['tokens'][arm][key])
    check('all_report_token_averages_ratios_and_window_percentages',True,{'numeric_fields':numeric})
    calls=exp.audit.rows(out/'model_calls.jsonl');eval_projects={t['project'] for t in exp.read(out/'tasks.json')}
    cs=[c for c in calls if c['purpose'].startswith('build_') and c['meta']['project'] in eval_projects]
    b=summary['build']['evaluation']
    equal(len(cs),b['summary_calls']);equal(sum(c['input_tokens'] for c in cs),b['input_tokens'])
    equal(sum(c['output_tokens'] for c in cs),b['output_tokens']);equal(sum(c['wall_seconds'] for c in cs),b['model_wall_seconds'])
    equal(sum(c['stop_type']=='limit' or c['stopped_limit'] for c in cs),b['output_limit_calls'])
    check('preparation_costs_and_limits_recomputed',True)
    ex=exp.read(out/'index_example/generated.json');ec=exp.audit.rows(out/'index_example/model_calls.jsonl')
    lookup={s['id']:s for s in ex['asset']['summaries']};leaf=lookup['summary:leaf:memory://symbol/service.py::remaining']['text'].split('\n',1)[1]
    root=lookup['summary:level3:project']['text'].split('\n',1)[1]
    check('example_has_actual_summaries_but_no_question_answer_call',len(ec)==6 and all(c['purpose'].startswith('build_') and c['ok'] for c in ec))
    check('example_numeric_omission_and_higher_summary_are_real',not re.search(r'\b3\b',leaf) and bool(re.search(r'\b3\b',root)))
    check('example_selection_and_compaction_match',ex['arms']['RH']['chosen']==ex['arms']['C']['chosen'] and ex['arms']['C']['compaction']['payload_preserved'] and {a:r['tokens'] for a,r in ex['arms'].items()}=={'RF':417,'RH':754,'C':658})
    report=exp.REPORT.read_text();manifest=exp.read(out/'report_manifest.json')
    check('report_saved_from_verified_results',exp.v1.sha(exp.REPORT)==manifest['report_sha256'] and manifest['summary_sha256']==exp.v1.sha(out/'summary.json'))
    inside=False;plain=[];columns=None
    for line in report.splitlines():
        if line.startswith('```'):inside=not inside;continue
        if inside:continue
        plain.append(line)
        if line.startswith('|'):
            n=len(re.split(r'(?<!\\)\|',line))-2
            if columns is None:columns=n
            assert n==columns,('table column mismatch',line,n,columns)
        else:columns=None
    check('balanced_fences_and_table_columns',not inside)
    check('required_explanations_and_latest_results_present',all(s in report for s in ['### RF:','### RH:','### C:','### 세 방식에는 RAPTOR','## 9. 같은 큰 파일','사전 요약 생성 비용','최대 호출 입력의 평균','0.09375']))
    check('markdown_has_no_image_embeds',not re.search(r'!\[',report))
    links=[]
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)','\n'.join(plain)):
        if target.startswith(('https://','http://','#')):continue
        name=re.sub(r':\d+$','',target.strip('<>').split('#')[0]);path=Path(name)
        if not path.is_absolute():path=exp.REPORT.parent/path
        assert path.exists(),str(path);links.append(str(path.resolve()))
    check('local_report_links_resolve',True,{'links':len(links)})
    exp.v1.dump(out/'completion_audit.json',{'status':'PASS','completed_at_utc':exp.audit.now(),'checks':checks,
        'report_sha256':exp.v1.sha(exp.REPORT),'numeric_fields':numeric,'model_calls_main':len(calls),
        'model_calls_example':len(ec),'actual_eval_answers':len(rows),'new_eval_answers':864})
    print(json.dumps({'status':'PASS','checks':len(checks),'numeric_fields':numeric,'local_links':len(links)},ensure_ascii=False))

if __name__=='__main__':main()
