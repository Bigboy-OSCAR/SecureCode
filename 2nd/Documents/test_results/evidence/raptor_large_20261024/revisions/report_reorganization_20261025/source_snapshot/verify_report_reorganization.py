"""Check content preservation, measured values and navigation after reordering.

This is a document audit, not a new experiment. It independently compares the
archived Markdown's code blocks, table cells and links with the final document.
Consolidated introductory/concluding prose is explicitly recorded for review.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode=True
import experiment_raptor_large as exp
from reorganize_report import INPUT_SHA256,REVISION


def normalize(text):
    return re.sub(r'\s+',' ',text.replace('**','').replace('`','')).strip()


def parsed_tables(text):
    result=[]
    current=[]
    in_code=False
    for line in text.splitlines()+['']:
        if line.startswith('```'):
            in_code=not in_code
        if not in_code and line.startswith('|'):
            current.append([v.strip() for v in re.split(r'(?<!\\)\|',line)[1:-1]])
        elif current:
            assert len(current)>1 and all(len(r)==len(current[0]) for r in current),current
            result.append(current)
            current=[]
    assert not in_code
    return result


def main():
    rev=exp.OUT/REVISION
    before=(rev/exp.REPORT.name).read_text()
    after=exp.REPORT.read_text()
    checks=[]

    def check(name,condition,detail=None):
        assert condition,(name,detail)
        checks.append({'name':name,'passed':True,'detail':detail})

    check('archived_original_matches_verified_editorial_revision',hashlib.sha256(before.encode()).hexdigest()==INPUT_SHA256)
    manifest=exp.read(exp.OUT/'report_manifest.json')
    check('current_document_matches_generation_manifest',exp.v1.sha(exp.REPORT)==manifest['report_sha256'])
    mapping=exp.read(rev/'content_map.json')
    counts=Counter()
    original_lines=before.splitlines()
    for item in mapping['entries']:
        a,b=item['source_start'],item['source_end']
        source='\n'.join(original_lines[a-1:b]).strip()
        assert hashlib.sha256(source.encode()).hexdigest()==item['source_sha256']
        for n in range(a,b+1):
            if original_lines[n-1].strip():
                counts[n]+=1
        if item['action']=='moved_or_reformatted':
            assert item['output_text'] in after,(a,b,item['destination'])
    expected={n for n,l in enumerate(original_lines,1) if l.strip()}
    check('all_nonempty_original_lines_accounted_for_once',set(counts)==expected and set(counts.values())=={1},len(expected))
    check('all_moved_content_blocks_present',True,sum(i['action']=='moved_or_reformatted' for i in mapping['entries']))

    original_codes=re.findall(r'^```[^\n]*\n(.*?)^```\s*$',before,re.M|re.S)
    final_codes=re.findall(r'^```[^\n]*\n(.*?)^```\s*$',after,re.M|re.S)
    check('every_original_code_json_and_summary_example_preserved',not (Counter(original_codes)-Counter(final_codes)),len(original_codes))

    # Every data cell of every original table must survive somewhere in the text.
    # Only location references change; no numerical normalization is used here.
    tables=parsed_tables(before)
    final_tables=parsed_tables(after)
    normalized_after=normalize(after)
    cells=[]
    for t in tables:
        for row in t[2:]:
            for cell in row:
                cell=cell.replace('8절과 바이트까지 동일한 큰 파일','2.2절과 바이트까지 동일한 큰 파일')
                cell=cell.replace('8절의 A·B·R0·파일 전체','2.2절의 A·B·R0·파일 전체')
                cells.append(cell)
    missing=[c for c in cells if normalize(c) not in normalized_after]
    check('every_original_table_data_cell_retained',not missing,{'tables':len(tables),'cells':len(cells),'missing':missing})

    old_seven=next(t for t in tables if t[0][0]=='방식' and '정답 / 96' in t[0])
    new_quality=next(t for t in final_tables if t[0]==['방식','정답 / 96','정답률','대표 응답 시간','p95'])
    new_cost=next(t for t in final_tables if t[0]==['방식','평균 근거 토큰','평균 총 입력 토큰','파일 전체 대비 총 입력 절감'])
    check('seven_method_results_keep_each_value_with_its_correct_method',
          new_quality[2:]==[[r[i] for i in [0,1,2,3,4]] for r in old_seven[2:]] and
          new_cost[2:]==[[r[i] for i in [0,5,6,7]] for r in old_seven[2:]])

    # With three transformed/merged tables, all other tables remain intact.
    transformed_headers=[tables[0][0],['저장 항목','실제 요약 본문'],old_seven[0],
                         ['방식','함수 선택 입력','최종 답변 입력','총 입력']]
    exact=0
    for t in tables:
        if t[0] in transformed_headers:
            continue
        adjusted=[[c.replace('8절과 바이트까지 동일한 큰 파일','2.2절과 바이트까지 동일한 큰 파일').replace('8절의 A·B·R0·파일 전체','2.2절의 A·B·R0·파일 전체') for c in r] for r in t]
        assert adjusted in final_tables,t[0]
        exact+=1
    check('all_other_result_condition_category_case_and_statistics_tables_unchanged',True,exact)

    links=lambda text:re.findall(r'\[[^\]]*\]\(([^)]+)\)',text)
    old_links=set(links(before));new_links=set(links(after))
    check('all_original_evidence_and_paper_links_retained',old_links<=new_links,{'original_unique_targets':len(old_links)})
    anchors=re.findall(r'<a id="([^"]+)"',after)
    check('navigation_anchors_unique',len(anchors)==len(set(anchors)))
    check('all_internal_navigation_links_resolve',all(x[1:] in anchors for x in new_links if x.startswith('#')))
    check('no_stale_section_8_or_9_references',not re.search(r'(?<![\d.])(?:8|9)(?:\.\d+)?절|1~7절',after))
    check('markdown_tables_and_code_fences_balanced',bool(final_tables))
    check('markdown_has_no_images_or_hidden_sections','![' not in after and '<details' not in after)
    check('all_seven_factual_and_hypothesis_explanations_retained',
          all(f'**{name} — ' in after for name in ['A','B','R0','RF','RH','C','파일 전체']) and
          after.count('**확인:**')==7 and after.count('**추측:**')==8)
    check('limits_and_unperformed_experiments_remain_explicit',all(t in after for t in [
        '사후 분석','추가 실험을 수행한 결과는 아니다','입력 잘림은 없었으며','원 논문 전체',
        '0.09375','보정 p값','세션','한국어 질문','보안 취약점 탐지',
        '후속 검증 제안','이번에 실행한 실험 목록에 포함하지 않았다']))

    old_deliverable=exp.read(rev/'deliverable_manifest.json')
    mutable={'report_manifest.json','completion_audit.json','final_source_manifest.json','reproduce.txt'}
    frozen={p:h for p,h in old_deliverable['hashes'].items() if p not in mutable}
    check('all_existing_measurement_analysis_and_previous_revision_records_unchanged',
          all(exp.v1.sha(exp.OUT/p)==h for p,h in frozen.items()),len(frozen))
    # Validate the experiment's own frozen corpus/protocol/source constraints too.
    exp.validate(exp.OUT)
    exp.large.validate_frozen(exp.large.DEFAULT_OUT)
    check('both_experiment_protocols_still_valid',True)
    result={'status':'PASS','completed_at_utc':exp.audit.now(),'checks':checks,
            'report_sha256':exp.v1.sha(exp.REPORT),'before_sha256':INPUT_SHA256,
            'new_model_calls':0,'original_table_count':len(tables),'original_table_data_cells':len(cells),
            'original_code_blocks':len(original_codes),'mapped_nonempty_source_lines':len(expected),
            'limitations':'The mapping and exact comparisons check content preservation. Consolidated front matter and conclusions were additionally reviewed for meaning; automated checks alone do not prove prose equivalence.'}
    exp.v1.dump(rev/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['checks','limitations']},ensure_ascii=False))
    print('Passed checks:',len(checks))


if __name__=='__main__':
    main()
