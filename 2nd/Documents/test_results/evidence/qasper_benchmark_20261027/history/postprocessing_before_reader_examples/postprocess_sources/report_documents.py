"""Append the verified, complete QASPER experiment as report section 9.

No inference, no partial-result publication, no edits to frozen experiment code.
``render`` writes a standalone section only. ``apply`` also inserts the section,
contents row and reading notice, then audits the report. Historical text stays intact.
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
CONTENTS_NEW = CONTENTS_OLD + '\n| [9. QASPER 데이터셋 실험: A·B·R0·FULL](#document-benchmarks) | |'
READING_ANCHOR = '**읽는 순서:**'
READING_NOTICE = '**추가 일반 문서 실험:** QASPER 전체 984문항에서 A·B·R0·논문 전체(FULL)를 비교한 새 결과는 [9절](#document-benchmarks)에 있으며, 기존 코드 실험 수치와 별도로 읽는다.'
APPENDIX = '<a id="detail"></a>\n\n## 부록 A. 상세 성적과 통계'
EXAMPLE = ('1. Study Setup\nThe experiment is described in 2. Training Method below.\n\n'
           '2. Training Method\nThe selected setting is reported in 3. Main Result below.\n\n'
           '3. Main Result\nThe model uses twelve layers.\n')
EXAMPLE_PREVIEW = '1. Study Setup The experiment is described in 2. Training Method below.'
COUNTS = {'qasper':984}
NAMES = {'qasper':'QASPER'}
METRICS = {'qasper':'F1'}
EXPECTED_METRICS = {'qasper':'f1'}
URLS = {
    'tfidf': 'https://www.sciencedirect.com/science/article/pii/0306457388900210',
    'logtf': 'https://nlp.stanford.edu/IR-book/html/htmledition/sublinear-tf-scaling-1.html',
    'scrolls': 'https://aclanthology.org/2022.emnlp-main.823/',
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
    assert DATASETS==['qasper'] and ARMS==['A','B','R0','FULL'], 'QASPER-only report'
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
        assert len(fitids)==n and d['all_questions']['arms']['FULL']['context_overflow']==0
        assert d['all_questions']['arms']['FULL']['usage']['requested_answer_input_tokens']['max']+protocol['config']['answer_max_tokens']['qasper']<=32768
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
           'analysis_plan':'.json','source_clusters':'.json','input_eligibility':'.json'}
    for name,ext in names.items():
        assert (out/(name+ext)).is_file(), f'Final artifact missing: {name+ext}'
    hashes={name:sha(out/(name+ext)) for name,ext in names.items()}
    values={name:read(out/(name+'.json')) for name in names if names[name]=='.json'}
    require_gate(values['summary'],values['verification'],values['completed'],values['protocol'],hashes)
    tasks=rows(out/'tasks.jsonl')
    assert collections.Counter(t['dataset'] for t in tasks)==collections.Counter(COUNTS)
    assert len({t['task_id'] for t in tasks})==sum(COUNTS.values())
    assert values['data_manifest']['task_count']==len(tasks)
    assert values['data_manifest']['document_count']==273
    assert set(values['data_manifest']['datasets'])=={'qasper'}
    assert values['data_manifest']['datasets']['qasper']['raw_rows']==1726
    eligibility=values['input_eligibility']
    assert eligibility['tasks_sha256']==hashes['tasks']
    assert eligibility['count']==eligibility['full_fit']==984 and eligibility['contexts']==273
    assert {x['task_id'] for x in eligibility['items']}=={t['task_id'] for t in tasks}
    assert len(eligibility['items'])==984 and all(x['fits'] for x in eligibility['items'])
    maximum=values['summary']['datasets']['qasper']['all_questions']['arms']['FULL']['usage']['requested_answer_input_tokens']['max']+values['protocol']['config']['answer_max_tokens']['qasper']
    assert eligibility['max_wrapped_input_plus_output_reservation']==maximum
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
    lines=[fit_table(dataset,fit),'',
        '답변 완료: '+', '.join(f"{a} {allq['arms'][a]['completed_answers']:,}/{allq['arms'][a]['n']:,}개" for a in ARMS)+'.',
        '목록 선택 실패: '+', '.join(f"{a} {allq['arms'][a]['selector_invalid']:,}개" for a in ['A','B'])+'. '+
        '답변 출력 한도 도달: '+', '.join(f"{a} {allq['arms'][a]['output_limit']:,}개" for a in ARMS)+'.','',
        '**동일 질문의 F1 차이 [95% 구간]:** '+
        '; '.join(contrast_text(label.replace('-','−'),allq['paired_contrasts'][label]) for label in ['B-A','R0-A','R0-B'])+'.','']
    if fit['n_questions']:lines.append(full_comparison_table(fit))
    return '\n'.join(lines)


def tradeoff_text(summary):
    cohort=summary['datasets']['qasper']['full_fit'];n=cohort['n_questions']
    if not n:return 'FULL 가능 공통 문항이 없어 비용·점수의 공통 비교를 계산하지 않았다.'
    arms=cohort['arms'];best_score=max(a['official']['score_unrounded'] for a in arms.values())
    best=[a for a in ARMS if abs(arms[a]['official']['score_unrounded']-best_score)<1e-10]
    lowest=min(a['usage']['input_tokens']['mean'] for a in arms.values())
    cheapest=[a for a in ARMS if abs(arms[a]['usage']['input_tokens']['mean']-lowest)<1e-10]
    representative=min(best,key=lambda a:arms[a]['usage']['input_tokens']['mean'])
    cheap=max(cheapest,key=lambda a:arms[a]['official']['score_unrounded'])
    lead=f"이번 관측에서 최고 F1은 **{'/'.join(best)} {number(best_score,2)}점**, 최소 누적 입력은 **{'/'.join(cheapest)} {number(lowest)}토큰/질문**이다. "
    if cheap in best:return lead+'최고 점수와 최소 입력이 겹쳤다. 이 관측만으로 다른 모델·문서에서도 같은 우열이 유지된다고 단정할 수는 없다.'
    delta=best_score-arms[cheap]['official']['score_unrounded'];cost=arms[representative]['usage']['input_tokens']['mean']
    saving=100*(1-lowest/cost) if cost else None
    return lead+f"{cheap}는 {representative}보다 입력이 **{number(saving,1)}% 적은 대신 F1이 {number(delta,2)}점 낮았다.** 차이의 불확실성은 위 구간과 함께 읽어야 한다."


def render_text(values,stats):
    summary=values['summary'];manifest=values['data_manifest'];config=values['protocol']['config']
    result=summary['datasets']['qasper'];allq=result['all_questions'];fit=result['full_fit'];s=stats['qasper']
    total=COUNTS['qasper'];calls=sum(allq['arms'][a]['actual_completed_calls'] for a in ARMS)
    max_reserved=allq['arms']['FULL']['usage']['requested_answer_input_tokens']['max']+config['answer_max_tokens']['qasper']
    local=str(Path(values['out']).resolve())+'/'
    methods=table(['방식','질문이 들어오면 누가 무엇을 고르나?','답변 LLM에 보내는 자료'],[
        ['A','프로그램이 절 제목·미리보기로 목록을 추림 → LLM이 출발 조각 1개 선택 → 같은 문서 연결 1단계 확장','골라진 조각의 실제 원문'],
        ['B','A와 같은 목록·별도 LLM 선택 → 연결을 2단계 확장','골라진 조각의 실제 원문; 이번 자료에서는 같은 논문 안에서만 확장'],
        ['R0','프로그램이 질문과 단독 원문·최대 3단계 연결 묶음의 TF-IDF 유사도로 선택','선택한 단독·묶음 후보의 실제 원문; 선택 LLM 호출 없음'],
        ['FULL','별도 검색·선택 없이 준비','그 질문에 제공된 논문 원문 전부']])
    conditions=table(['고정 항목','설정'],[
        ['모델·전체 한도','Qwen2.5-Coder-7B-Instruct Q5_K_M / 로컬 llama-server / 호출당 32,768토큰'],
        ['A·B·R0 답변 자료','출처 ID·위치 표기까지 최대 1,024토큰; 후보 전체가 들어가지 않으면 건너뜀'],
        ['A·B 선택 목록','최대 24개·2,048토큰 / 선택 출력 최대 32토큰 / 원문 확장 최대 8조각'],
        ['생성·순서','답변 최대 128토큰 / temperature 0·seed 1 / 질문당 방식별 1회 / 네 방식의 24가지 순서를 각각 41번 배치'],
        ['캐시·누적 입력','모델 프롬프트 캐시 비활성화 / 선택 호출과 답변 호출의 입력을 모두 합산']])
    chunks=[ANCHOR,'',TITLE,'',
        f'**논문 원문을 전부 보내는 것보다 필요한 부분을 골라 보내면 얼마나 절약하며, 답변 품질은 어떻게 달라지는가?** '
        f'이를 QASPER의 공개 검증 질문 **{total:,}개 전체**에서 A·B·R0·FULL로 비교했다. '
        f'네 방식 결과 **{total*4:,}개**, 실제 선택·답변 호출 **{calls:,}회**를 평가했다. 사전 연결 점검 호출은 비교에서 제외했다.', '',
        '**1~8절은 코드 실험, 이 절은 일반 문서 실험이다.** 아래 A·B는 코드 색인을 문서용으로 바꾼 방식이며, FULL도 함수 파일이 아니라 제공된 논문 전체다. '
        '기존 코드 실험의 숫자와 합산하지 않는다. 부록 C의 “새 LLM 실험 없음”은 그 부록에 적힌 과거 문서 정리의 범위이며, 이번 실행 근거는 9.7절에 따로 남겼다.', '',
        '### 9.1 왜 QASPER를 골랐고, 어떤 연구를 따랐나?', '',
        f'QASPER는 연구 논문을 읽고 질문에 답하는 과제이며 [RAPTOR 논문]({URLS["raptor"]})에서도 평가했다. '
        '답은 짧은 설명, yes/no, 또는 답할 수 없음일 수 있다. 논문에서 사용한 과제 하나에 집중하면서, '
        '**원문 전체가 모델 한도에 들어가므로 FULL을 실제 호출한 비교**를 할 수 있어 선택했다. 성능 결과를 보고 유리한 질문만 뽑은 것이 아니다.', '',
        f'판본은 [SCROLLS]({URLS["scrolls"]})가 공개한 **QASPER validation**이다. 원자료 '
        f'**{manifest["datasets"]["qasper"]["raw_rows"]:,}행**의 같은 질문 ID·여러 참조 답안을 묶으면 '
        f'**{total:,}개 질문, {s["exact_contexts"]:,}개 고유 원문**이다. 전부 사용했고 원문을 요약본으로 대체하지 않았다. '
        '질문과 논문 경계를 분리한 뒤 다시 합쳐 원래 입력이 복원되는지도 검증했다.', '',
        f'R0의 TF-IDF는 새로 만든 지표가 아니다. [Salton·Buckley의 단어 가중치 연구]({URLS["tfidf"]})와 '
        f'[로그 TF 설명]({URLS["logtf"]})처럼 단어 빈도를 벡터로 바꿔 비교하는 기존 정보검색 방법을 적용했다. '
        '이번 구현은 `TF=1+ln(횟수)`, `IDF=ln((후보 수+1)/(그 단어가 있는 후보 수+1))+1`을 곱하고 길이를 1로 정규화해 질문 벡터와 내적한다. '
        'IDF는 해당 논문의 원문 후보들로만 계산한다. 계산 예제는 1.5절을 참고한다.', '',
        '**RAPTOR 재현 실험은 아니다.** RAPTOR의 임베딩·군집·재귀 요약 트리를 만들지 않았고, RF·RH·C·H도 실행하지 않았다. '
        'RAPTOR 논문의 일반 검색 예산은 2,000토큰이며 이번 선택 자료 예산은 1,024토큰이다. '
        '문서 분할·제목 연결·미리보기와 로컬 모델 설정은 이 프로젝트의 통제 실험 규칙이므로 논문 수치와 직접 우열을 비교하지 않는다.', '',
        '### 9.2 원문에서 색인을 만들고 LLM에게 전달하기까지', '',
        '**우리 프로그램이 질문·정답을 보지 않고 자료를 만든다.** 논문 원문을 문단 단위로 읽고, 긴 문단은 실제 모델 기준 최대 256토큰 조각으로 나눈다. '
        '각 조각에는 ID·문서 ID·절 제목·문자 위치·앞 12단어를 저장한다. 원문 모든 문자는 보존하며, 위치로 해당 원문을 다시 읽을 수 있다. '
        '**12단어 미리보기는 원문 일부다.** 따라서 본문 없는 함수 주소록과 같은 색인이라고 부르면 안 된다. 이 준비 과정에 LLM 요약 호출은 없다.', '',
        methods,'',
        '**프로그램이 원문 전체를 처리한 것과 답변 LLM이 전체를 읽은 것은 다르다.** A·B의 선택 LLM은 목록을 보고, 답변 LLM은 예산 안에 담긴 원문만 본다. '
        'R0도 가중치를 LLM에 주어 파일을 읽게 하는 것이 아니라, 프로그램이 고른 실제 원문을 보낸다.', '',
        f'연결은 **긴 한 문단을 나눈 조각끼리 이어지는 관계**가 {s["edges"].get("paragraph_continuation",0):,}개, '
        f'같은 논문 안의 고유한 두 단어 이상 절 제목을 그대로 언급한 관계가 {s["edges"].get("section_heading_mention",0):,}개다. '
        f'다른 문서 연결은 **{s["cross_edges"]:,}개**다. 실제 `import`나 의미를 추론한 연결이 아니며, 서로 다른 문단을 단순히 가깝다고 잇지도 않는다. '
        '**이번 B는 주로 같은 긴 문단에서 한 단계 더 읽는 방식이다. 다른 파일을 따라가는 장점은 검증하지 못한다.**', '',
        '**작은 예시:** 다음은 같은 문서의 절 제목 연결을 보여 주기 위한 예시이며 평가 자료는 아니다.', '',
        '```text\n'+EXAMPLE+'```','',
        f'첫 목록 항목은 `ID=n000001`, `문서ID=d0001`, `절=1. Study Setup`, `미리보기="{EXAMPLE_PREVIEW}"`다. '
        '프로그램은 제목 언급으로 `n000001 → n000002 → n000003`을 잇는다. '
        '**A·B가 첫 조각을 골랐고 예산에 들어간다면**, A는 1·2번 원문, B는 1·2·3번 원문을 보낼 수 있다. '
        '긴 문단을 세 조각으로 나눈 연결에서도 출발점과 확장 깊이에 따라 이와 같은 범위 차이가 생긴다. 연결 없는 같은 조각을 고르면 범위는 같다.', '',
        'R0에는 단독 조각과 최대 3단계 연결 묶음이 검색 후보로 등록된다. '
        '출처 ID·문서 ID·문자 위치 표기와 원문을 합친 후보 문자열의 TF-IDF를 질문과 비교해 높은 순서로 담는다. '
        '**단독 후보가 선택되면 단독 원문, 묶음 후보가 선택되면 묶음 원문**을 보낸다. 완전 중복은 생략하지만 부분 중복은 남을 수 있다. '
        'A·B·R0 모두 후보를 중간에서 잘라 넣지는 않으며, 필요한 근거를 반드시 고른다는 보장은 없다.', '',
        '### 9.3 같은 조건에서 FULL을 실제 실행했나?', '',conditions,'',
        f'**FULL은 {fit["n_questions"]:,}개 질문 모두에서 제공 논문 원문 전부를 실제 전송했다.** '
        f'지시문·질문·원문·출력 예약을 합친 최대 길이는 **{number(max_reserved,0)}토큰 < 32,768토큰**이다. '
        '앞뒤만 남기는 자르기는 없었다. 모든 문항이 들어가므로 아래 품질·비용의 분모는 네 방식 모두 같은 984개다. '
        f'실행 전 문항별 [전체 입력 가능성 검사]({local}input_eligibility.json)와 실행 후 호출 기록을 함께 확인했다.', '',
        '**누적 입력**은 선택·답변 호출을 합친 토큰이고, **최대 호출 입력의 평균**은 질문마다 가장 큰 한 번의 입력을 고른 뒤 평균한 값이다. '
        '전자는 처리 비용, 후자는 한 번에 차지하는 컨텍스트를 비교하는 데 쓰인다. 두 호출의 합을 한 호출의 컨텍스트 크기로 보지 않는다. '
        '초과 시에는 미전송·0비용으로 기록하도록 설계했지만 이번 FULL에는 초과가 없었다. 따라서 실패의 0비용을 절약으로 계산한 결과가 아니다.', '',
        '질의 시간에는 검색·선택·원문 구성·답변이 들어가고 모델 시작과 사전 자료 구축·로딩은 빠진다. '
        '중간 복구 때문에 온전한 시간을 잴 수 없는 질문은 시간 평균에서만 제외해 측정 수를 표시한다. '
        'A·B의 목록 선택 실패는 빈 원문으로 답변을 요청하고 실제 출력으로 채점한다. 출력 한도에 닿은 답도 나온 부분 그대로 채점하며 재질문으로 고치지 않았다.', '',
        '### 9.4 점수와 차이를 어떻게 읽나?', '',
        '**F1은 정답률이 아니다.** 답변과 참조 답안을 소문자화하고 구두점·영어 관사·공백을 정규화한 뒤, 일치하는 단어의 정밀도와 재현율의 조화평균을 구한다. '
        '한 질문에 여러 참조 답안이 있으면 가장 높은 F1을 쓰고 질문 전체를 평균해 0~100으로 표시한다. '
        f'[공식 SCROLLS 평가 구현]({HERE / "official_sources/scrolls/metrics/f1.py"})을 따르며 LLM 심판은 사용하지 않았다.', '',
        f'같은 논문에 여러 질문이 있으므로 질문을 모두 독립 표본으로 보지 않는다. 앞뒤 공백 변형을 합친 **{s["clusters"]:,}개 원문 묶음** 단위로 '
        '같은 질문의 방식별 결과를 함께 10,000번 재표집해 차이의 95% 구간을 계산했다. '
        '구간은 불확실성을 보여 주는 설명용이며, 0을 포함하지 않는다는 이유만으로 여러 비교를 보정한 확증 검정이라고 주장하지 않는다.', '',
        '**FULL 대비 표:** 점수 차이가 음수면 F1이 낮고, 입력 절감률이 양수면 적은 토큰을 썼고, 시간 차이가 음수면 빨랐다는 뜻이다. '
        '모든 대괄호는 95% 구간이며, 시간 차이는 양쪽 시간이 모두 있는 질문 쌍만 쓴다. 점수 차이 단위는 F1 0~100 척도의 점이다.', '',
        '### 9.5 QASPER 전체 984문항의 결과', '',
        dataset_section(1,'qasper',values,stats),'',
        '### 9.6 무엇이 유리했고, 어디까지 해석할 수 있나?', '',
        tradeoff_text(summary),'',
        '토큰 절감과 품질 개선은 별개다. R0는 선택용 LLM 호출이 없고 A·B는 목록 선택 호출이 추가되지만, '
        '최종 효율은 실제 고른 원문·답변 품질까지 함께 봐야 한다. B가 A보다 좋아도 이번 자료에서 다른 파일을 찾는 능력을 입증한 것은 아니다. '
        '또한 이 단일 데이터셋·한 로컬 코딩 모델·한 번의 생성·선택 자료 1,024토큰 결과를 모든 코드·문서와 모델에 일반화하지 않는다.', '',
        '**이번 비교로 알 수 없는 것:** 정답 근거 위치를 공통 기준으로 평가하지 않았으므로 이전 코드 실험의 “필요 원문 포함률”은 산출하지 않았다. '
        '연결 수나 원문 길이가 그 비율을 대신하지 않는다. 모든 FULL이 들어갔으므로 컨텍스트 초과 문서에서의 처리율 우위도 이번 결과로 입증하지 않는다.', '',
        f'**준비 비용:** 새 실행에서 원문 분할·목록·관계 자료 생성 및 저장에 **{number(manifest["preparation_seconds"],2)}초**가 걸렸고 LLM 요약 호출은 없었다. '
        'R0의 TF-IDF 구성과 자료 로딩은 질의 시간 바깥에서 수행해 별도 기록했다. '
        '따라서 질의 시간 표만으로 새 프로젝트 등록부터 답변까지의 전체 비용을 판단해서는 안 된다.', '',
        '### 9.7 원자료·검증·재현', '',
        f'[최종 검증]({local}verification.json)의 PASS 뒤에만 이 절을 생성한다. '
        f'[프로토콜]({local}protocol.json), [분석 계획]({local}analysis_plan.json), [최종 집계]({local}summary.json), '
        f'[문항별 채점]({local}task_scores.jsonl), [데이터 목록·해시]({local}data_manifest.json)에서 수치를 확인할 수 있다. '
        f'[논문 조사]({HERE / "research_papers.md"})·[배포본 조사]({HERE / "research_sources.md"})·'
        f'[실행 기록]({local}execution_notes.md)·[자료 로딩 기록]({local}asset_load_times.jsonl)에 설정과 예외를 남긴다.', '',
        f'기존 보고서에는 이 절·목차·읽기 안내만 추가하고 기존 본문과 부록은 보존한다. 반영 후 생성되는 '
        f'[문서 변경 기록]({local}report_update.json)과 [문서 검증]({local}report_update_verification.json)으로 정확히 되돌릴 수 있는지 확인한다.','']
    return '\n'.join(chunks)


def render_section(out=OUT):
    values=load_verified(out);stats=graph_statistics(values)
    structure=stats['qasper']
    assert structure['exact_contexts']==273 and structure['nodes']==6018 and structure['cross_edges']==0
    assert structure['edges']=={'paragraph_continuation':9504,'section_heading_mention':41}
    text=render_text(values,stats)
    assert text.count(TITLE)==1 and text.count(ANCHOR)==1
    assert text.count('### 9.5 QASPER 전체 984문항의 결과')==1
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
           {'name':'reading_notice','old':READING_ANCHOR,'new':READING_NOTICE+'\n\n'+READING_ANCHOR}]
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
    assert section.count('### 9.5 QASPER 전체 984문항의 결과')==1
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
            'checks':['complete final verified results only','QASPER all 984 questions and 273 contexts',
                      'four arms and same FULL-fit population','final artifacts hash bound',
                      'historical report byte-for-byte recoverable','section, contents row and reading notice inserted; historical body and appendices preserved',
                      'QASPER-only result section','balanced example fences and no images','local evidence links exist'],
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
        'scope':'QASPER section 9, contents row and reading notice inserted. All original body and appendix content is preserved and reversible byte-for-byte; no historical experiment numbers changed.'})
    return audit_report(out,report)


def self_test():
    assert number(None)=='—' and number(1234.56)=='1,234.6'
    assert interval(None)=='산출 불가' and interval([-1.234,2.345])=='[-1.23, 2.35]'
    assert '산출 불가' in contrast_text('x',{'n':1,'score':{'difference_percentage_points':0,'ci95':None}})
    assert '없다' in contrast_text('x',{'n':0,'score':None})
    assert '계산하지 않았다' in fit_table('qasper',{'n_questions':0})
    before='원래 내용 123\n'+READING_ANCHOR+' 기존 안내\n'+CONTENTS_OLD+'\n\n'+APPENDIX+'\n기존 숫자 4.56\n'
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
    assert len(document['nodes'])==3
    assert document['nodes'][0]['id']=='n000001' and document['nodes'][0]['deps']==['n000002']
    assert document['nodes'][1]['deps']==['n000003'] and document['nodes'][2]['deps']==[]
    assert len({n['doc_id'] for n in document['nodes']})==1
    assert document['nodes'][0]['preview']==EXAMPLE_PREVIEW and len(EXAMPLE_PREVIEW.split())==12
    # Exercise every rendering branch with artificial values held only in RAM.
    # These values are never saved as benchmark data and never pass load_verified.
    import copy
    fixture={'out':OUT,'summary':{'datasets':{}},'data_manifest':{'datasets':{},'preparation_seconds':50},
             'protocol':{'config':{'answer_max_tokens':{'qasper':128}}}}
    stats={}
    for dataset in DATASETS:
        arms={}
        for index,arm in enumerate(ARMS,1):
            arms[arm]={'n':2,'official':{'score_unrounded':10*index,'components_unrounded':{
                'rouge/rouge1':10*index,'rouge/rouge2':10*index,'rouge/rougeL':10*index}},
                'coverage':1.0,'completed_answers':2,'context_overflow':0,'selector_invalid':0,
                'output_limit':0,'actual_completed_calls':2,
                'usage':{'input_tokens':{'mean':1000+index*100},'peak_input_tokens':{'mean':900+index*100},
                         'query_seconds':{'mean':index,'n':2},'requested_answer_input_tokens':{'max':20000}}}
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
    assert rendered.count('### 9.5 QASPER')==1 and rendered.count('| A−FULL |')==1
    assert rendered.count('| B−FULL |')==1 and rendered.count('| R0−FULL |')==1
    assert 'A는 FULL보다 입력' in tradeoff_text(fixture['summary'])
    assert not any(name in rendered for name in ['QMSum','NarrativeQA','QuALITY','HotpotQA','MuSiQue','MultiFieldQA'])
    for link in re.findall(r'\]\(([^)]+)\)',rendered):
        assert link.startswith(('https://','http://','#','/')), ('Standalone link is relative',link)
    assert len(rendered)<13000, ('Section exceeds reading-length guard',len(rendered))
    qasper=fixture['summary']['datasets']['qasper']['full_fit']
    qasper['arms']['R0']['official']['score_unrounded']=40
    qasper['arms']['R0']['usage']['input_tokens']['mean']=100
    assert '최고 점수와 최소 입력이 겹쳤다' in tradeoff_text(fixture['summary'])
    qasper['paired_contrasts']['A-FULL']['usage']['query_seconds'].update(difference=None,ci95=None,n_pairs=0)
    assert '— 산출 불가 (n=0)' in full_comparison_table(qasper)
    qasper['n_questions']=0
    assert '공통 비교를 계산하지 않았다' in tradeoff_text(fixture['summary'])
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
