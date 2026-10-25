"""Extend report 03 only from verified completed RF/RH/C measurements."""
from __future__ import annotations
import json, sys, textwrap
sys.dont_write_bytecode=True
import experiment_raptor_large as exp

NAMES={'A':'현재 색인(A)','B':'파일 간 확장(B)','R0':'원문 검색(R0)',
       'RF':'함수 요약(RF)','RH':'계층 요약(RH)','C':'계층 요약 정리(C)','FULL':'파일 전체'}
ARMS=['A','B','R0','RF','RH','C','FULL']
BASE='evidence/raptor_large_20261024'

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
        ['| '+' | '.join(str(x).replace('\n',' ') for x in row)+' |' for row in rows])

def literal(value):return json.dumps(value,ensure_ascii=False)
def count(value):return str(int(value)) if float(value).is_integer() else f'{value:.2f}'

def explanation(example):
    asset=example['asset'];lookup={x['id']:x for x in asset['summaries']}
    leaf=lookup['summary:leaf:memory://symbol/service.py::remaining']
    file=lookup['summary:level2:service.py'];project=lookup['summary:level3:project']
    fields={k:leaf[k] for k in ['id','level','children','source_uris']}
    rfjson=json.dumps(fields,ensure_ascii=False,indent=2)
    rhjson=json.dumps([{k:s[k] for k in ['id','level','children']} for s in [file,project]],ensure_ascii=False,indent=2)
    body=leaf['text'].split('\n',1)[1]
    filebody=file['text'].split('\n',1)[1]
    projectbody=project['text'].split('\n',1)[1]
    rht=example['arms']['RH']['tokens'];ct=example['arms']['C']['tokens']
    return f'''### RF: 원문 후보에 ‘함수와 관련 코드의 설명’을 함께 저장한다

RF는 **함수 요약 방식**이다. R0이 준비한 원문 후보를 그대로 두고, 각 함수 후보의 코드를 LLM으로 읽어 만든 요약을 추가한다. 위 예제의 `remaining` 관련 코드 묶음을 요약하면, 해당 함수뿐 아니라 `sellable`과 `SAFETY_STOCK`도 요약의 재료가 된다. 질문을 받기 전에 생성하고 저장한다.

실제로 생성한 요약 항목의 연결 정보는 다음과 같다. `level: 1`은 함수 단계, `children`은 직접 요약한 원문 후보, `source_uris`는 그 후보의 출처를 뜻한다.

```json
{rfjson}
```

이 항목의 `text`에는 출처 제목과 다음 **실제 LLM 요약 본문**이 저장되었다. 아래는 읽기 쉽게 줄만 나눴다.

```text
{textwrap.fill(body,76)}
```

질문이 오면 **원문 후보와 함수 요약 후보를 한 목록에 놓고** R0과 같은 단어 유사도로 순위를 정해 1,024토큰 안에 넣는다. 함수 주소만 전달하거나 요약만 전달하는 방식이 아니다. 요약이 원문보다 짧을 수는 있지만, 원문과 요약을 함께 선택할 수 있어 전체 입력이 반드시 줄지는 않는다. 또한 ‘출처에 포함되었다’는 사실만으로 요약에 그 출처의 모든 규칙이 남아 있다고 볼 수 없다.

### RH: 함수 설명들을 다시 요약해 파일·프로젝트 설명을 만든다

RH는 **계층 요약 방식**이다. RF의 함수 요약들을 파일별로 묶어 다시 요약하고, 파일 요약들을 모아 프로젝트 요약을 만든다. 저장하는 연결 구조의 일부는 다음과 같다.

```json
{rhjson}
```

이 예제에서 실제 생성한 상위 요약은 다음과 같다.

| 저장 항목 | 실제 요약 본문 |
|---|---|
| `service.py` 파일 요약 | {filebody.replace(chr(10),' ').replace('|','&#124;')} |
| 프로젝트 요약 | {projectbody.replace(chr(10),' ').replace('|','&#124;')} |

RH는 **원문 + 함수 요약 + 파일 요약 + 프로젝트 요약**을 모두 검색 후보로 사용한다. 질문마다 전체 요약 트리를 LLM에 보내지 않는다. 각 단계의 후보를 하나의 목록에서 검색하고, 선택된 일부만 전달한다. 따라서 ‘계층’은 요약을 만드는 구조를 말하며, 검색할 때 반드시 프로젝트→파일→함수 순으로 내려가는 구현은 아니다.

큰 파일에서 한 파일의 자식 요약들이 모델 입력 한도에 들어가지 않으면, 순서대로 여러 묶음으로 나눠 먼저 요약하고 그 결과를 다시 합친다. 어떤 자식도 임의로 버리지 않으며, 이 중간 요약도 RH·C의 후보에 포함한다. 실제 적용 횟수는 9절의 준비 비용 표에 제시한다.

### C: RH가 고른 자료를 그대로 두고 반복과 긴 출처 표기를 줄인다

C는 **계층 요약 정리 방식**이다. 저장하는 요약과 검색 결과는 RH와 같다. 검색 후 전달 문자열을 만들 때 같은 함수 원문은 한 번만, 같은 파일의 import문도 한 번만 넣고, 긴 제목을 짧게 바꾼다. 예를 들어 원문 제목은 다음처럼 바뀐다.

```text
정리 전: ### memory://symbol/service.py::remaining lines 3-4
정리 후: # Code service.py::remaining
```

```python
# 정리 후에도 아래 원문 본문은 그대로 유지된다.
from rules import sellable
def remaining(on_hand, held):
    return sellable(on_hand, held)
```

고유 코드·import문·요약 본문은 그대로 보존한다. LLM으로 다시 요약하지 않고, 확보한 여유 공간을 다른 자료로 채우지도 않는다. 위 별도 예제에서 실제 선택 결과는 RH **{rht}토큰**, C **{ct}토큰**이었다. 이는 예제의 입력 구성 수치이며 96문제의 성능 수치는 9절에 있다. 본문이 같아도 반복·표시가 바뀌면 LLM의 답은 달라질 수 있다.

### 세 방식에는 RAPTOR의 어떤 아이디어가 들어갔나?

[RAPTOR 원 논문](https://arxiv.org/abs/2401.18059)은 내용을 묶어 요약하고, 요약들을 다시 묶어 상위 요약을 만드는 과정을 반복하며 여러 추상화 단계에서 근거를 찾는 접근을 제안한다. 이 실험은 그중 **요약을 검색 자료로 저장하고, 여러 단계의 요약과 원문을 함께 검색하는 아이디어**를 코드에 적용한 변형이다.

| 방식 | 적용한 아이디어 | 이 실험에서 하지 않는 것 |
|---|---|---|
| RF | 함수·관련 원문을 요약해 원문과 함께 검색 | 파일·프로젝트까지 재귀적으로 요약하지 않음 |
| RH | 함수→파일→프로젝트로 재귀 요약하고 모든 단계에서 검색 | 원 논문의 학습된 임베딩·군집화 전체를 재현하지 않음 |
| C | RH의 요약 구조와 검색을 그대로 사용한 뒤 입력을 정리 | 새로운 요약 방식이나 RAPTOR 고유 기능이라고 주장하지 않음 |

여기서는 코드의 참조 관계와 파일 경계로 내용을 묶고 TF-IDF로 검색한다. 따라서 결과는 **이번 구현에 대한 평가**이며, RAPTOR 원 논문 전체의 성능을 검증하거나 반박하는 실험은 아니다. 예제 원문·요약 생성 요청·실제 선택 자료는 [예제 기록]({BASE}/index_example/generated.json)에 보존했다.

'''

