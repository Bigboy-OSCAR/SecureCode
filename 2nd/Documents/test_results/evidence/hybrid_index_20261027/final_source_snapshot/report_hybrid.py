"""Add the verified H experiment without removing earlier report evidence."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True
import experiment_hybrid as exp

PREFIX = 'evidence/hybrid_index_20261027'


def count(x):
    return str(round(x)) if abs(x-round(x)) < 1e-8 else f'{x:.2f}'


def interval(values, digits=1):
    return ' ~ '.join(f'{x:+.{digits}f}' for x in values)


def sections(s):
    fresh = s['populations']['all96']
    h = fresh['H']; diag = s['hybrid_diagnostics']
    full = s['historical']['FULL']['tokens']['total']
    parts = ['<a id="hybrid"></a>\n\n## 8. 추가 실험 — TF-IDF와 작은 색인을 결합한 H\n\n',
        (exp.OUT/'report_materials/design.md').read_text(),
        '### 8.2 새로 실행한 세 방식의 정답과 원문 포함률\n\n',
        '| 방식 | 정답 / 96문제 | 정답률 | 필요한 원문 평균 포함률 | 필요한 원문을 모두 포함한 비율 | 질문당 시간 |\n|---|---:|---:|---:|---:|---:|\n']
    for a in ['B','R0','H']:
        m=fresh[a]['metrics']
        parts.append(f"| {a} | {count(m['question_equivalent_correct'])} | {100*m['accuracy']:.1f}% | {100*m['raw_evidence_recall']:.1f}% | {100*m['all_raw_evidence']:.1f}% | {m['mean_query_seconds']:.2f}초 |\n")
    parts.append('\n정답 수는 질문마다 3회 실행한 점수를 평균한 뒤 96문제에 합한 값이다. 반복 실행을 서로 다른 288문제로 세지 않는다. 시간은 각 질문의 3회 중앙값을 구한 뒤 평균했다. **원문 포함률은 답에 필요한 함수·상수의 고유 항목이 실제 답변 입력에 들어간 비율**이며, 단독·묶음 여부와 관계없이 세고 같은 항목을 중복 계산하지 않는다. 여기서 필요한 항목은 각 질문의 기준 자료에 사전에 지정한 목록을 뜻한다. 작은 목록에 이름만 나타난 것은 원문을 포함한 것으로 세지 않는다.\n\n')
    rep=s['historical_control_reproduction']
    parts.append(f"기존 큰 파일 기록과도 대조했다. 같은 질문·반복의 288쌍 중 B는 원문 입력이 {rep['B']['same_context']}쌍, 최종 출력 문자열이 {rep['B']['same_answer']}쌍 같았다. R0는 각각 {rep['R0']['same_context']}쌍, {rep['R0']['same_answer']}쌍 같았다. 아래 H의 직접 비교에는 이번에 새로 측정한 B·R0를 사용한다.\n\n")
    parts.append('### 8.3 파일 하나 전체와 비교한 입력 토큰\n\n')
    parts.append('**선택 호출과 답변 호출의 입력을 모두 합산**했다. 여기서 토큰은 실제 LLM 토크나이저가 센 길이이며, TF-IDF 계산에서 추출한 단어 수나 가중치 개수와 구분한다. 아래의 원문 토큰에는 원문 조각의 출처·import 표기도 포함되며, 전체 호출 입력에는 질문·지시문·대화 형식도 들어간다. ‘최대 호출’은 질문마다 두 호출 중 큰 입력을 고른 값의 평균이다. 평균값은 소수 첫째 자리로 반올림해 표시했다.\n\n')
    parts.append('| 방식·실행 시점 | 선택 호출 입력 | 답변용 원문 | 답변 호출 입력 | 질문당 누적 입력 | 최대 호출 입력 평균 | 파일 전체 대비 누적 절감 |\n|---|---:|---:|---:|---:|---:|---:|\n')
    for a,session,data in [('A','기존',s['historical']['A']),('B','이번',fresh['B']),('R0','이번',fresh['R0']),('H','이번',h),('파일 전체','기존',s['historical']['FULL'])]:
        t=data['tokens']
        parts.append(f"| {a} · {session} | {t['selector']:.1f} | {t['context']:.1f} | {t['answer']:.1f} | {t['total']:.1f} | {t['peak']:.1f} | {100*(1-t['total']/full):.1f}% |\n")
    t=h['tokens']
    parts.append(f"\nH의 작은 목록 본문은 평균 **{t['index']:.1f}토큰**이고, 선택 호출 전체는 **{t['selector']:.1f}토큰**이다. 따라서 ‘원문만 {t['context']:.1f}토큰’이라는 수치를 H의 전체 비용으로 읽으면 안 된다. 선택 호출 **{t['selector']:.1f}토큰**과 답변 호출 **{t['answer']:.1f}토큰**을 더한 누적 입력은 **약 {t['total']:.1f}토큰**이다. H의 최대 호출 입력 평균은 8,192토큰 컨텍스트의 **{100*t['peak']/8192:.2f}%**이고, 출력 자리는 별도로 필요하다. 평균 출력은 H {t['output']:.1f}토큰, B {fresh['B']['tokens']['output']:.1f}토큰, R0 {fresh['R0']['tokens']['output']:.1f}토큰이다.\n\n")
    parts.append('비용 관계를 식으로 쓰면 **H의 총 입력 = 선택 호출 입력 + 답변 호출 입력**, **R0의 총 입력 = 답변 호출 입력**이다. 따라서 H가 R0보다 적게 쓰려면, 줄어든 답변 호출 입력이 새로 추가한 선택 호출 입력보다 커야 한다. 목록이 작다는 사실만으로 총 입력 절약이 정해지지는 않는다.\n\n')
    parts.append(f"실측 평균을 대입하면, R0보다 줄어든 답변 호출 입력은 약 **{fresh['R0']['tokens']['answer']-t['answer']:.1f}토큰**이다. 여기서 새 선택 호출의 **{t['selector']:.1f}토큰**을 지불하므로, 순절감은 약 **{fresh['R0']['tokens']['total']-t['total']:.1f}토큰**, 즉 **{s['comparisons']['H-R0']['cost']['total']['reduction_pct']:.1f}%**가 된다. 원문 길이만 보면 {s['comparisons']['H-R0']['cost']['context']['reduction_pct']:.1f}% 감소했지만, 이 비율을 총 입력 절감률로 쓰면 선택 비용이 빠진다.\n\n")
    prep=exp.read(exp.OUT/'preparation.json')
    session=next(exp.read(p) for p in exp.OUT.glob('session_*.json') if not exp.read(p)['dev'])
    parts.append(f"사전 자연어 요약을 만들기 위한 LLM 호출은 **0회**다. 기존 원문·참조 자료를 재사용한 뒤, 7개 프로젝트(평가 6 + 연습 1)의 작은 메타데이터 목록 생성에 {prep['metadata_seconds']:.3f}초, 본 평가 시작 전 TF-IDF 벡터 준비에 {sum(session['vector_build_seconds'].values()):.3f}초가 들었다. 이 값은 기존 파싱·원문 구축 비용을 포함하지 않으므로 ‘프로젝트 전체를 처음 색인하는 시간’으로 해석할 수 없다. 원문·색인은 로컬에 계속 저장되며, 입력 토큰 감소가 디스크 저장량 감소를 뜻하지는 않는다.\n\n")
    parts.append('### 8.4 차이의 크기와 불확실성\n\n| 비교 | 정답률 차이 | 95% 구간 | 보정 p값 | H가 더 맞힘 / 덜 맞힘 / 같음 |\n|---|---:|---|---:|---|\n')
    for base in ['R0','B']:
        c=s['comparisons']['H-'+base]
        parts.append(f"| H − {base} | {c['delta_pp']:+.2f}%p | {interval(c['ci95_pp'])}%p | {c['holm_p_two_quality_contrasts']:.5f} | {c['win']} / {c['loss']} / {c['tie']}문제 |\n")
    parts.append('\n| 비교 기준 | H의 누적 입력 절감률 [95% 구간] | H의 최대 호출 입력 절감률 [95% 구간] | H의 시간 차이 [95% 구간] |\n|---|---|---|---|\n')
    for base in ['R0','B']:
        c=s['comparisons']['H-'+base];cost=c['cost']
        parts.append(f"| {base} | {cost['total']['reduction_pct']:+.1f}% [{interval(cost['total']['ci95_pct'])}%] | {cost['peak']['reduction_pct']:+.1f}% [{interval(cost['peak']['ci95_pct'])}%] | {c['latency_delta_seconds']:+.2f}초 [{interval(c['latency_ci95_seconds'],2)}초] |\n")
    parts.append('\n절감률의 양수는 H가 더 적게 썼다는 뜻이고, 시간 차이의 양수는 H가 더 오래 걸렸다는 뜻이다. **누적 입력 절감과 한 번에 쓰는 컨텍스트 절감은 서로 다른 지표**다. 95% 구간은 6개 프로젝트를 묶음 단위로 재표집한 46,656가지 조합에서 계산했다. 정답률의 p값은 64가지 프로젝트 부호 반전과 두 비교의 Holm 보정을 적용했다. 프로젝트가 6개뿐이므로 탐색적 결과이며, 차이를 확정하지 못했다고 두 방식이 동등하거나 H의 정확도가 유지된다고 입증되는 것은 아니다.\n\n')
    parts.append('이 검정의 해상도도 제한된다. 프로젝트 6개의 부호 조합은 `2⁶ = 64`개이므로 양측 p값의 최솟값은 `2/64 = 0.03125`다. 두 비교에 Holm 보정을 하면 최소 보정값도 `0.0625`이므로, 이번 설계의 5% 기준으로 유의성을 확정할 수는 없다. 효과 크기와 구간을 탐색적으로 읽고, 더 많은 독립 프로젝트에서 재검증해야 한다.\n\n')
    parts.append('### 8.5 어디서 필요한 근거가 빠졌나?\n\n')
    parts.append('| H의 단계 | 필요한 항목의 평균 포함률 | 필요한 항목을 모두 가진 실행 / 288 |\n|---|---:|---:|\n')
    parts.append(f"| LLM에게 보여 준 작은 목록 | {100*diag['index_required_recall']:.1f}% | {diag['index_all_required_calls']} |\n")
    hs=[r for r in exp.audit.rows(exp.OUT/'results.jsonl') if r['arm']=='H']
    tasks={t['id']:t for t in exp.read(exp.OUT/'tasks.json')}
    requested_all=sum(set(tasks[r['task_id']]['required_uris']) <= set(r['requested_uris']) for r in hs)
    parts.append(f"| LLM이 읽도록 지정한 항목 | {100*diag['requested_required_recall']:.1f}% | {requested_all} |\n")
    parts.append(f"| 실제 답변 입력에 담긴 원문 | {100*diag['raw_required_recall']:.1f}% | {diag['raw_all_required_calls']} |\n")
    parts.append(f"\nH는 평균 {diag['mean_index_items']:.1f}개 항목을 보여 주고, {diag['mean_requested_symbols']:.1f}개를 요청받아 {diag['mean_delivered_symbols']:.1f}개의 원문을 보냈다. 288회 중 선택 규칙 위반·빈 선택 또는 선택 호출 실패는 {diag['invalid_selection_calls']}회, 지정된 원문이 1,024토큰을 넘어 일부 빠진 실행은 {diag['source_budget_rejected_calls']}회였다. 목록 작성 중 512토큰 한도로 적어도 한 행을 제외한 실행은 {diag['index_budget_rejected_calls']}회다. 필요한 원문을 모두 보낸 {diag['raw_all_required_calls']}회 중 정답은 {diag['correct_with_all_raw']}회였다. **목록에 없어서 못 고른 경우, 목록에는 있었지만 안 고른 경우, 원문을 갖고도 답을 틀린 경우를 구분**해야 한다.\n\n")
    parts.append((exp.OUT/'report_materials/interpretation.md').read_text())
    parts.append('### 8.8 원자료와 검증\n\n')
    parts.append(f"[고정한 실험 계획]({PREFIX}/protocol.json) · [사전 분석 계획]({PREFIX}/analysis_plan.json) · [질문별 실제 결과]({PREFIX}/results.jsonl) · [모든 LLM 요청과 응답]({PREFIX}/model_calls.jsonl) · [집계 결과]({PREFIX}/summary.json) · [독립 재계산 검증]({PREFIX}/verification.json) · [재현 절차]({PREFIX}/reproduce.md)\n\n")
    parts.append(f"새 모델 호출은 평가용 1,440회(B 576 + R0 288 + H 576), 연습용 40회, 준비 응답 2회로 총 **{s['new_model_calls']:,}회**다. H의 선택 응답이 규칙을 어긴 경우도 두 번째 답변 호출과 그 입력을 포함해 집계했다. 파일 해시·실행 순서·원문 재구성·토큰·채점·통계를 기록과 대조했으며, 외부 기관의 검증이나 실제 독자를 대상으로 한 이해도 시험을 뜻하지는 않는다.\n\n")
    return ''.join(parts)


def augment(text):
    out=exp.OUT
    exp.validate(out)
    s=exp.read(out/'summary.json');verification=exp.read(out/'verification.json')
    assert verification['status']=='PASS' and verification['summary_sha256']==exp.v1.sha(out/'summary.json')
    previous=(out/'history'/exp.REPORT.name).read_text()
    assert text==previous, 'Reconcile the previous report before adding the hybrid experiment'
    edits=[]
    def replace(old,new):
        nonlocal text
        assert text.count(old)==1, (old,text.count(old))
        text=text.replace(old,new,1);edits.append(dict(old=old,new=new))
    replace('검색 결과의 적중률과 구분해야 하며, 보안 취약점 탐지 성능을 측정한 것은 아니다.', 'A·B·H에서는 원문 선택 절차가 실패하면 최종값과 관계없이 오답으로 평가했다. 검색 결과의 적중률과 구분해야 하며, 보안 취약점 탐지 성능을 측정한 것은 아니다.')
    replace('## 1. 일곱 방식의 원리와 실제 색인 예시','## 1. 여덟 방식의 원리와 실제 색인 예시')
    replace('[1. 일곱 방식의 원리와 실제 색인 예시]','[1. 여덟 방식의 원리와 실제 색인 예시]')
    replace('### 1.9 파일 전체 입력과 일곱 방식의 전달 범위','### 1.9 파일 전체 입력과 여덟 방식의 전달 범위')
    replace('**A·B·R0의 준비 자료는 파싱·규칙 계산으로 만들고,','**A·B·R0·H의 준비 자료는 파싱·규칙 계산으로 만들고,')
    old='| 원문 검색(R0) ↔ 함수 요약(RF)'
    replace(old,'| 원문 검색(R0) ↔ TF-IDF·색인 결합(H) | 검색한 원문을 바로 보내는 대신 작은 목록으로 다시 고르면, 추가 선택 비용을 포함하고도 입력을 줄일 수 있는가? |\n'+old)
    old='| 파일 하나 전체 | 파일 경로만 제공;'
    replace(old,'| H | R0의 검색 자료 + 본문 없는 함수·상수 목록 | 목록에서 LLM이 지정한 개별 원문만 전달; 자동 참조 확장 없음 |\n'+old)
    old='여러 호출의 입력 합계는 총 처리량이고,'
    replace(old,'H도 작은 목록을 읽는 선택 호출과 지정한 원문을 읽는 답변 호출의 두 번이다. '+old)
    replace('<a id="index-build"></a>',(out/'report_materials/method.md').read_text()+'<a id="index-build"></a>')
    old='| **파일 전체** | 검색 전용 색인 불필요 | 없음 |'
    replace(old,'| **H — TF-IDF·색인 결합** | R0 자료 + 본문 없는 함수·상수 메타데이터 목록 | 없음 |\n'+old)
    old='### 2.4 실제 코드는 무엇을 저장하고, 무엇을 메모리에 준비하나?'
    replace(old,'H도 질문이 들어와야 TF-IDF 순위, 보여 줄 목록, LLM의 원문 선택을 정할 수 있다. 버튼 단계에서는 검색 자료와 목록의 재료만 준비한다.\n\n'+old)
    old='| TF-IDF 가중치와 후보 벡터 |'
    replace(old,'| H의 본문 없는 메타데이터 목록 | `symbol_metadata(nodes)`가 파싱된 함수·상수에서 추출 | 이번 추가 실험의 `symbol_metadata.json`에 저장. 질문마다 이 중 일부만 표시한다. |\n'+old)
    replace('## 7. 목적에 따른 판단과 한계','## 7. 기존 일곱 방식의 판단과 한계\n\n이 절은 10월 24~25일에 실행한 기존 일곱 방식의 판단이다. 추가한 H와 새 B·R0 비교는 [8절](#hybrid)에서 별도로 판단한다.')
    replace('<a id="detail"></a>',sections(s)+'<a id="detail"></a>')
    replace('| [7. 목적에 따른 판단과 한계](#decision) | |','| [7. 기존 일곱 방식의 판단과 한계](#decision) | |\n| [8. 추가 실험: TF-IDF·색인 결합 H](#hybrid) | |')
    replace('**읽는 순서:** 결과를 먼저 보려면 [4절](#results) → [5절](#cost) → [7절](#decision)을 읽으면 된다. 방식과 배경부터 이해하려면 1절부터 순서대로 읽는다.',
        '**읽는 순서:** 새 결합 방식의 결과는 [8절](#hybrid), 원리는 [1.11절](#hybrid-method)에서 읽는다. 기존 일곱 방식의 비교는 [4절](#results) → [5절](#cost) → [7절](#decision), 배경 개념은 1절부터 읽으면 된다. **4~7절의 표는 기존 실험값을 보존했고, 새로 실행한 B·R0·H 결과는 8절에 모았다.**')
    old='**파일 하나 전체와 비교해 얻은 것과 남은 대가**'
    replace(old,(out/'report_materials/opening.md').read_text()+'\n'+old)
    exp.v1.dump(out/'report_edits.json',dict(base_report_sha256=exp.v1.sha(out/'history'/exp.REPORT.name),edits=edits))
    exp.v1.dump(out/'report_generation.json',dict(generated_at_utc=exp.audit.now(),summary_sha256=exp.v1.sha(out/'summary.json'),
        verification_sha256=exp.v1.sha(out/'verification.json'),generator_sha256=exp.v1.sha(__file__),
        materials={str(p.relative_to(out)):exp.v1.sha(p) for p in sorted((out/'report_materials').glob('*.md'))}))
    return text
