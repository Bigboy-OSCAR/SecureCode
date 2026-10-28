"""Append the verified, complete document experiment as report section 9.

No inference, no partial-result publication, no edits to frozen experiment code.
``render`` writes a standalone section only. ``apply`` also makes two reversible
insertions and one historical-scope clarification, then audits the report.
``audit`` rechecks the installed report. ``self-test`` exercises formatting and
reversal using in-memory fixtures, without fabricating experiment artifacts.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, re
from pathlib import Path
from common import ARMS, DATASETS, HERE, OUT, digest, dump, now, read, rows, sha

REPORT_NAME = '03_현재색인_A와_파일간확장_B_재실험_비교보고서.md'
ANCHOR = '<a id="document-benchmarks"></a>'
TITLE = '## 9. 데이터셋을 이용한 실험'
SECTION_FILE = 'report_section09.md'
CONTENTS_OLD = '| [8. 추가 실험: TF-IDF·색인 결합 H](#hybrid) | |'
CONTENTS_NEW = CONTENTS_OLD + '\n| [9. 데이터셋을 이용한 실험: A·B·R0·FULL](#document-benchmarks) | |'
APPENDIX = '<a id="detail"></a>\n\n## 부록 A. 상세 성적과 통계'
HISTORY_OLD = '아래 링크는 기존 실행 기록과 검증 자료다. **이번 편집은 문서의 배치·제목·표 구성을 정리한 것이며, 새 LLM 실험이나 정답률 변경은 없다.**'
HISTORY_NEW = '아래 C.1~C.5는 기존 코드 실험의 실행 기록과 문서 정리 이력이다. **이 문서 정리 당시에는 새 LLM 실험이나 정답률 변경이 없었다.** 이후 추가한 H 실험은 8.8절, 이번 일반 문서 실험은 9.7절의 기록을 따른다.'
EXAMPLE = ('Passage 1:\nProject Schedule\nThe launch depends on Review Schedule. This section also lists communication tasks.\n\n'
           'Passage 2:\nReview Schedule\nApproval is scheduled for 12 June.\n')
EXAMPLE_PREVIEW = 'Passage 1: Project Schedule The launch depends on Review Schedule. This section'
COUNTS = dict(zip(DATASETS, [272, 984, 3425, 2086, 200, 200, 150]))
NAMES = dict(zip(DATASETS, ['QMSum', 'Qasper', 'NarrativeQA', 'QuALITY', 'HotpotQA', 'MuSiQue', 'MultiFieldQA-en']))
METRICS = dict(zip(DATASETS, ['ROUGE 기하평균', 'F1', 'F1', 'EM', 'F1', 'F1', 'F1']))
EXPECTED_METRICS = dict(zip(DATASETS, ['rouge/geometric_mean', 'f1', 'f1', 'exact_match', 'f1', 'f1', 'f1']))
BENCHMARKS = {d: ('SCROLLS validation' if d in DATASETS[:4] else 'LongBench v1 test') for d in DATASETS}
INTRO = {
    'qmsum': '회의록을 읽고 특정 질의에 맞는 요약을 작성한다. 한 문장의 사실만 찾는 문제와 달리, 여러 발언에 흩어진 결정·의견을 함께 담아야 한다.',
    'qasper': '연구 논문을 읽고 질문에 답한다. 답은 짧은 설명뿐 아니라 yes/no 또는 답할 수 없음일 수 있다. 같은 질문에 여러 참조 답안이 있으면 모두 채점에 사용한다.',
    'narrative_qa': '공식 배포본의 책·영화 대본 본문 전체를 검색 대상으로 사용해 이야기 질문에 답한다. 외부 줄거리 요약으로 원문을 대체하지 않았다. 같은 작품에 여러 질문이 있으므로 질문 수와 독립 자료 수를 구분한다.',
    'quality': '긴 기사·이야기를 읽고 네 선택지 중 정답을 고른다. 모델에는 선택지의 문자만이 아니라 정답 선택지의 본문을 출력하게 했다. 이번 배포본에는 hard 구분이 없어 별도 hard 점수를 만들지 않았다.',
    'hotpotqa': '여러 위키 문서의 단서를 결합해 답한다. LongBench가 제공하는 문서들과 방해 문서를 모두 검색 대상으로 유지했다. 원래 HotpotQA 전체 dev/test와는 다른 LongBench 배포 과제다.',
    'musique': '여러 단계를 이어야 풀 수 있는 질문이다. 한 문서에서 얻은 정보로 다른 문서의 단서를 찾아야 할 수 있다. 여기서는 LongBench가 제공한 전체 문서 묶음을 사용했다.',
    'multifieldqa_en': '다양한 분야의 긴 영어 문서에서 답할 내용을 찾는다. 일부 분야에 맞춘 별도 검색 규칙 없이, 다른 과제와 같은 A·B·R0 규칙을 적용했다.',
}
URLS = {
    'tfidf': 'https://www.sciencedirect.com/science/article/pii/0306457388900210',
    'logtf': 'https://nlp.stanford.edu/IR-book/html/htmledition/sublinear-tf-scaling-1.html',
    'scrolls': 'https://aclanthology.org/2022.emnlp-main.823/',
    'longbench': 'https://aclanthology.org/2024.acl-long.172/',
    'raptor': 'https://proceedings.iclr.cc/paper_files/paper/2024/file/8a2acd174940dbca361a6398a4f9df91-Paper-Conference.pdf',
}


def number(value, decimals=1, signed=False):
    if value is None: return '—'
    assert isinstance(value,(float,int)) and math.isfinite(value)
    return format(value, f'{"+" if signed else ""},.{decimals}f')


def interval(values, decimals=2):
    return '산출 불가' if values is None else f'[{number(values[0],decimals)}, {number(values[1],decimals)}]'


def score(arm):
    return '—' if not arm.get('official') else number(arm['official']['score_unrounded'],2)


def table(headers, lines):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] +
                     ['| '+' | '.join(map(str,line))+' |' for line in lines])


def require_gate(summary, verification, completed, protocol, hashes):
    """Pure gate, also exercised by self-test; missing evidence never passes."""
    assert verification.get('status')=='PASS', 'Final verification must be PASS'
    assert summary.get('provisional') is False, 'Provisional summaries cannot be reported'
    assert protocol['config']['arms']==ARMS and protocol['config']['datasets']==DATASETS
    assert protocol['config']['model_context']==32768 and protocol['config']['source_budget']==1024
    expected=sum(COUNTS.values())*len(ARMS)
    for key in ['expected_result_rows','observed_result_rows','analyzed_result_rows']:
        assert summary[key]==expected, (key,'Full benchmark results are required')
    assert summary['unfinished_question_rows_excluded']==0
    assert completed['rows']==expected
    assert set(summary['datasets'])==set(DATASETS)
    for dataset,n in COUNTS.items():
        d=summary['datasets'][dataset]
        assert d['expected_questions']==n and d['all_questions']['n_questions']==n
        allids=d['all_questions']['task_ids']; fitids=d['full_fit']['task_ids']
        assert len(allids)==len(set(allids))==n
        assert len(fitids)==len(set(fitids))==d['full_fit']['n_questions']
        assert set(fitids)<=set(allids)
        assert d['excluded_from_full_fit']==n-len(fitids)
        for population in ['all_questions','full_fit']:
            cohort=d[population]
            assert set(cohort['arms'])==set(ARMS)
            for arm in ARMS:
                a=cohort['arms'][arm]
                assert a['n']==cohort['n_questions']
                if a['n']:
                    assert a['official']['metric']==EXPECTED_METRICS[dataset]
                    assert a['completed_answers']+a['context_overflow']==a['n']
        assert d['all_questions']['arms']['FULL']['completed_answers']==len(fitids)
    for name in ['summary','results','protocol','task_scores']:
        assert verification[name+'_sha256']==hashes[name], ('Unbound final verification',name)
    assert summary['results_sha256']==completed['results_sha256']==hashes['results']
    assert summary['task_scores_sha256']==hashes['task_scores']
    assert summary['tasks_sha256']==protocol['tasks_sha256']==hashes['tasks']
    assert protocol['data_manifest_sha256']==hashes['data_manifest']
    assert summary['analysis_plan_sha256']==protocol['analysis_plan_sha256']==hashes['analysis_plan']
    assert summary['source_clusters_sha256']==protocol['source_clusters_sha256']==hashes['source_clusters']


def load_verified(out=OUT):
    out=Path(out)
    names={'summary':'.json','verification':'.json','completed':'.json','protocol':'.json',
           'results':'.jsonl','task_scores':'.jsonl','tasks':'.jsonl','data_manifest':'.json',
           'analysis_plan':'.json','source_clusters':'.json'}
    for name,ext in names.items():
        assert (out/(name+ext)).is_file(), f'Final artifact missing: {name+ext}'
    hashes={name:sha(out/(name+ext)) for name,ext in names.items()}
    values={name:read(out/(name+'.json')) for name in names if names[name]=='.json'}
    require_gate(values['summary'],values['verification'],values['completed'],values['protocol'],hashes)
    tasks=rows(out/'tasks.jsonl')
    assert collections.Counter(t['dataset'] for t in tasks)==collections.Counter(COUNTS)
    assert len({t['task_id'] for t in tasks})==sum(COUNTS.values())
    assert values['data_manifest']['task_count']==len(tasks)
    for dataset in DATASETS:
        assert set(values['summary']['datasets'][dataset]['all_questions']['task_ids'])=={
            t['task_id'] for t in tasks if t['dataset']==dataset}
    values.update(tasks=tasks,hashes=hashes,out=out)
    return values


def graph_statistics(values):
    """Counts describe source structure, never ground-truth evidence coverage."""
    out=values['out'];manifest=values['data_manifest'];tasks=values['tasks']
    assets={}
    for uid,meta in manifest['document_files'].items():
        path=out/meta['path'];assert sha(path)==meta['sha256']
        doc=read(path);assert digest(doc['context'])==uid==doc['document_id']
        byid={n['id']:n for n in doc['nodes']}
        cross=sum(byid[dep]['doc_id']!=n['doc_id'] for n in doc['nodes'] for dep in n['deps'])
        assets[uid]={'cross_edges':cross,'linked_nodes':sum(bool(n['deps']) for n in doc['nodes']),
                     'multi_document':len(doc['roots'])>1,'source_documents':len(doc['roots']),
                     'tokens':meta['context_tokens'],'nodes':len(doc['nodes']),
                     'edges':meta['edge_counts']}
    mapping=values['source_clusters']['document_to_cluster'];result={}
    for dataset in DATASETS:
        selected=[t for t in tasks if t['dataset']==dataset]
        ids={t['document_id'] for t in selected}
        edge_counts=collections.Counter()
        for uid in ids:edge_counts.update(assets[uid]['edges'])
        result[dataset]={'exact_contexts':len(ids),'clusters':len({mapping[uid] for uid in ids}),
            'question_weighted_mean_tokens':sum(assets[t['document_id']]['tokens'] for t in selected)/len(selected),
            'nodes':sum(assets[uid]['nodes'] for uid in ids),
            'linked_nodes':sum(assets[uid]['linked_nodes'] for uid in ids),
            'cross_edges':sum(assets[uid]['cross_edges'] for uid in ids),
            'multi_document_contexts':sum(assets[uid]['multi_document'] for uid in ids),
            'edges':dict(edge_counts)}
    return result


def all_table(dataset, cohort):
    lines=[]
    for name in ARMS:
        arm=cohort['arms'][name]
        lines.append([name,score(arm),f"{arm['completed_answers']:,}/{arm['n']:,} ({100*arm['coverage']:.1f}%)",
                      f"{arm['context_overflow']:,}", '—' if name not in {'A','B'} else f"{arm['selector_invalid']:,}",
                      f"{arm['output_limit']:,}"])
    return table(['방식',METRICS[dataset]+' 점수','답변 완료/전체','입력 초과','목록 선택 실패','답변 출력 한도 도달'],lines)


def fit_table(dataset, cohort):
    if not cohort['n_questions']:
        return 'FULL을 온전히 입력할 수 있는 문항이 없어, 네 방식의 공통 문항 비용·점수 비교를 계산하지 않았다.'
    lines=[]
    for name in ARMS:
        arm=cohort['arms'][name];usage=arm['usage'];latency=usage['query_seconds']
        lines.append([name,score(arm),number(usage['input_tokens']['mean']),
                      number(usage['peak_input_tokens']['mean']),
                      f"{number(latency['mean'],2)} (n={latency['n']:,})"])
    return table(['방식',METRICS[dataset]+' 점수','누적 입력 토큰/질문','최대 호출 입력의 평균','평균 시간·초 (측정 문항)'],lines)


def contrast_text(label, contrast):
    if not contrast['n'] or contrast['score'] is None:return label+' 비교를 계산할 공통 문항이 없다.'
    result=contrast['score']
    return f"{label} **{number(result['difference_percentage_points'],2,True)}점** {interval(result['ci95'])}"


def full_comparison_table(cohort):
    lines=[]
    for arm in ['A','B','R0']:
        item=cohort['paired_contrasts'][arm+'-FULL'];result=item['score']
        saving=item['usage']['input_tokens']['savings_vs_FULL_percent']
        latency=item['usage']['query_seconds']
        lines.append([arm+'−FULL',
            f"{number(result['difference_percentage_points'],2,True)} {interval(result['ci95'])}",
            f"{number(saving['estimate'],1)}% {interval(saving['ci95'],1)}",
            f"{number(latency['difference'],2,True)} {interval(latency['ci95'])} (n={latency['n_pairs']:,})"])
    return table(['FULL 대비','점수 차이 [구간]','입력 절감률 [구간]','시간 차이·초 [구간] (쌍 수)'],lines)


def dataset_section(index,dataset,values,stats):
    result=values['summary']['datasets'][dataset];allq=result['all_questions'];fit=result['full_fit']
    s=stats[dataset];n=allq['n_questions'];e=s['edges']
    lines=[f'#### 9.5.{index} {NAMES[dataset]} — {METRICS[dataset]}로 평가', '', INTRO[dataset], '',
        f"**{BENCHMARKS[dataset]}, {n:,}문항 전부.** 고유 입력 원문 {s['exact_contexts']:,}개, "
        f"통계용 원문 묶음 {s['clusters']:,}개. 질문별 전체 원문은 평균 "
        f"{number(s['question_weighted_mean_tokens'],0)}토큰이다.", '',
        all_table(dataset,allq), '',
        f"**FULL이 들어가는 동일 {fit['n_questions']:,}문항에서 비교** "
        f"(전체 중 {100*fit['n_questions']/n:.1f}%, 제외 {result['excluded_from_full_fit']:,}문항).", '',
        fit_table(dataset,fit), '',
        '**전체 문항 점수 차이 [95% 구간]:** '+contrast_text('B−A',allq['paired_contrasts']['B-A'])+'; '+
        contrast_text('R0−A',allq['paired_contrasts']['R0-A'])+'; '+
        contrast_text('R0−B',allq['paired_contrasts']['R0-B'])+'.']
    if fit['n_questions']:
        lines.extend(['',full_comparison_table(fit)])
    if dataset=='qmsum':
        components=[]
        for arm in ARMS:
            u=allq['arms'][arm]['official']['components_unrounded']
            components.append(arm+' '+ '/'.join(number(u['rouge/'+key],2) for key in ['rouge1','rouge2','rougeL']))
        lines.extend(['','전체 문항의 ROUGE-1/2/L은 '+', '.join(components)+'이다. 표의 대표 점수는 이 세 평균의 기하평균이다.'])
    lines.extend(['',f"**연결 구조:** 조각 {s['nodes']:,}개 중 연결 보유 {s['linked_nodes']:,}개. "
        f"문단 이어짐 {e.get('paragraph_continuation',0):,}개 / 같은 문서 절 제목 언급 "
        f"{e.get('section_heading_mention',0):,}개 / 다른 문서 제목 언급 {s['cross_edges']:,}개."])
    if s['cross_edges']==0:
        lines.extend(['다른 문서 확장은 불가능하다. A·B의 차이는 확장 깊이와 별도 선택 호출에서 생길 수 있다.'])
    else:
        lines.extend(['B가 다른 문서의 첫 조각까지 확장할 수 있다. 그 첫 조각이 필요한 근거인지는 별개다.'])
    return '\n'.join(lines)


def tradeoff_table(summary):
    """Describe observed per-task tradeoffs, never infer a cross-task winner."""
    records=[]
    for dataset in DATASETS:
        cohort=summary['datasets'][dataset]['full_fit'];n=cohort['n_questions']
        if not n:
            records.append([NAMES[dataset],'0','—','—','공통 비교 불가; 전체 문항의 점수·완료율 확인'])
            continue
        arms=cohort['arms']
        best_score=max(a['official']['score_unrounded'] for a in arms.values())
        best=[a for a in ARMS if abs(arms[a]['official']['score_unrounded']-best_score)<1e-10]
        lowest=min(a['usage']['input_tokens']['mean'] for a in arms.values())
        cheapest=[a for a in ARMS if abs(arms[a]['usage']['input_tokens']['mean']-lowest)<1e-10]
        representative=min(best,key=lambda a:arms[a]['usage']['input_tokens']['mean'])
        cheap=max(cheapest,key=lambda a:arms[a]['official']['score_unrounded'])
        if cheap in best:
            interpretation='관측 최고 점수와 최소 입력이 겹침'
        else:
            delta=best_score-arms[cheap]['official']['score_unrounded']
            cost=arms[representative]['usage']['input_tokens']['mean']
            saving=100*(1-lowest/cost) if cost else None
            interpretation=f"{cheap}는 {representative}보다 입력 {number(saving,1)}% 적고, 점수 {number(delta,2)}점 낮음"
        records.append([NAMES[dataset],f'{n:,}', '/'.join(best)+' '+number(best_score,2),
                        '/'.join(cheapest)+' '+number(lowest)+'토큰',interpretation])
    return table(['과제','FULL 가능 문항','관측 최고 점수','최소 누적 입력/질문','함께 읽을 차이'],records)


def render_text(values,stats):
    summary=values['summary'];manifest=values['data_manifest'];config=values['protocol']['config']
    total=sum(COUNTS.values());total_records=total*len(ARMS)
    calls=sum(summary['datasets'][d]['all_questions']['arms'][a]['actual_completed_calls'] for d in DATASETS for a in ARMS)
    overflow=sum(summary['datasets'][d]['all_questions']['arms']['FULL']['context_overflow'] for d in DATASETS)
    # Absolute paths keep the evidence links valid both in the final report and
    # when this section is opened independently from its evidence directory.
    local=str(Path(values['out']).resolve())+'/'
    datasets_table=table(['데이터셋','공식 배포·분할','원자료 행 → 서로 다른 질문','대표 지표'],[
        [NAMES[d],BENCHMARKS[d],f"{manifest['datasets'][d]['raw_rows']:,} → {COUNTS[d]:,}",METRICS[d]] for d in DATASETS])
    conditions_table=table(['고정 항목','이번 실행의 값'],[
        ['답변·선택 모델','Qwen2.5-Coder-7B-Instruct Q5_K_M, 로컬 llama-server'],
        ['전체 컨텍스트 한도','호출당 32,768토큰; 지시문·질문·자료·출력 예약분 포함'],
        ['A·B·R0 답변용 자료','출처 ID·위치 표기를 포함해 최대 1,024토큰; 후보 전체가 들어가지 않으면 건너뜀'],
        ['원문 조각','문단·발언을 보존해 나누며, 긴 단위는 실제 모델 기준 최대 256토큰으로 분할'],
        ['A·B 선택 목록','최대 24개 후보·2,048토큰; 선택 출력 최대 32토큰, 원문 확장 최대 8조각'],
        ['최종 출력 상한','QMSum 512 / Qasper·NarrativeQA 128 / QuALITY 256 / HotpotQA·MuSiQue 32 / MultiFieldQA-en 64토큰'],
        ['반복과 실행 순서','질문당 각 방식 1회, temperature 0·seed 1; 데이터셋을 번갈아 진행하고 네 방식 순서를 균형 배치'],
        ['캐시·집계','모델 프롬프트 캐시 비활성화; 선택 호출과 답변 호출의 입력을 모두 합산'],
    ])
    methods_table=table(['방식','질문을 받은 뒤 누가 무엇을 고르나?','최종 답변 LLM에 보내는 자료'],[
        ['A','프로그램이 제목·앞부분 단어로 목록을 추림 → LLM이 출발 조각 1개 선택 → 프로그램이 같은 문서 연결을 1단계 확장','선택·확장된 조각의 실제 원문'],
        ['B','A와 같은 목록·별도 LLM 선택 → 프로그램이 다른 문서도 허용해 연결을 2단계 확장','선택·확장된 조각의 실제 원문'],
        ['R0','프로그램이 질문과 단독 원문·최대 3단계 연결 묶음의 TF-IDF 유사도를 계산해 선택','선택한 후보의 실제 원문; 별도 선택 LLM 호출 없음'],
        ['FULL','프로그램이 공식 입력의 전체 원문을 그대로 준비','제공된 원문 전부; 한 문서 또는 여러 문서 전체 묶음'],
    ])
    chunks=[ANCHOR,'',TITLE,'',
        f'이 절은 **긴 일반 문서에서도 필요한 원문을 골라 보내는 것이 전체 원문 입력보다 유리한가**를 시험한다. '
        f'공식 배포 자료의 서로 다른 질문 **{total:,}개 전체**를 A·B·R0·FULL 네 방식으로 평가했다. '
        f'최종 기록은 **{total_records:,}개**, 실제 수행한 선택·답변 호출은 **{calls:,}회**다. '
        '사전 연결 점검 호출은 이 수치와 아래 비교 비용에서 제외했다. '
        f'FULL은 **{overflow:,}문항**에서 컨텍스트를 초과해 답변 요청을 실행하지 못했다. 아래에는 이 실패를 포함한 결과와, FULL이 들어가는 같은 문항끼리의 비교를 모두 제시한다.', '',
        '**1~8절의 코드 실험과 구분한다.** 여기서 A·B는 코드 색인을 일반 문서에 맞게 바꾼 방식이고, '
        'FULL은 질문에 제공된 전체 자료다. 함수가 들어 있는 파일 하나를 보낸 이전 FULL과 범위가 다르다. '
        'RF·RH·C·H 및 RAPTOR 요약 트리를 새로 실행한 결과는 이 절에 포함하지 않는다.', '',
        '### 9.1 어떤 논문과 평가 원칙을 참고했나?', '',
        f'R0의 핵심은 **문서와 질문을 단어 가중치 벡터로 바꾸고 유사도를 계산하는 기존 정보검색 방법**이다. '
        f'새로운 지표를 발명한 것이 아니다. 단어 가중치와 코사인 비교는 [Salton·Buckley의 연구]({URLS["tfidf"]}), '
        f'등장 횟수에 로그를 적용하는 이유는 [정보검색 교재의 설명]({URLS["logtf"]})을 참고할 수 있다. '
        '이번 구현은 `TF = 1 + ln(등장 횟수)`, `IDF = ln((후보 수 + 1)/(해당 단어가 있는 후보 수 + 1)) + 1`을 곱하고 벡터 길이를 1로 맞춘 뒤 내적한다. '
        'IDF는 그 입력 원문의 원문 후보들로만 계산한다. 계산식과 예제의 자세한 흐름은 1.5절에 있다.', '',
        f'데이터 분할·여러 참조 답안의 처리·평가지표는 [SCROLLS]({URLS["scrolls"]})와 '
        f'[LongBench]({URLS["longbench"]})의 논문 및 공식 구현을 따른다. '
        '문단 분할, 제목 연결, 앞 12단어 미리보기, 1,024토큰 예산은 **이 프로젝트가 고정한 실험 규칙**이다. '
        'A·B의 문서 변환 방식 자체가 해당 논문에서 검증된 알고리즘이라는 뜻은 아니다.', '',
        f'[RAPTOR 논문]({URLS["raptor"]})이 평가한 데이터셋은 **NarrativeQA·QASPER·QuALITY 세 종류**다. '
        '이번의 일곱 데이터셋 전체가 RAPTOR 논문에 나온 것은 아니다. RAPTOR는 임베딩·군집·재귀 요약을 사용하며 일반 검색 예산은 2,000토큰이었다. '
        '이번 실험은 요약을 만들지 않고 같은 로컬 모델에 1,024토큰의 선택 자료를 주므로, 논문 점수 재현이나 RAPTOR 성능 검증으로 해석하지 않는다. '
        f'세부 대조는 [논문 조사 기록]({HERE / "research_papers.md"})에 남겼다.', '',
        '### 9.2 코드의 색인을 일반 문서에 어떻게 적용했나?', '',
        '**자료를 만드는 주체는 우리 프로그램이다.** 질문과 정답을 제외한 원문을 읽고, 각 조각의 ID·문서 제목·절 제목·문자 위치·앞 12단어를 저장한다. '
        '문단과 회의 발언을 나누며 긴 문단은 최대 256토큰 조각으로 분할한다. 모든 문자를 빠짐없이 보존하고, 나중에 위치로 원문을 읽는다. '
        '**앞 12단어는 원문 일부를 복사한 미리보기**이므로, 함수 이름과 위치만 있던 코드의 `symbol_index`와 동일하다고 부르면 안 된다. '
        '이 준비 단계에서 LLM 요약 호출은 없다. **프로그램이 원문 전체를 처리했다는 것과 LLM이 원문 전체를 읽었다는 것은 다르다.** '
        'A·B·R0의 답변 LLM에는 아래 규칙으로 골라 예산에 담은 원문만 전달된다.', '', methods_table, '',
        '문서 사이의 연결도 프로그램이 만든다. **고유한 두 단어 이상 문서 제목이 다른 문서에 그대로 등장하면 그 문서의 첫 조각으로 연결**한다. '
        '절 제목 언급은 같은 문서 안에서 연결한다. 한 문단을 여러 조각으로 나눈 경우에만 이웃 조각을 서로 잇는다. '
        '관련 있어 보인다는 이유로 연결을 추측하거나, 서로 다른 문단을 단순히 가깝다고 잇지 않는다. '
        '따라서 이 연결은 실제 Python `import`가 아니라, 제한적인 **제목 언급·문단 이어짐 관계**다.', '',
        '**짧은 동작 예시** — 아래 문장은 원리를 설명하기 위한 예시이며 평가 자료나 성능 결과가 아니다.', '',
        '```text\n'+EXAMPLE+'```', '',
        '프로그램은 첫 조각의 목록에 `ID=n000001`, `문서=Project Schedule`, '
        f'`미리보기="{EXAMPLE_PREVIEW}"`를 저장하고, '
        '제목 언급으로 `n000001 → n000002`를 연결한다. **두 방식이 같은 첫 조각을 골랐다고 가정하면**, '
        'A는 첫 문서 원문만, B는 두 번째 문서의 승인일 원문까지 읽을 수 있다. '
        'R0에는 첫 조각 단독·두 번째 조각 단독·연결된 두 조각 묶음이 검색 후보가 된다. '
        '**단독 후보가 선택되면 단독 원문만, 묶음 후보가 선택되면 그 묶음 원문을 보낸다.** '
        '가중치를 받아 LLM이 알아서 파일을 읽는 구조가 아니다.', '',
        'A·B는 제목·미리보기와 질문의 단어 겹침으로 최대 24개를 추린 뒤 LLM이 하나를 고른다. '
        'R0는 출처 ID·문서 ID·문자 위치 표기와 원문을 합친 각 후보 문자열의 TF-IDF로 순위를 계산하고, 높은 순서대로 1,024토큰 안에 들어가는 후보를 담는다. '
        '완전히 중복된 원문 후보는 생략하지만 부분 중복은 남을 수 있다. 원문을 중간에서 잘라 넣지는 않는다. '
        '질문에 맞는 핵심 내용을 반드시 골랐다는 보장은 없으며, 제목 연결이 드물면 B가 더 넓게 읽을 기회도 적다.', '',
        '### 9.3 입력 예산·초과·실패를 어떻게 공정하게 비교했나?', '',conditions_table,'',
        '**한도 안에 들어가는 문항에서는 FULL이 제공 원문 전부를 실제 전송했다.** `지시문 + 질문 + 전체 원문 + 출력 예약분 > 32,768`인 경우에는 '
        '모델에 보내기 전에 `context_overflow`로 기록했다. 가운데나 뒷부분을 자른 문서를 FULL이라고 부르지 않았다. '
        '이는 입력 가운데를 잘라 모델 한도에 맞추는 LongBench의 기본 평가 관행과 구분되는, 이번 비교의 명시적 규칙이다.', '',
        '**표는 두 모집단을 구분한다.** 전체 문항 표는 초과 문항도 빈 답변으로 공식 채점하며 답변 완료율을 함께 보여 준다. '
        '비용 표는 **FULL을 온전히 입력한 같은 문항만 골라 네 방식 모두 다시 집계**한다. '
        'FULL 초과 기록의 실제 입력·출력 비용은 0이지만, 답변을 실행하지 못한 결과이므로 이를 싼 방식이라고 평가하지 않는다. '
        '보내려고 준비한 길이는 `requested_answer_input_tokens`, 실제 수행한 입력은 `input_tokens`로 따로 남겼다.', '',
        '**누적 입력**은 질문 하나에서 선택·답변 호출을 모두 합친 토큰이다. **최대 호출 입력의 평균**은 질문마다 가장 큰 호출을 고른 뒤 평균한 값이다. '
        '두 호출을 합친 길이를 한 번의 컨텍스트 점유로 해석하지 않는다. 시간은 검색·선택·원문 구성·답변을 포함하며, '
        '모델 시작과 사전 자료 구축·로딩은 제외한다. 중간 복구로 온전한 질의 시간을 잴 수 없는 문항은 시간 평균에서만 제외하고 분모를 표기했다.', '',
        '목록 선택에 실패한 A·B는 빈 원문으로 답변 호출을 한 번 수행하고, 실제 나온 문장을 공식 지표로 채점했다. '
        '출력 한도에 닿은 답변도 나온 부분 그대로 채점한다. 재질문으로 답을 고치거나 성공한 경우만 남기지 않았다. '
        '이는 선택 실패를 자동 오답으로 처리한 앞선 코드 실험과 채점 규칙이 다르다.', '',
        '### 9.4 어떤 데이터를 몇 문제 사용했고, 점수는 무엇인가?', '',datasets_table,'',
        f'공식 원자료 **{sum(manifest["datasets"][d]["raw_rows"] for d in DATASETS):,}행** 중 같은 질문 ID의 여러 참조 답안을 묶어 '
        f'**{total:,}개의 서로 다른 질문**으로 평가했다. 임의 표본 추출은 하지 않았다. '
        'SCROLLS 입력에서 질문·QuALITY 선택지와 본문을 분리한 뒤 다시 합치면 원래 입력이 복원되는지도 검사했다. '
        'LongBench는 질문과 제공된 `context`를 각각 원래 필드 그대로 보존했다.', '',
        '**F1은 정답률이 아니다.** 정규화한 답변과 참조 답안의 단어가 얼마나 겹치는지 측정한다. '
        'ROUGE는 요약의 단어·구문 겹침을 재고, QMSum의 대표 점수는 문항 전체의 ROUGE-1·2·L 평균 세 개의 기하평균이다. '
        'QuALITY의 EM은 정규화한 정답 선택지 본문과 일치하는 비율이다. 모두 0~100으로 표시하지만 서로 다른 지표이므로 '
        '**일곱 과제의 점수를 합쳐 하나의 평균 성능으로 만들지 않았다.** 표는 소수 둘째 자리로 표시하며 정밀값은 원자료에 보존했다.', '',
        '아래 점수 차이의 95% 구간은 같은 입력 원문을 공유하는 질문들을 함께 묶어 10,000번 재표집해 계산했다. '
        '앞뒤 공백만 다른 원문은 같은 묶음으로 취급하지만 모델에 보낸 원문은 수정하지 않았다. '
        '여러 문서 입력끼리는 개별 문서가 겹칠 수 있어 완전한 독립성이 보장되지 않는다. '
        '구간은 차이의 불확실성을 보는 설명용이며, 0을 포함하지 않는다는 이유만으로 보정된 확증 검정 결과라고 주장하지 않는다. '
        '점수 차이의 단위는 0~100 척도의 **점**이다.', '',
        '### 9.5 데이터셋별 결과', '',
        '각 첫 표의 **답변 완료**는 모델의 답변 요청이 실행됐다는 뜻이며 정답 보장이 아니다. '
        '**입력 초과·선택 실패·답변 출력 한도**는 서로 다른 사건으로 구분했다. '
        '두 번째 표는 FULL 가능 문항을 네 방식에 동일하게 적용한다. 어떤 방식의 시간 분모만 작으면 복구 등으로 시간이 빠진 문항이 있다는 뜻이다. '
        'FULL 대비 표에서 **점수 차이가 음수면 낮은 점수, 입력 절감률이 양수면 적은 입력, 시간 차이가 음수면 빠른 응답**이다. '
        '시간 차이는 양쪽의 시간을 모두 측정한 질문 쌍으로만 계산하며, 모든 대괄호 구간은 95% 구간이다.', '',
        '각 과제의 **연결 구조**는 고유 원문마다 한 번씩 센 조각·연결 수이며 질문별 근거 적중률이 아니다. '
        '제목이 직접 등장하지 않거나 한 단어 제목이면 다른 문서 연결을 만들지 않는다. '
        '연결이 없는 같은 조각을 A·B가 고르면 읽을 원문 범위도 같다.','']
    for index,dataset in enumerate(DATASETS,1):chunks.extend([dataset_section(index,dataset,values,stats),''])
    chunks.extend(['### 9.6 이 결과를 실제 선택에 어떻게 사용할까?', '',
        '**완료된 수치에서 보이는 과제별 선택의 대가**를 아래에 모았다. 각 행은 FULL이 들어가는 동일 문항만 비교한다. '
        '‘최고’와 ‘최소’는 이번 관측값의 순위이며, 차이가 통계적으로 확정됐거나 다른 모델에도 유지된다는 뜻은 아니다.', '',
        tradeoff_table(summary), '',
        '**FULL이 들어가는 상황부터 판단한다.** 같은 문항의 점수 차이와 누적 입력·시간을 함께 보고, '
        '절약한 토큰만큼 답변 품질을 희생했는지 확인해야 한다. R0는 선택용 LLM 호출이 없지만 원문을 더 보낼 수 있고, '
        'A·B는 적은 원문을 골라도 목록 선택 호출이 추가된다. 따라서 어느 한 방식이 모든 과제와 예산에서 가장 효율적이라고 결론 내리지 않는다.', '',
        '**FULL이 들어가지 않는 상황은 별도의 이점이다.** 원문 일부를 골라 답변을 실행할 수 있다는 것은 처리 범위의 개선이다. '
        '그러나 실행됐다고 답이 정확한 것은 아니므로 전체 문항 점수를 함께 확인한다. '
        '이 실험에는 사람이 지정한 정답 근거 위치가 모든 과제에 공통으로 제공되지 않아, 이전 코드 실험의 ‘필요 원문 포함률’을 만들어 붙이지 않았다. '
        '제목 연결의 개수나 선택 원문의 길이를 그 지표로 대신해서도 안 된다.', '',
        '범위는 **일곱 공개 문서 과제·한 로컬 코딩 모델·한 번의 결정적 생성·선택 자료 1,024토큰**이다. '
        '문서용 A·B의 제목 언급 관계를 실제 코드의 import 관계처럼 일반화할 수 없고, 32,768 컨텍스트의 이번 결과를 '
        '8,192 컨텍스트였던 앞선 코드 실험과 합산할 수 없다. 모델·검색 예산·자료 분야가 바뀌면 우열도 달라질 수 있다.', '',
        '**준비 비용의 한계:** 자료 구축에는 LLM 요약 호출이 없었다. 저장된 준비 시간은 QuALITY 구분자 수정 후 '
        '이미 만든 유효 자료를 재사용한 마지막 성공 실행의 시간이다. 이를 처음부터 전체 색인을 만든 시간으로 제시하지 않는다. '
        '질의 시간에서도 자료 구축·로딩을 제외했으므로, 새 프로젝트 하나를 처음 등록하는 전체 비용을 평가한 수치가 아니다.', '',
        '### 9.7 원자료·검증·재현', '',
        f'전체 질문·방식의 누락 여부, 실제 전달 원문, 호출 토큰, 채점 및 통계는 '
        f'[최종 검증]({local}verification.json)의 PASS를 확인한 뒤 이 절을 생성했다. '
        f'실험 전 고정한 [프로토콜]({local}protocol.json)과 [분석 계획]({local}analysis_plan.json), '
        f'[최종 집계]({local}summary.json), [문항별 채점]({local}task_scores.jsonl), '
        f'[데이터 목록·해시]({local}data_manifest.json)에서 각 표의 근거를 확인할 수 있다.', '',
        f'공식 배포 버전과 평가 구현은 [자료 조사 기록]({HERE / "research_sources.md"}), '
        f'실행·준비 단계의 예외는 [실행 기록]({local}execution_notes.md)에 남겼다. '
        f'기존 보고서 반영 시에는 이전 실험 수치를 유지하고 이 절·목차 링크와 부록 C의 과거 편집 범위 설명을 반영한다. '
        f'반영 후 생성되는 [문서 변경 기록]({local}report_update.json)과 [문서 검증]({local}report_update_verification.json)으로 '
        f'되돌리기와 보존 여부를 확인할 수 있다.',''])
    return '\n'.join(chunks)


def render_section(out=OUT):
    values=load_verified(out);stats=graph_statistics(values)
    text=render_text(values,stats)
    assert text.count(TITLE)==1 and text.count(ANCHOR)==1
    assert all(f'#### 9.5.{i} {NAMES[d]}' in text for i,d in enumerate(DATASETS,1))
    assert text.count('```')%2==0 and '![' not in text
    return text,values,stats


def atomic_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.part');temp.write_text(text,encoding='utf8');os.replace(temp,path)


def write_section(out=OUT):
    out=Path(out);text,values,stats=render_section(out)
    path=out/SECTION_FILE;atomic_text(path,text)
    dump(out/'report_section09_metadata.json',{'status':'PASS','created_at_utc':now(),
        'section_sha256':sha(path),'source_sha256':sha(Path(__file__)),
        'input_hashes':values['hashes'],'graph_statistics':stats,
        'section_characters':len(text),'report_modified':False})
    return text,values


def insert_section(before,section):
    assert ANCHOR not in before and TITLE not in before, 'Section 9 already exists in baseline'
    edits=[{'name':'contents','old':CONTENTS_OLD,'new':CONTENTS_NEW},
           {'name':'section','old':APPENDIX,'new':section.rstrip()+'\n\n'+APPENDIX},
           {'name':'historical_scope','old':HISTORY_OLD,'new':HISTORY_NEW}]
    result=before
    for edit in edits:
        assert result.count(edit['old'])==1, ('Insertion anchor is not unique',edit['name'])
        result=result.replace(edit['old'],edit['new'],1)
    assert reverse_edits(result,edits)==before
    return result,edits


def reverse_edits(text,edits):
    for edit in reversed(edits):
        assert text.count(edit['new'])==1, ('Reversal anchor is not unique',edit['name'])
        text=text.replace(edit['new'],edit['old'],1)
    return text


def audit_report(out=OUT,report=None):
    out=Path(out);report=Path(report) if report else out.parent.parent/REPORT_NAME
    values=load_verified(out);update=read(out/'report_update.json')
    before_path=out/'history'/REPORT_NAME;before=before_path.read_text(encoding='utf8')
    after=report.read_text(encoding='utf8');section=(out/SECTION_FILE).read_text(encoding='utf8')
    assert section==render_text(values,graph_statistics(values)), 'Report section differs from verified summary rendering'
    assert sha(before_path)==values['protocol']['report_before_sha256']==update['before_sha256']
    assert sha(report)==update['after_sha256'] and digest(section)==update['section_sha256']
    assert update['summary_sha256']==values['hashes']['summary']
    assert update['verification_sha256']==values['hashes']['verification']
    assert reverse_edits(after,update['edits'])==before, 'Historical report content changed'
    expected,expected_edits=insert_section(before,section)
    assert after==expected and update['edits']==expected_edits
    assert after.count(ANCHOR)==1 and section.count('```')%2==0 and '![' not in section
    for i,d in enumerate(DATASETS,1):assert section.count(f'#### 9.5.{i} {NAMES[d]}')==1
    links=re.findall(r'\]\(([^)]+)\)',section)
    checked=[]
    for link in links:
        if link.startswith(('https://','http://','#')):continue
        target=(report.parent/link).resolve()
        if target.name in {'report_update_verification.json'}:continue
        assert target.is_file(), ('Missing section evidence link',str(target));checked.append(str(target))
    result={'status':'PASS','checked_at_utc':now(),'report_sha256':sha(report),
            'report_path':str(report),'before_sha256':sha(before_path),
            'section_sha256':digest(section),'summary_sha256':values['hashes']['summary'],
            'verification_sha256':values['hashes']['verification'],
            'checks':['complete final verified results only','seven full dataset populations',
                      'four arms and same FULL-fit population','final artifacts hash bound',
                      'historical report byte-for-byte recoverable','two insertions and one historical-scope clarification',
                      'seven dataset subsections','balanced example fences and no images','local evidence links exist'],
            'local_links_checked':checked}
    dump(out/'report_update_verification.json',result)
    return result


def apply_to_report(out=OUT,report=None):
    out=Path(out);report=Path(report) if report else out.parent.parent/REPORT_NAME
    section,values=write_section(out)
    before_path=out/'history'/REPORT_NAME
    assert before_path.is_file() and sha(before_path)==values['protocol']['report_before_sha256']
    before=before_path.read_text(encoding='utf8');after,edits=insert_section(before,section)
    current=report.read_text(encoding='utf8')
    assert current in {before,after}, 'Report changed after freeze; reconcile edits before applying section 9'
    if current!=after:atomic_text(report,after)
    dump(out/'report_update.json',{'created_at_utc':now(),'report_path':str(report),
        'before_sha256':sha(before_path),'after_sha256':sha(report),'section_sha256':digest(section),
        'summary_sha256':values['hashes']['summary'],'verification_sha256':values['hashes']['verification'],
        'generator_sha256':sha(Path(__file__)),'edits':edits,
        'scope':'Section 9 and contents row inserted; appendix C historical editing scope clarified. All original content is reversible byte-for-byte; no historical experiment numbers changed.'})
    return audit_report(out,report)


def self_test():
    assert number(None)=='—' and number(1234.56)=='1,234.6'
    assert interval(None)=='산출 불가' and interval([-1.234,2.345])=='[-1.23, 2.35]'
    assert '산출 불가' in contrast_text('x',{'n':1,'score':{'difference_percentage_points':0,'ci95':None}})
    assert '없다' in contrast_text('x',{'n':0,'score':None})
    assert '계산하지 않았다' in fit_table('qasper',{'n_questions':0})
    before='원래 내용 123\n'+CONTENTS_OLD+'\n\n'+APPENDIX+'\n기존 숫자 4.56\n'+HISTORY_OLD+'\n'
    section=ANCHOR+'\n\n'+TITLE+'\n새 설명\n'
    after,edits=insert_section(before,section)
    assert reverse_edits(after,edits)==before and after.index(TITLE)<after.index('## 부록 A.')
    for changed in [before.replace(CONTENTS_OLD,''),before.replace(APPENDIX,''),before+ANCHOR]:
        try:insert_section(changed,section)
        except AssertionError:pass
        else:raise AssertionError('Unsafe insertion was accepted')
    try:require_gate({'provisional':True},{'status':'PASS'},{},{},{})
    except AssertionError:pass
    else:raise AssertionError('Provisional summary was accepted')
    try:require_gate({'provisional':False},{'status':'RUNNING'},{},{},{})
    except AssertionError:pass
    else:raise AssertionError('Unverified summary was accepted')
    from prepare_data import build_document
    class ExampleTokenizer:
        def tokens(self,text):return len(text.split())
    document=build_document(EXAMPLE,ExampleTokenizer())
    assert len(document['nodes'])==2
    assert document['nodes'][0]['id']=='n000001' and document['nodes'][0]['deps']==['n000002']
    assert document['nodes'][0]['preview']==EXAMPLE_PREVIEW and len(EXAMPLE_PREVIEW.split())==12
    # Exercise every rendering branch with artificial values held only in RAM.
    # These values are never saved as benchmark data and never pass load_verified.
    import copy
    fixture={'out':OUT,'summary':{'datasets':{}},'data_manifest':{'datasets':{}},'protocol':{'config':{}}}
    stats={}
    for dataset in DATASETS:
        arms={}
        for index,arm in enumerate(ARMS,1):
            arms[arm]={'n':2,'official':{'score_unrounded':10*index,'components_unrounded':{
                'rouge/rouge1':10*index,'rouge/rouge2':10*index,'rouge/rougeL':10*index}},
                'coverage':1.0,'completed_answers':2,'context_overflow':0,'selector_invalid':0,
                'output_limit':0,'actual_completed_calls':2,
                'usage':{'input_tokens':{'mean':1000+index*100},'peak_input_tokens':{'mean':900+index*100},
                         'query_seconds':{'mean':index,'n':2}}}
        pairs={}
        for label in ['B-A','R0-A','R0-B','A-FULL','B-FULL','R0-FULL']:
            left,right=label.split('-');diff=arms[left]['official']['score_unrounded']-arms[right]['official']['score_unrounded']
            pairs[label]={'n':2,'score':{'difference_percentage_points':diff,'ci95':[diff-1,diff+1]},
                'usage':{'input_tokens':{'savings_vs_FULL_percent':{'estimate':20,'ci95':[19,21]}},
                         'query_seconds':{'difference':-1,'ci95':[-2,0],'n_pairs':2}}}
        cohort={'n_questions':2,'arms':arms,'paired_contrasts':pairs}
        fixture['summary']['datasets'][dataset]={'all_questions':copy.deepcopy(cohort),
                                               'full_fit':cohort,'excluded_from_full_fit':0}
        fixture['data_manifest']['datasets'][dataset]={'raw_rows':2}
        stats[dataset]={'exact_contexts':2,'clusters':2,'question_weighted_mean_tokens':3000,
                        'nodes':4,'linked_nodes':2,'cross_edges':int(dataset=='hotpotqa'),
                        'edges':{'paragraph_continuation':1,'section_heading_mention':1}}
    rendered=render_text(fixture,stats)
    assert rendered.count('#### 9.5.')==7 and rendered.count('| A−FULL |')==7
    assert rendered.count('| B−FULL |')==7 and rendered.count('| R0−FULL |')==7
    assert 'A는 FULL보다 입력' in tradeoff_table(fixture['summary'])
    for link in re.findall(r'\]\(([^)]+)\)',rendered):
        assert link.startswith(('https://','http://','#','/')), ('Standalone link is relative',link)
    assert len(rendered)<25000, ('Section exceeds reading-length guard',len(rendered))
    qasper=fixture['summary']['datasets']['qasper']['full_fit']
    qasper['arms']['R0']['official']['score_unrounded']=40
    qasper['arms']['R0']['usage']['input_tokens']['mean']=100
    assert '관측 최고 점수와 최소 입력이 겹침' in tradeoff_table(fixture['summary'])
    qasper['paired_contrasts']['A-FULL']['usage']['query_seconds'].update(difference=None,ci95=None,n_pairs=0)
    assert '— 산출 불가 (n=0)' in full_comparison_table(qasper)
    qasper['n_questions']=0
    assert '공통 비교 불가' in tradeoff_table(fixture['summary'])
    assert '계산하지 않았다' in dataset_section(2,'qasper',fixture,stats)
    return {'status':'PASS','phase':'self-test','fixture_render_characters':len(rendered),
            'fixture_characters_without_link_targets':len(re.sub(r'\]\([^)]+\)',']',rendered)),
            'scope':'in-memory full rendering, source example, ties, empty cohorts, missing timings, absolute links, reversible insertion and fail-closed guards; no benchmark artifacts created'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['render','apply','audit','self-test']);p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--report',type=Path)
    args=p.parse_args()
    if args.phase=='self-test':result=self_test()
    elif args.phase=='render':
        section,values=write_section(args.out)
        result={'status':'PASS','phase':'render','section':str(args.out/SECTION_FILE),'characters':len(section),'report_modified':False}
    elif args.phase=='apply':result=apply_to_report(args.out,args.report)
    else:result=audit_report(args.out,args.report)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