def results(s):
    allp=s['populations']['all96'];m=allp['metrics'];t=allp['tokens'];build=s['build']['evaluation']
    headline=table(['방식','정답 / 96','정답률','대표 시간','근거 토큰','총 입력 토큰','전체 파일 대비 입력 절감'],[
        [NAMES[a],count(m[a]['question_equivalent_correct']),f"{100*m[a]['accuracy']:.1f}%",f"{m[a]['mean_query_seconds']:.2f}초",f"{t[a]['context']:.1f}",f"{t[a]['total']:.1f}",f"{t[a]['saving_total_vs_full_pct']:.1f}%"] for a in ARMS])
    context_table=table(['방식','선택 호출 입력','답변 호출 입력','가장 큰 한 호출 입력','8,192토큰 중 점유'],[
        [NAMES[a],f"{t[a]['selector']:.1f}",f"{t[a]['answer']:.1f}",f"{t[a]['peak']:.1f}",f"{t[a]['window_pct']:.2f}%"] for a in ARMS])
    contrasts=table(['비교','정답률 차이','탐색적 95% 구간','보정 p값','개선 / 악화 / 동일 문제'],[
        [f"{NAMES[c['higher']]} − {NAMES[c['base']]}",f"{c['delta_pp']:+.1f}%p",f"{c['ci95_pp'][0]:+.1f} ~ {c['ci95_pp'][1]:+.1f}%p",f"{c['holm_p_three_quality_contrasts']:.3f}",f"{c['win']} / {c['loss']} / {c['tie']}"] for c in s['comparisons'].values()])
    first=s['historical_matched_questions']['original48'];firstc=s['historical_matched_questions']['original48_C']['C']
    historical=table(['방식','최초 작은 파일: 같은 48문제','이번 큰 파일: 같은 48문제','나머지 48문제: 큰 파일'],[
        [NAMES[a],count(first[a]['old_correct']) if a in first else f"{count(firstc['old_correct'])} (후속 1회 재확인)" if a=='C' else '최초 실험 없음',
         count(s['populations']['original48']['metrics'][a]['question_equivalent_correct']),count(s['populations']['additional48']['metrics'][a]['question_equivalent_correct'])] for a in ARMS])
    prep_rows=[]
    for purpose,label in [('build_leaf','함수 요약'),('build_level_2_batch','파일 안 중간 묶음 요약'),('build_level_2','최종 파일 요약'),('build_level_3','프로젝트 요약')]:
        b=build['by_purpose'].get(purpose,{'calls':0,'input_tokens':0,'output_tokens':0,'model_wall_seconds':0})
        prep_rows.append([label,b['calls'],f"{b['input_tokens']:,}",f"{b['output_tokens']:,}",f"{b['model_wall_seconds']/60:.1f}분"])
    prep=table(['준비 단계: 평가용 6개 프로젝트','실제 생성 수','입력 토큰','출력 토큰','모델 호출 시간 합계'],prep_rows)
    selected=table(['방식','함수 요약 선택 수','상위 요약 선택 수','요약이 들어간 문제 / 96','상위 요약이 들어간 문제 / 96','지정 원문 평균 포함률'],[
        [NAMES[a],m[a]['selected_levels'].get('1',0),sum(m[a]['selected_levels'].get(k,0) for k in ['2','3']),m[a]['questions_with_summary'],m[a]['questions_with_higher_summary'],f"{100*m[a]['raw_evidence_recall']:.1f}%"] for a in ['RF','RH','C']])
    cr=s['comparisons']['C-RH'];comp=s['compaction']
    limittext=' · '.join(f"{a} {m[a]['output_limit_calls']}회" for a in ARMS)
    stable=all(v['different_raw_output_questions']==0 for v in s['repeat_stability'].values())
    stability=('새 세 방식도 각 문제의 세 출력이 모두 같았다. 따라서 정답 수는 독립된 96문제 기준이다.' if stable else '새 방식 일부에서 반복 출력이 달랐다. 정답 수는 문제별 3회 정답 비율의 합계이므로 소수가 될 수 있다. 반복을 독립 문제로 취급하지 않았다.')
    interpretation=[]
    for key,phrase in [('RF-R0','함수 요약 추가'),('RH-RF','파일·프로젝트 요약 추가'),('C-RH','입력 정리')]:
        c=s['comparisons'][key];h,b=c['higher'],c['base'];diff=m[h]['question_equivalent_correct']-m[b]['question_equivalent_correct']
        sig='보정 검정에서 차이가 관찰되었다' if c['holm_p_three_quality_contrasts']<.05 else '보정 검정에서 정확도 차이를 확정하지 못했다'
        interpretation.append(f"- **{phrase}({b}→{h}):** 정답 {count(m[b]['question_equivalent_correct'])}→{count(m[h]['question_equivalent_correct'])}개({diff:+.0f}개). {sig}.")
    examples=[]
    for label,pred in [('요약을 추가해 맞힌 사례',lambda q:q['arms']['RF']['correct'] and not q['arms']['R0']['correct']),
                       ('요약을 추가해 틀린 사례',lambda q:q['arms']['R0']['correct'] and not q['arms']['RF']['correct']),
                       ('정리 후 판정이 달라진 사례',lambda q:q['arms']['RH']['correct']!=q['arms']['C']['correct'])]:
        candidates=[q for q in s['questions'] if pred(q)]
        if candidates:
            q=candidates[0]
            examples.append(f"**{label}** — `{q['task_id']}`\n\n{q['question']}\n\n"+table(['정답','R0','RF','RH','C'],[[literal(q['expected'])]+[literal(q['arms'][a]['parsed_answer']) for a in ['R0','RF','RH','C']]]))
    return f'''## 9. 같은 큰 파일에 RF·RH·C를 추가한 실제 실험

### 9.1 첫 실험과 결과가 달라 보이는 이유부터 구분하면

01번 보고서의 최초 실험은 **48문제**, 최근 비교는 그 문제와 추가 48문제를 합친 **96문제**다. 정답 개수를 분모 없이 비교하면 개선 폭을 오해할 수 있다. 아래는 질문 문장과 정답이 같은 최초 48문제로 맞춘 비교다.

{historical}

최초 실험에는 C와 파일 전체 방식이 없었다. C의 48문제 수치는 01번 보고서에 기록된 **후속 재확인 1회**이며, 이번에는 3회 실행했다. 파일을 키울 때 원래 기능은 유지했지만 관계없는 함수·검색 후보와 줄 위치도 함께 바뀌었다. 요약 역시 커진 파일에서 새로 생성했다. 따라서 아래 차이는 파일 크기 하나만의 인과 효과가 아니다. 최초 실험의 시간은 일부 호출 비용을 공유·합산했으므로 이번 실측 시간과 직접 비교하지 않는다.

### 9.2 이번에 새로 실행한 범위

| 항목 | 고정한 조건 |
|---|---|
| 원문·질문 | 8절과 바이트까지 동일한 큰 파일, 동일한 96문제·정답. 평가용 6개 합성 프로젝트, 파일당 4,099~4,157토큰 |
| 새 평가 | RF·RH·C 각각 96문제 × 3회 = **864개 실제 답변** |
| 비교 기준 | 8절의 A·B·R0·파일 전체 **1,152개 실제 답변을 보존**하여 함께 제시 |
| 모델·생성 | 같은 Qwen2.5-Coder-7B Q5_K_M, M3 Pro, 컨텍스트 8,192, 출력 128, temperature 0, seed 1, 입력 계산 재사용 끔 |
| 근거 선택 | RF·RH는 최대 1,024토큰. C는 RH의 동일 선택 결과를 정리하고 여유 공간을 채우지 않음. 파일 전체는 원문 전체를 전달 |
| 요약 | 질문·정답을 입력하지 않고 원문에서 새로 생성. 함수 요약은 출력 최대 256토큰·100단어 이내 지시, 상위 요약도 같은 지시·한도 |
| 실행 순서 | 매 반복에서 세 방식의 6가지 순서를 각각 16번씩 배치. 질문 블록 순서는 고정 시드로 무작위화 |
| 별도 개발 확인 | 평가와 다른 8문제 × 3방식 = 24답변. 주 점수에서 제외 |

RF·RH·C는 같은 세션에서 번갈아 실행했지만, A·B·R0·파일 전체는 앞선 세션이다. **새 세 방식 사이의 시간 비교는 같은 세션이며, 이전 네 방식과의 시간 차이는 세션 상태까지 통제한 결과가 아니다.** 답변 지시문·검색 방식·토큰 계산과 모델 파일은 동일하다.

파일 단위 상위 요약이 입력 한도에 들어가지 않을 때만 중간 묶음 요약을 추가하도록 **생성 전에 규칙을 고정**했다. 자식 요약을 잘라 버리지 않는다. 이 처리까지 포함한 변형이며, 원 논문 구현 전체를 재현한 것은 아니다.

### 9.3 일곱 방식의 정답·시간·입력량

{headline}

{stability} 대표 시간은 문제별 세 번의 중앙값을 구한 뒤 평균한 값이다. ‘근거’는 코드·요약·출처 제목 등을 포함한 선택 자료이고, ‘총 입력’에는 질문·지시문·대화 형식과 A·B의 함수 선택 호출도 포함한다. 사전 요약 생성과 출력 토큰은 이 입력 표에서 제외하고 9.6절에 별도로 제시한다.

출력 최대 128토큰에서 끝난 평가 호출: **{limittext}**. 이 응답들은 오답으로 포함했으며 성공한 재시도로 대체하지 않았다. 입력 잘림이나 전송 실패 여부는 검증 기록에서 확인했다. 파일 전체 방식의 21회 제한 종료라는 8절의 조건도 그대로 유지된다.

### 9.4 A의 목적에 맞춰 컨텍스트 윈도우를 비교하면

{context_table}

RF·RH·C는 질문당 답변 호출 1회이므로 답변 입력=총 입력=한 호출 입력이다. A·B의 선택 호출과 답변 호출은 별도 컨텍스트를 사용하므로 누적 입력을 한 번의 점유량으로 읽으면 안 된다. 위 점유율은 입력만이며 출력 공간은 별도 확보한다.

전체 파일 대비 입력 절감률은 **1 − 방식의 평균 총 입력 / 전체 파일의 평균 총 입력**으로 계산했다. RF·RH도 1,024토큰 상한을 두므로 큰 파일 전체보다 짧다는 사실 자체는 예상되는 결과다. 요약의 가치 여부는 같은 상한의 R0보다 얼마나 더 정확한지와 준비 비용까지 함께 봐야 한다.

### 9.5 요약과 정리에서 각각 얼마나 달라졌나?

{contrasts}

이번 추가 실험에서 미리 지정한 세 비교에 대해서만 Holm 보정을 적용했다. 6개 프로젝트 단위의 46,656가지 재표집으로 95% 구간을, 프로젝트별 부호 뒤집기로 p값을 계산했다. 두 계산법이 달라 구간과 검정 결과를 동일시하지 않는다. 같은 문제의 세 반복은 독립된 세 문제가 아니며, 이 작은 합성 표본은 탐색적 근거다.

{chr(10).join(interpretation)}

C는 RH보다 근거 입력을 **{comp['context_reduction_pct']:.1f}%**, 전체 입력을 **{comp['input_reduction_pct']:.1f}%** 줄였다. 같은 세션에서 대표 응답 시간은 **{m['RH']['mean_query_seconds']:.2f}→{m['C']['mean_query_seconds']:.2f}초**, 변화율은 **{cr['latency_reduction_pct']:.1f}% 단축**이었다. 단축률이 음수이면 더 오래 걸렸다는 뜻이다. 속도 변화의 탐색적 95% 구간은 {cr['latency_reduction_ci95_pct'][0]:.1f}~{cr['latency_reduction_ci95_pct'][1]:.1f}%다. RH와 C의 **288쌍 모두 선택 자료가 같고, 고유 코드·import·요약 본문이 보존되었는지** 별도로 검증했다.

실제로 어떤 종류의 근거를 골랐는지도 확인했다. ‘선택 수’는 288번의 호출에서 선택한 항목 수 합계로, 고유한 요약 문서 수와 다르다.

{selected}

원문 포함률은 필요한 원문 코드가 실제 입력에 들어간 비율이다. 요약의 출처 목록에 함수가 들어 있다는 이유만으로 그 함수의 내용을 모두 전달했다고 계산하지 않았다. 요약이 맞는 내용을 전달할 수도 있으므로, 원문 포함률만으로 요약 방식의 답변 품질을 판정할 수도 없다.

### 9.6 요약을 미리 만드는 비용

{prep}

평가용 요약 생성은 총 **{build['summary_calls']:,}회**, 입력 **{build['input_tokens']:,}토큰**, 출력 **{build['output_tokens']:,}토큰**, 모델 호출 시간 합계 **{build['model_wall_seconds']/60:.1f}분**이었다. 이 시간은 요청의 토큰 계산·모델 응답·로그 처리를 포함하며 서버 시작이나 모든 파일 준비 시간을 뜻하지 않는다. 개발용 프로젝트는 별도 {s['build']['development']['summary_calls']}회이고 위 표에서 제외했다.

RF에는 함수 요약까지만 필요하다. RH·C는 그 요약을 공유하고 파일·프로젝트 요약을 추가로 사용한다. 세 방식 각각의 비용인 것처럼 공유 요약 비용을 세 번 더하지 않았다. 사전 요약에서 출력 한도에 도달한 호출은 **{build['output_limit_calls']}회**이며, 해당 비어 있지 않은 결과는 원문 그대로 저장하고 상태를 표시하도록 사전에 정했다. 요약 내용이 모두 정확하다는 보장은 없다.

질문이 늘면 일회성 준비 비용은 여러 질문에 나누어 볼 수 있다. 예를 들어 질의당 상각 입력은 `질의 입력 + 해당 방식의 준비 입력 / 재사용한 질문 수`다. 실제 코드 변경에 따른 재생성 횟수·갱신 비용·비용 회수 시점은 이번 실험에서 측정하지 않았다.

### 9.7 같은 질문의 실제 답변

{chr(10)+chr(10).join(examples)}

위 사례는 판정이 바뀐 질문 중 ID 순서로 처음 나타난 것을 골라 보여 준 것이다. 어느 문장이나 요약 오류가 답변 변화를 일으켰는지는 따로 제거 실험을 하지 않았으므로 원인으로 단정하지 않는다.

### 확인 자료

| 확인할 내용 | 기록 |
|---|---|
| 실행 전 고정 조건 | [실험 계획]({BASE}/protocol.json) |
| 생성한 요약·출처·계층 | [요약 자료]({BASE}/assets.json) |
| 새 864개 답변과 실제 입력 | [평가 원자료]({BASE}/results.jsonl) |
| 사전 요약부터 답변까지 실제 모델 요청 | [호출 기록]({BASE}/model_calls.jsonl) |
| 일곱 방식 집계·같은 48문제 비교 | [집계]({BASE}/summary.json) |
| 독립 재계산·토큰·검색·본문 보존 점검 | [검증]({BASE}/verification.json) |
| 기존 보고서 보존본 | [수정 전 보고서]({BASE}/history/report_before_raptor_large.md) |

'''

