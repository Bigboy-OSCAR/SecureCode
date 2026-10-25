"""Append verified large-file results to the existing Korean Markdown report."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_large as exp
from report_r0 import table
from report_ab import pct, ncorrect, CATEGORIES

NAMES={'A':'현재 색인(A)','B':'파일 간 확장(B)','R0':'원문 검색(R0)','FULL':'파일 하나 전체'}


def build(out):
    s,v=exp.read(out/'summary.json'),exp.read(out/'verification.json')
    assert s['status']=='COMPLETE' and v['status']=='PASS'
    assert v['source_hashes']['summary.json']==exp.original.sha(out/'summary.json')
    pop=s['by_population']['all96'];m=pop['metrics'];t=pop['token_metrics'];old=s['historical_small']
    files=[f for f in s['corpus']['files'] if f['project'].startswith('eval_')]
    min_tokens,max_tokens=min(f['large_tokens'] for f in files),max(f['large_tokens'] for f in files)
    min_lines,max_lines=min(f['large_lines'] for f in files),max(f['large_lines'] for f in files)
    min_added,max_added=min(f['added_functions'] for f in files),max(f['added_functions'] for f in files)
    stable=all(x['different_output_questions']==0 for x in m.values())
    main=table(['지표',*[NAMES[a] for a in exp.ARMS]],[
        ['정답 수 / 96문제',*[ncorrect(m[a]) for a in exp.ARMS]],
        ['정답률',*[pct(m[a]['accuracy']) for a in exp.ARMS]],
        ['대표 응답 시간',*[f"{m[a]['mean_query_seconds']:.2f}초" for a in exp.ARMS]],
        ['느린 요청의 시간: p95',*[f"{m[a]['request_p95_seconds']:.2f}초" for a in exp.ARMS]],
        ['코드 자료 평균',*[f"{t[a]['code_tokens']:.1f}토큰" for a in exp.ARMS]],
        ['총 입력 평균: 선택 + 답변',*[f"{t[a]['total_input_tokens']:.1f}토큰" for a in exp.ARMS]],
        ['가장 큰 한 호출 입력의 평균',*[f"{t[a]['peak_call_input_tokens']:.1f}토큰" for a in exp.ARMS]],
        ['8,192토큰 중 입력 점유',*[f"{t[a]['input_window_pct']:.2f}%" for a in exp.ARMS]],
        ['지정 원문 근거의 평균 포함률',*[pct(m[a]['raw_evidence_recall']) for a in exp.ARMS]],
        ['지정 원문 근거를 모두 포함한 비율',*[pct(m[a]['all_raw_evidence']) for a in exp.ARMS]],
        ['질문당 모델 호출 수','2회','2회','1회','1회'],
        ['실제 평가 답변 수','288회','288회','288회','288회'],
    ])
    changes=table(['파일 전체 대비','코드 토큰 증감','총 입력 증감','한 호출 입력 증감','정답률 차이','시간 차이'],[
        [NAMES[a],f"{t[a]['code_change_vs_full_pct']:+.1f}%",f"{t[a]['total_input_change_vs_full_pct']:+.1f}%",f"{t[a]['peak_input_change_vs_full_pct']:+.1f}%",
         f"{100*(m[a]['accuracy']-m['FULL']['accuracy']):+.1f}%p",f"{m[a]['mean_query_seconds']-m['FULL']['mean_query_seconds']:+.2f}초"] for a in ['A','B','R0']])
    small_large=table(['방식','정답 수: 작은 파일 → 큰 파일','코드 토큰: 작은 파일 → 큰 파일','총 입력: 작은 파일 → 큰 파일'],[
        [NAMES[a],f"{ncorrect(old['metrics'][a])} → {ncorrect(m[a])} / 96",f"{old['token_metrics'][a]['code_tokens']:.1f} → {t[a]['code_tokens']:.1f}",
         f"{old['token_metrics'][a]['total_input_tokens']:.1f} → {t[a]['total_input_tokens']:.1f}"] for a in exp.ARMS])
    input_table=table(['방식','함수 선택 입력','최종 답변 입력','총 입력'],[
        [NAMES[a],f"{t[a]['selector_input_tokens']:.1f}",f"{t[a]['answer_input_tokens']:.1f}",f"{t[a]['total_input_tokens']:.1f}"] for a in exp.ARMS])
    comparisons=table(['비교: 앞 방식 − 뒤 방식','정답률 차이','탐색적 95% 추정 구간','보정 p값'],[
        [f"{NAMES[c['higher']]} − {NAMES[c['base']]}",f"{c['delta_pp']:+.1f}%p",f"{c['ci95_pp'][0]:+.1f} ~ {c['ci95_pp'][1]:+.1f}%p",f"{c['holm_p_six_quality_contrasts']:.3f}"] for c in s['comparisons'].values()])
    categories=table(['질문 종류','문제 수','A','B','R0','파일 전체'],[
        [label,m['A']['by_category'][key]['unique_questions'],*[f"{m[a]['by_category'][key]['question_equivalent_correct']:g}" for a in exp.ARMS]] for key,label in CATEGORIES.items()])
    timing=table(['단계: 요청당 평균','A','B','R0','파일 전체'],[
        ['출발 함수 선택',*[f"{m[a]['mean_select_seconds']:.3f}초" for a in exp.ARMS]],
        ['원문 검색·읽기·구성·길이 확인',*[f"{m[a]['mean_retrieval_seconds']+m[a]['mean_expansion_seconds']+m[a]['mean_packing_seconds']:.3f}초" for a in exp.ARMS]],
        ['최종 답변 처리',*[f"{m[a]['mean_answer_seconds']:.3f}초" for a in exp.ARMS]],
    ])
    q=next(q for q in s['questions'] if q['task_id']=='eval_inventory__v2_partial_depletes_available')
    example=table(['항목','A','B','R0','파일 전체'],[
        ['실제 답변',*['`'+json.dumps(q['arms'][a]['answer'],ensure_ascii=False)+'`' for a in exp.ARMS]],
        ['코드 자료 토큰',*[q['arms'][a]['context_tokens'] for a in exp.ARMS]],
    ])
    best_accuracy=max(x['accuracy'] for x in m.values());best='·'.join(NAMES[a] for a in exp.ARMS if m[a]['accuracy']==best_accuracy)
    all_saving=all(t[a]['total_input_change_vs_full_pct']<0 for a in ['A','B','R0'])
    saving_statement=('큰 파일에서는 A·B·R0 모두 파일 전체보다 총 입력을 줄였다.' if all_saving else '큰 파일에서도 총 입력 절감 여부는 방식별로 달랐다.')
    additions=f'''## 8. 큰 파일에서도 같은 네 방식을 실제로 실행하면

### 8.1 작은 파일이었던 것이 이전 토큰 역전의 이유인가?

**작은 파일 크기가 중요한 이유였지만, B·R0이 인덱스만 전달한다는 이해는 수정해야 한다.** 색인은 코드를 찾는 자료다. B는 그 색인을 따라 여러 파일의 함수·상수 원문을 모아 보내고, R0은 검색된 원문 조각과 참조 묶음을 보낸다. B에는 출발 함수를 고르는 별도 LLM 호출도 있다. R0은 일부가 겹치는 원문 묶음을 함께 넣을 수 있으며, 점수 하한 없이 1,024토큰까지 후보를 담는다.

작은 파일 실험의 파일 전체는 평균 **{old['token_metrics']['FULL']['code_tokens']:.1f}토큰**이었다. 그보다 넓은 범위를 읽은 B는 **{old['token_metrics']['B']['code_tokens']:.1f}토큰**, R0은 **{old['token_metrics']['R0']['code_tokens']:.1f}토큰**의 코드 자료를 보냈다. 비교 대상 파일이 작고, 가져오는 원문 범위·표시·중복·호출 수가 달랐기 때문에 토큰이 더 들었던 것이다.

### 8.2 이번 큰 파일 실험의 조건

기존 **같은 96문제 × 3회 × 4방식 = 1,152개 답변을 새로 생성**했다. 개발용 32개 답변과 예열은 점수에서 제외했다. 이전의 작은 파일 결과는 보존하고 비교에 함께 제시한다.

| 항목 | 이번 조건 |
|---|---|
| 파일 크기 | 평가용 6프로젝트 × 5파일. 각 파일 {min_tokens:,}~{max_tokens:,}토큰, {min_lines}~{max_lines}줄 |
| 커진 부분 | 파일마다 관계없는 실행 가능한 보조 함수 {min_added}~{max_added}개 추가. 공백이나 긴 댓글로 채우지 않음 |
| 유지한 부분 | 기존 함수·상수의 원문, import, 참조 관계, 질문·정답. 96개 정답을 다시 실행하여 확인 |
| 원래 코드 위치 | 파일 앞·중간·뒤에 배치. 평가 프로젝트를 각 위치에 2개씩 배정 |
| A·B·R0 | 기존 선택·확장·검색 구현 그대로 사용. 답변용 코드 자료 최대 1,024토큰 |
| 파일 하나 전체 | 대상 함수가 정의된 파일 경로를 미리 제공하고, 그 파일 전체를 원문 그대로 전달. 다른 파일은 자동으로 추가하지 않음 |
| 공통 모델·문맥 | 기존과 같은 Qwen2.5-Coder-7B-Instruct Q5_K_M, M3 Pro, 컨텍스트 8,192토큰 |
| 생성 조건 | 같은 질문·답변 지시문, temperature 0, seed 1, 답변 최대 128토큰, 입력 계산 재사용 끔 |
| 실행 순서 | 같은 세션에서 질문마다 네 방식을 번갈아 실행. 프로젝트·반복마다 각 방식이 1~4번째에 같은 횟수로 등장 |

**길이 제한의 차이:** 기존 작은 파일은 원문 전체도 1,024토큰 안에 들어갔다. 이번 파일 전체 방식에는 그 코드 한도를 적용하지 않아, 4천여 토큰의 원문을 자르지 않고 모두 전달했다. 네 방식의 전체 컨텍스트 한도는 동일한 8,192토큰이다. 따라서 이번 비교는 **같은 양의 코드를 준 비교가 아니라, ‘일부를 고르는 전략’과 ‘파일 전체를 주는 전략’의 비교**다.

### 8.3 큰 파일의 실제 실행 결과

{main}

{'문제·방식별 답은 세 반복 모두 같았으므로 정답 수는 서로 다른 96문제를 기준으로 표시했다.' if stable else '반복별 출력이 달라 정답 수는 문제별 세 번의 성공률을 합한 환산값이다. 반복별 기록도 원자료에 보존했다.'} 대표 시간은 각 문제의 세 번 중앙값을 구한 뒤 평균했다. 코드 자료에는 원문과 붙여 보낸 제목·import문·코드 표시가 포함된다. 총 입력은 모든 호출의 질문·지시문·대화 형식까지 포함한다. 출력 토큰은 이 표의 입력량에 포함하지 않는다.

### 8.4 파일 전체보다 얼마나 줄었나?

아래는 **각 방식 − 파일 전체**다. 음수는 토큰이 적거나 시간이 짧다는 뜻이다. 정답률의 `%p`는 두 비율의 차이다.

{changes}

{saving_statement} 다만 A·B·R0의 코드 자료는 1,024토큰 이하로 제한하고 파일 전체는 4천여 토큰을 보내므로, **코드 토큰 절감 자체는 설정상 예상되는 결과**다. 실제 실험에서 확인할 핵심은 그 절감과 함께 정답률·검색 비용·응답 시간이 어떻게 달라지는가다.

단위는 토큰이며, 한 질문의 평균 입력을 호출별로 나누면 다음과 같다.

{input_table}

함수 선택 호출과 답변 호출은 별도 문맥을 사용한다. 따라서 누적 입력량과 한 번에 차지하는 컨텍스트를 구분해야 한다. 답변용 출력 128토큰, 함수 선택용 출력 96토큰은 각 호출에서 별도로 확보했다.

### 8.5 작은 파일 결과와 나란히 보면

{small_large}

같은 질문과 원래 동작을 유지했지만, **파일 크기만 변한 것은 아니다.** 관계없는 함수와 검색 후보가 늘었고, 원래 코드의 줄 위치도 달라졌다. 그래서 이 결과는 ‘짧은 관련 코드를 포함한 파일에 다른 기능이 많이 추가된 상황’에 대한 실험이다. 관련 함수 자체가 수천 줄로 길어지는 경우는 평가하지 않았다.

큰 파일 네 방식은 같은 세션에서 번갈아 측정했다. 작은 파일은 이전 세션의 기록이므로, 작은 파일과 큰 파일 사이의 시간 변화에는 장비 상태 차이가 섞일 수 있다. 토큰은 실제 입력 문자열과 같은 모델의 토크나이저로 확인한 값이다.

### 8.6 정답률과 시간에서 관찰한 차이

{categories}

각 칸은 해당 종류에서 맞힌 문제 수다. 전체 96문제를 이용한 방식 간 비교는 아래와 같다.

{comparisons}

6개 프로젝트를 묶음으로 재표집하는 46,656가지 조합으로 추정 구간을 계산했다. 3회 반복을 독립된 문제로 세지 않았으며, 이번 큰 파일의 여섯 정답률 비교에 Holm 보정을 적용했다. 보정 p값이 0.05보다 크면 검정상 우위를 확정하지 않는다. 프로젝트가 6개뿐이므로 결과는 탐색적이다.

{timing}

단계별 표는 요청 전체 평균이므로, 문제별 중앙값을 사용한 대표 시간과 합계가 정확히 같을 필요는 없다. 사전 색인·참조 그래프·검색 벡터 생성 시간은 질의 시간에서 제외했다. 파일이 커지면서 늘어난 후보를 확인하고 토큰 길이를 계산하는 시간은 질의 시간에 포함했다.

### 8.7 같은 질문의 큰 파일 답변 예시

6절과 같은 재고 문제다. `remaining_after(9,1,8,True)`의 정답은 `0`이며, 원래 계산 코드는 바꾸지 않았다.

{example}

파일 전체 방식은 커진 `service.py`의 모든 줄을 입력했다. 다른 파일에 있는 계산 함수·정책 상수는 그 파일 안에 자동으로 들어오지 않는다. 각 값은 첫 번째 반복의 실제 출력이다. 이전부터 사용한 사례를 그대로 비교했으며, 전체 결과를 대표하도록 골라낸 사례는 아니다.

### 8.8 이 실험에서 내릴 수 있는 판단

**{saving_statement}** 가장 높은 관측 정답률은 **{best}의 {pct(best_accuracy)}**였다. 토큰을 적게 쓴다는 사실과 답변이 더 정확하다는 사실은 따로 판단해야 한다. 코드 자료의 범위가 넓어지거나 검색 후보가 많아져도 정답이 보장되는 것은 아니다.

이번 결과는 파일 전체를 전달하는 비용이 커질 때 선택 방식의 토큰 사용량이 어떻게 달라지는지 보여 준다. 그러나 보조 함수를 추가한 합성 자료이며, 원래 질문 대상 함수는 여전히 짧다. 큰 단일 함수·복잡한 실제 저장소·다른 언어·보안 취약점 탐지에서 같은 절감률이나 정확도를 보장하지 않는다. 파일 전체 방식이 파일 경로를 미리 제공받는 조건도 고려해야 한다.

### 큰 파일 실험의 확인 자료

새 1,152회 답변과 실제 요청·응답, 원문 전체 입력, 정답, 토큰, 집계에 대해 **{v['count']}개 점검을 통과**했다. 측정 기록을 확인하는 로컬 검증이며 외부 인증은 아니다.

| 확인할 자료 | 링크 |
|---|---|
| 큰 파일 통합 결과·질문별 답변 | [통합 집계](evidence/large_files_20261024/summary.json) |
| 실제 평가 실행·모델 요청 | [1,152회 실행 기록](evidence/large_files_20261024/results.jsonl) · [모델 호출 로그](evidence/large_files_20261024/model_calls.jsonl) |
| 고정한 계획·파일 구성 | [실험 계획](evidence/large_files_20261024/protocol.json) · [파일 크기와 확장 내역](evidence/large_files_20261024/corpus_manifest.json) |
| 환경·정답·검증 | [실행 환경](evidence/large_files_20261024/environment.json) · [정답 재확인](evidence/large_files_20261024/gold_recheck.json) · [검증 결과](evidence/large_files_20261024/verification.json) |
| 실제 큰 파일 예시 | [재고 service.py](evidence/large_files_20261024/projects/eval_inventory/service.py) · [재고 rules.py](evidence/large_files_20261024/projects/eval_inventory/rules.py) |
| 재현 | [실행·분석·검증 안내](evidence/large_files_20261024/reproduce.txt) |
| 추가 전 문서 | [작은 파일 보고서 보관본](evidence/large_files_20261024/history/report_before_large_files.md) |

'''
    base=(out/'history/report_before_large_files.md').read_text()
    base=base.replace('네 방식의 답변용 코드 상한은 동일하게 1,024토큰이며,','1~7절의 작은 파일 실험에서는 네 방식의 답변용 코드 상한이 1,024토큰이며,')
    base=base.replace('## 2. 파일 전체 방식도 실제로 어떻게 실험했나?','## 2. 작은 파일: 파일 전체 방식도 실제로 어떻게 실험했나?')
    base=base.replace('## 3. 네 방식을 실제로 실행한 결과','## 3. 작은 파일에서 네 방식을 실제로 실행한 결과')
    base=base.replace('## 7. 목적에 따른 판단','## 7. 작은 파일 결과에서 목적에 따른 판단')
    intro=(f"**추가 실험:** 파일을 약 4,100토큰으로 키운 뒤 네 방식을 총 1,152회 새로 실행했다. 큰 파일의 결과는 **8절**, 기존 작은 파일의 결과와 색인 예시는 **1~7절**에 있다. {saving_statement}\n\n")
    first_break=base.index('\n\n')+2;base=base[:first_break]+intro+base[first_break:]
    assert base.count('## 확인 자료와 재현')==1
    text=base.replace('## 확인 자료와 재현',additions+'## 작은 파일 실험의 확인 자료와 재현')
    exp.small.r0.REPORT.write_text(text)
    exp.original.dump(out/'report_manifest.json',{'created_at_utc':exp.audited.now(),'report':str(exp.small.r0.REPORT),
        'report_sha256':exp.original.sha(exp.small.r0.REPORT),'summary_sha256':exp.original.sha(out/'summary.json'),
        'verification_sha256':exp.original.sha(out/'verification.json'),'generator_sha256':exp.original.sha(__file__),
        'previous_report_sha256':exp.original.sha(out/'history/report_before_large_files.md')})
    print(json.dumps({'report':str(exp.small.r0.REPORT),'characters':len(text)},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=exp.DEFAULT_OUT);build(p.parse_args().out)