def main():
    out=exp.OUT;s=exp.read(out/'summary.json');v=exp.read(out/'verification.json')
    assert v['status']=='PASS' and v['summary_sha256']==exp.v1.sha(out/'summary.json')
    original=(out/'history/report_before_raptor_large.md').read_text()
    manifest=out/'report_manifest.json'
    allowed={exp.audit.digest(original)}
    if manifest.exists():allowed.add(exp.read(manifest)['report_digest'])
    assert exp.audit.digest(exp.REPORT.read_text()) in allowed,'Report edited externally; reconcile instead of overwriting'
    example=exp.read(out/'index_example/generated.json')
    text=original.replace('# 현재 색인(A)·파일 간 확장(B)·원문 검색(R0)·파일 전체 입력: 실제 실험 비교',
        '# 코드 검색·RAPTOR 요약·파일 전체 입력: 실제 실험 비교')
    intro=('**최신 추가 실험:** 8절과 동일한 큰 파일·96문제에서 RF(함수 요약)·RH(계층 요약)·C(계층 요약 정리)를 '
           '**864회 새로 실행**했다. 일곱 방식의 비교와 첫 실험과 같은 48문제의 비교는 **9절**, 색인·요약의 구체적 예시는 **1절**에 있다.\n\n')
    text=text.replace('\n\n**추가 실험:**','\n\n'+intro+'**앞선 큰 파일 실험:**',1)
    text=text.replace('실험일: 2026년 10월 24일 · 동일한 96문제 × 방식별 3회 · 네 방식 모두 RAPTOR 요약 없음',
        '기존 네 방식 실험일: 2026년 10월 24일 · 동일한 96문제 × 방식별 3회 · A·B·R0·파일 전체는 RAPTOR 요약 없음')
    text=text.replace('## 1. 같은 원본 파일로 A·B·R0의 색인을 비교하면','## 1. 같은 원본 파일로 색인과 RAPTOR 요약을 비교하면')
    marker='### 파일 전체 방식까지 나란히 비교하면'
    text=text.replace(marker,explanation(example)+marker,1)
    text=text.replace('| 파일 하나 전체 | 파일 경로만 제공;',
        '| RF | R0 원문 후보 + 함수·관련 코드 요약 | 단어 검색으로 고른 원문·함수 요약 일부 |\n'
        '| RH | RF 자료 + 파일·프로젝트 요약 | 여러 단계의 원문·요약 중 선택된 일부 |\n'
        '| C | RH와 같은 자료 | RH와 같은 선택 결과를 중복 제거·출처 축약 후 전달 |\n'
        '| 파일 하나 전체 | 파일 경로만 제공;',1)
    text=text.replace('R0과 파일 전체 방식은 답변 호출만 있다.','R0·RF·RH·C와 파일 전체 방식은 질문당 답변 호출만 있다. RF·RH·C의 사전 요약 생성 호출은 이 질의당 횟수와 별도다.',1)
    text=text.replace('세 색인 방식 모두 RAPTOR 요약을 사용하지 않는다.','A·B·R0은 RAPTOR 요약을 사용하지 않는다.',1)
    text=text.replace('## 작은 파일 실험의 확인 자료와 재현',results(s)+'## 작은 파일 실험의 확인 자료와 재현',1)
    exp.REPORT.write_text(text)
    exp.v1.dump(manifest,{'generated_at_utc':exp.audit.now(),'report_sha256':exp.v1.sha(exp.REPORT),'report_digest':exp.audit.digest(text),
        'summary_sha256':exp.v1.sha(out/'summary.json'),'verification_sha256':exp.v1.sha(out/'verification.json'),
        'generator_sha256':exp.v1.sha(__file__)})
    print('Updated report:',exp.REPORT,'characters:',len(text))

if __name__=='__main__':main()
