"""Extend report 03 only from verified completed RF/RH/C measurements."""
from __future__ import annotations
import json, sys, textwrap
from datetime import datetime
from zoneinfo import ZoneInfo
sys.dont_write_bytecode=True
import experiment_raptor_large as exp
import reorganize_report
import clarify_report_context
import add_index_build_section

NAMES={'A':'현재 색인(A)','B':'파일 간 확장(B)','R0':'원문 검색(R0)',
       'RF':'함수 요약(RF)','RH':'계층 요약(RH)','C':'계층 요약 정리(C)','FULL':'파일 전체'}
ARMS=['A','B','R0','RF','RH','C','FULL']
BASE='evidence/raptor_large_20261024'
REVISION='revisions/methods_and_interpretation_20261025'

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
        ['| '+' | '.join(str(x).replace('\n',' ').replace('|','&#124;') for x in row)+' |' for row in rows])

def literal(value):return json.dumps(value,ensure_ascii=False)
def count(value):return str(int(value)) if float(value).is_integer() else f'{value:.2f}'

def construction(facts):
    prep=facts['preparation'];leaf=prep['by_purpose']['build_leaf']['calls']
    return f'''### 색인·요약은 누가, 어떤 과정으로 만드는가?

**파싱**은 소스 코드를 문법 구조로 읽는 작업이다. 여기서는 Python의 `ast.parse`로 **AST(함수·변수·import문 등의 구조를 표현한 문법 트리)**를 만든다. 예를 들어 함수 이름과 시작 줄, 참조한 이름을 읽을 수 있으며, 이 단계에서는 코드를 실행해 결과를 계산하지 않는다. **자연어 요약**은 그 코드가 무엇을 하는지 설명하는 새 문장을 만드는 작업이다. 아래에서 두 작업을 구분한다.

| 방식 | 질문이 오기 전에 준비하는 과정 | 준비 단계의 LLM 요약 생성 | 질문이 온 뒤의 과정 |
|---|---|---|---|
| **A — 현재 색인** | 파일 파싱 → 함수·클래스의 이름, 파일, 줄 위치를 추출 → `symbol_index` 주소록 저장 | **없음.** 이름·위치는 파서가 추출하며 요약 문장은 만들지 않음 | 이름·경로에 관한 규칙으로 후보를 최대 24개 추림 → LLM이 출발 함수 선택 → 파서로 같은 파일의 관련 원문을 모음 → LLM 답변 |
| **B — 파일 간 확장** | A의 주소록 + 파싱한 함수·상수·import 원문 → 참조 이름과 `from … import …` 연결을 코드로 계산 → 파일 간 참조 관계 저장 | **없음.** 참조 관계도 LLM이 추측해 만드는 것이 아님 | A와 같은 후보·선택 절차 → 참조 관계를 2차례 따라 원문 확장(함수 최대 8개) → LLM 답변 |
| **R0 — 원문 검색** | B와 같은 정적 참조 자료 → 함수·상수 원문을 최대 3단계 참조와 묶고 단독 원문 후보도 준비 → 단어 가중치 계산 | **없음.** 원문 조각을 복사·묶으며 자연어로 바꾸지 않음 | TF-IDF 단어 점수로 원문 후보 정렬 → 1,024토큰 안에서 선택 → LLM 답변 |
| **RF — 함수 요약** | R0의 원문 후보 → 각 함수와 연결된 원문 묶음을 LLM에 전달 → 함수 요약을 원문과 함께 저장 | **있음.** 평가용 6개 프로젝트에서 함수 요약 {leaf:,}개를 실제 생성 | 원문과 함수 요약을 같은 단어 점수로 정렬 → 1,024토큰 안에서 선택 → LLM 답변 |
| **RH — 계층 요약** | RF의 함수 요약 → 같은 파일의 요약들을 LLM으로 재요약 → 파일 요약들을 LLM으로 재요약해 프로젝트 요약 저장 | **있음.** 함수 {leaf:,}개 + 파일 30개 + 프로젝트 6개. 내용은 LLM이 쓰고, 파일별 묶음은 코드가 정함 | 원문·함수·파일·프로젝트 요약을 한 목록에서 검색 → 일부 선택 → LLM 답변 |
| **C — 계층 요약 정리** | RH와 같은 색인·요약을 공유 | **새 요약 생성은 없음.** RH에서 만든 LLM 요약은 그대로 사용 | RH와 같은 자료 선택 → 일반 코드로 중복 원문·import 제거와 제목 축약 → LLM 답변. 줄어든 공간은 다시 채우지 않음 |
| **파일 전체** | 검색용 색인·자연어 요약을 만들지 않음. 이 실험에서는 대상 파일 경로를 미리 제공 | **없음** | 지정된 파일을 처음부터 끝까지 읽음 → 그대로 LLM에 전달해 답변. 다른 파일의 정의는 자동 추가하지 않음 |

따라서 **A·B·R0의 준비 자료는 파싱·규칙 계산으로 만들고, RF·RH의 설명 문장은 LLM이 만든다. C는 RH의 LLM 요약을 재사용하고 전달 형식만 코드로 바꾼다.** 모든 방식의 최종 답변은 LLM이 생성한다. A·B의 ‘함수를 고르는 LLM 호출’도 사전 요약 생성과 구분해야 한다.

TF-IDF는 단어가 문서에 얼마나 자주 나오고 다른 문서에서는 얼마나 드문지를 수치로 계산하는 검색 방법이다. 이 구현은 **원문 후보만으로 단어의 희소성을 계산한 뒤 그 가중치를 원문과 요약 모두에 적용**한다. R0·RF·RH·C의 이 검색 단계에는 임베딩 모델이나 LLM을 이용한 후보 재평가를 사용하지 않았다. 토큰 길이를 세는 작업도 요약 문장을 생성하는 작업과 별개다.

RF·RH의 요약에는 답변과 같은 **Qwen2.5-Coder-7B-Instruct Q5_K_M**을 사용했다. RF에는 ‘동작·정확한 수식·분기·문자열 규칙·호출·상수를 보존하라’, RH에는 ‘하위 요약의 흐름·관계·예외와 제공된 수치·조건을 보존하라’고 지시했다. 두 단계 모두 **영어 100단어 이내를 요청하고 출력은 최대 256토큰**으로 제한했으며, 질문과 정답은 입력하지 않았다. 이는 생성 지시이지, 모든 세부 정보가 보존됐다는 검증 결과는 아니다.

RH의 파일·프로젝트 요약은 **하위 요약을 입력으로 다시 생성**한다. 그 단계에서 원문을 다시 대조해 검증하지는 않는다. C의 중복 제거는 저장된 식별자와 본문을 사용하는 일반 프로그램 처리이며, LLM이 내용을 다시 쓰지 않는다. 이러한 준비 과정과 실제 저장 예제를 아래에서 연결해 볼 수 있다.

'''

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

RF는 **함수 요약 방식**이다. R0이 준비한 원문 후보를 그대로 두고, 각 함수와 연결된 코드 묶음을 LLM으로 읽어 만든 요약을 추가한다. 위 예제의 `remaining` 관련 코드 묶음을 요약하면, 해당 함수뿐 아니라 `sellable`과 `SAFETY_STOCK`도 요약의 재료가 된다. 별도로 저장한 함수 단독 원문 후보에는 중복 요약을 만들지 않는다. 질문을 받기 전에 생성하고 저장한다.

실제로 생성한 요약 항목의 연결 정보는 다음과 같다. `level: 1`은 함수 단계, `children`은 직접 요약한 원문 후보, `source_uris`는 그 후보의 출처를 뜻한다.

```json
{rfjson}
```

이 항목의 `text`에는 출처 제목과 다음 **실제 LLM 요약 본문**이 저장되었다. 아래는 읽기 쉽게 줄만 나눴다.

```text
{textwrap.fill(body,76)}
```

이 요약은 ‘보유 수량에서 예약 수량과 안전재고를 빼고, 음수가 되지 않게 한다’는 설명이다. 출처 목록에는 `SAFETY_STOCK`이 있지만 위 함수 요약 본문에는 **숫자 `3`이 빠져 있다.** 출처가 연결되어 있다는 것과 세부 값이 남아 있다는 것은 다르다.

질문이 오면 **원문 후보와 함수 요약 후보를 한 목록에 놓고** R0과 같은 단어 유사도로 순위를 정해 1,024토큰 안에 넣는다. 함수 주소만 전달하거나 요약만 전달하는 방식이 아니다. 요약이 원문보다 짧을 수는 있지만, 원문과 요약을 함께 선택할 수 있어 전체 입력이 반드시 줄지는 않는다. 또한 ‘출처에 포함되었다’는 사실만으로 요약에 그 출처의 모든 규칙이 남아 있다고 볼 수 없다.

### RH: 함수 설명들을 다시 요약해 파일·프로젝트 설명을 만든다

RH는 **계층 요약 방식**이다. RF의 함수 요약들을 파일별로 묶어 다시 요약하고, 파일 요약들을 모아 프로젝트 요약을 만든다. 저장하는 연결 구조의 일부는 다음과 같다.

```json
{rhjson}
```

이 작은 예제에는 함수 요약 3개, 파일 요약 2개, 프로젝트 요약 1개가 저장됐다. `policy.py`에는 함수가 없어 독립된 파일 요약은 없으며, 상수 값은 `sellable`의 참조 묶음과 `rules.py` 요약을 통해 전달된다.

이 예제에서 실제 생성한 상위 요약은 다음과 같다.

| 저장 항목 | 실제 요약 본문 |
|---|---|
| `service.py` 파일 요약 | {filebody.replace(chr(10),' ').replace('|','&#124;')} |
| 프로젝트 요약 | {projectbody.replace(chr(10),' ').replace('|','&#124;')} |

앞의 `remaining` 함수 요약에서 빠졌던 값 `3`이 이 프로젝트 요약에는 들어 있다. `rules.py`의 설명까지 함께 다루기 때문이다. 다만 이 한 예제가 상위 요약에서 모든 세부 값이 항상 보존된다는 뜻은 아니다.

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
| RH | 함수→파일→프로젝트로 재귀 요약하고 모든 단계에서 검색 | 임베딩 모델로 비슷한 의미의 내용을 찾아 자동으로 묶는 원 논문의 과정까지 재현하지 않음 |
| C | RH의 요약 구조와 검색을 그대로 사용한 뒤 입력을 정리 | 새로운 요약 방식이나 RAPTOR 고유 기능이라고 주장하지 않음 |

여기서는 코드의 참조 관계와 파일 경계로 내용을 묶고, 단어의 출현 빈도와 희소성으로 계산하는 TF-IDF 점수로 검색한다. 따라서 결과는 **이번 구현에 대한 평가**이며, RAPTOR 원 논문 전체의 성능을 검증하거나 반박하는 실험은 아니다. 예제 원문·요약 생성 요청·실제 선택 자료는 [예제 기록]({BASE}/index_example/generated.json)에 보존했다.

'''

def mechanism_interpretation(s,facts):
    f=facts['arms'];pairs=facts['pairs'];b=facts['B_expansion_diagnostic']
    rf=f['RF'];rh=f['RH'];r0=f['R0'];full=f['FULL']
    pct=lambda a:f"{f[a]['accuracy_pct']:.1f}%"
    leaf_total=rf['leaf_selections_one_repeat']*3;aux_total=rf['auxiliary_leaf_selections_one_repeat']*3
    return f'''### 9.8 자료를 만드는 과정이 정답률에 어떤 영향을 주었을까?

아래 **확인**은 구축 코드와 기존 2,016개 실제 답변 기록에서 직접 확인한 사실이다. **추측**은 그 사실에 근거한 가능한 설명이다. 이 절은 사후 분석이며, 원인을 하나씩 바꾸는 추가 실험을 수행한 결과는 아니다. 정답 수는 반복을 제외한 같은 96문제 기준이다.

**A — {f['A']['correct']}/96, {pct('A')}.** 확인: 미리 지정한 출발 함수와 선택이 일치한 문제는 {f['A']['selector_matches_designated_target']}/96개였고, 필요한 원문 평균 포함률은 {f['A']['raw_inclusion_pct']:.1f}%였다. 파싱으로 만든 주소록 자체에는 함수의 동작 설명이 없으며, 선택 후에도 같은 파일 안에서만 확장한다. **추측:** 출발 함수 선택과 파일 경계 때문에 계산에 필요한 다른 파일의 규칙을 충분히 확보하지 못한 점이 낮은 정답률의 한 원인일 수 있다. 이는 적은 입력량을 얻는 과정에서 생긴 범위 제한으로 해석할 수 있다.

**B — {f['B']['correct']}/96, {pct('B')}.** 확인: A와 선택한 출발 함수가 {facts['AB_same_selected_function_questions']}/96문제에서 같았지만, 필요한 원문 평균 포함률은 {f['B']['raw_inclusion_pct']:.1f}%로 높아졌다. A보다 {len(pairs['A->B']['wins'])}문제에서 개선되고 {len(pairs['A->B']['losses'])}문제에서 악화됐다. 출발 함수가 지정값과 일치한 {b['target_matches']}문제 중 {b['missing_required_before_packing']}문제는 토큰을 채우기 전부터 필요한 원문을 모두 모으지 못했다. 이 집단에서 모아 둔 필수 원문이 토큰 제한 때문에 빠진 경우는 {b['required_lost_during_packing']}개였다. **추측:** 파일 간 원문 보강이 일부 문제에 도움이 됐지만, 2차례의 정적 확장만으로 깊은 참조나 별도 경로를 모두 확보하기 어려웠을 수 있다. 입력 범위와 표시 형식도 달라지므로 순수한 확장 효과의 크기를 이 결과만으로 분리하지는 않는다.

**R0 — {r0['correct']}/96, {pct('R0')}.** 확인: 필요한 원문 평균 포함률은 {r0['raw_inclusion_pct']:.1f}%, 지정 원문이 모두 들어간 문제는 {r0['all_raw_questions']}/96개였다. **추측:** 함수 하나의 선택에 묶이지 않고 여러 파일의 원문을 찾으며, 자연어로 바꾸는 과정 없이 수식·상수·조건을 전달한 점이 이번 표본에서 유리했을 수 있다. 다만 원문이 모두 있는 {r0['all_raw_questions']}문제 중 {r0['wrong_with_all_raw']}문제도 틀렸다. 검색 이후의 코드 해석·계산·정확한 출력 생성 역시 병목 후보다.

**RF — {rf['correct']}/96, {pct('RF')}.** 확인: R0보다 {len(pairs['R0->RF']['losses'])}문제에서 악화됐고 새로 맞힌 문제는 {len(pairs['R0->RF']['wins'])}개였다. 필요한 원문 평균 포함률은 {rf['raw_inclusion_pct']:.1f}%로 내려갔다. 함수 요약 선택 {leaf_total:,}건 중 {aux_total:,}건({rf['auxiliary_leaf_selection_pct']:.1f}%)은 파일을 늘리려고 추가한 보조 함수의 요약이었다. 이 보조 함수들은 평가 문제의 필수 원문 목록에 없다. **추측:** 같은 1,024토큰 안에 요약이 들어오면서 세부 원문이 밀려나고, 질문과 표현만 비슷한 설명이 공간을 차지했을 가능성이 있다. 짧게 요약하는 과정에서 수치·분기 조건이 빠지는 문제도 가능한 원인이다. 다만 모든 오답을 요약의 정보 손실 하나로 설명할 수는 없다.

**RH — {rh['correct']}/96, {pct('RH')}.** 확인: RF보다 새로 맞힌 문제는 {len(pairs['RF->RH']['wins'])}개였다. 파일 요약이 선택된 문제는 {rh['questions_with_file_summary']}/96개, 프로젝트 요약이 선택된 문제는 {rh['questions_with_project_summary']}/96개였다. **추측:** 계층을 만들어도 상위 요약이 답변에 거의 사용되지 않아, 그 이점이 성능으로 연결될 기회가 적었던 것으로 보인다. 유일하게 개선된 캐시 키 문제(`eval_cache__canonical_key`)의 파일 요약도 주로 보조 함수들을 설명했다. 이 한 사례를 ‘상위 요약이 정확한 규칙을 새로 제공해서 개선됐다’는 증거로 해석하기는 어렵다. 요약 선택과 입력 구성의 변화가 출력을 바꿨을 가능성도 있다.

**C — {f['C']['correct']}/96, {pct('C')}.** 확인: RH와 선택 자료 및 고유 본문은 같고, 총 입력은 {facts['compaction']['input_reduction_pct']:.1f}% 줄었다. 정답은 {len(pairs['RH->C']['wins'])}문제 개선·{len(pairs['RH->C']['losses'])}문제 악화로 총수가 같았다. **추측:** 중복·제목·배치의 변화가 모델이 자료를 읽고 답을 구성하는 데 영향을 줬을 수 있다. 본문 보존은 확인했지만, 모델 출력까지 보존되는 것은 아니다. 새 요약 정보를 더하지 않았으므로 정확도 개선이 자동으로 생길 이유도 없다.

**파일 전체 — {full['correct']}/96, {pct('FULL')}.** 확인: 필요한 원문 평균 포함률은 {full['raw_inclusion_pct']:.1f}%이며, 지정 원문이 모두 들어간 문제는 {full['all_raw_questions']}/96개다. 다른 파일의 정의는 따라가지 않고 관계없는 보조 함수도 모두 전달한다. 입력 잘림은 없었으며, {full['output_limit_questions']}문제는 세 반복 모두 답변 출력 한도에서 끝났다. **추측:** 한 파일을 완전히 읽어도 파일 밖의 필수 규칙은 빠지고, 파일 안에서는 필요한 규칙을 많은 보조 코드 사이에서 구분해야 하는 점이 불리했을 수 있다. 출력 한도 종료도 측정된 오답의 일부다.

**RF·RH의 검색에서 추가로 발견한 단서.** 평가용 6개 프로젝트 모두에서 원문 후보에는 단어 `function`이 없었지만, 함수 요약에는 전부 들어 있었다. 현재 구현은 단어 희소성을 원문 후보로만 계산하므로 이 단어를 요약에서도 희귀한 단어처럼 가중한다. `function`을 포함한 질문은 {facts['lexical_diagnostic']['questions_containing_term']}개였다. **추측:** 이런 질문에서는 구체적 코드 관계보다 반복되는 설명 용어가 검색 점수에 영향을 줬을 수 있다. 전체 후보로 희소성을 다시 계산하는 비교 실험은 하지 않았으므로, 실제 하락 중 얼마가 이 요인 때문인지는 아직 모른다.

**원문 누락만으로 설명되지 않는 실제 사례도 있다.** `can_edit_own('u1',['document:write'],100,3700)` 문제에서는 R0와 RF 모두 지정 원문을 전부 전달했지만, 정답 `false`에 대해 R0는 `false`, RF는 `true`라고 답했다. 따라서 ‘원문을 더 찾으면 모든 오류가 해결된다’거나 ‘요약이 틀려서 모든 오류가 생겼다’고 단정할 수 없다. 특히 R0의 오답 {96-r0['correct']}개 중 {r0['failures_by_question'].get('wrong_answer',0)}개는 정답 값 불일치, {r0['failures_by_question'].get('invalid_json',0)}개는 JSON 형식 오류였다. 낮은 점수를 출력 형식 문제만으로 설명할 수도 없다.

원인을 더 분리하려면 **정답에 필요한 원문을 고정한 채 요약만 추가**, **원문 전용 가중치와 전체 후보 가중치 비교**, **같은 RH 선택에서 중복 제거만 적용하거나 제목만 축약**하는 실험이 필요하다. 이는 후속 검증 제안이며 이번에 실행한 실험 목록에 포함하지 않았다. 구축 방식과 정답률에 관한 위 해석은 이번 합성 코드·모델·질문·길이 제한에 대한 가설로 읽어야 한다.

코드와 기록을 대조해 재계산한 근거는 [생성 과정·오답 사후 분석]({BASE}/{REVISION}/mechanism_facts.json)에 보존했다. 기존 정답률이나 평가 기준은 바꾸지 않았다.

'''

def results(s,facts):
    allp=s['populations']['all96'];m=allp['metrics'];t=allp['tokens'];build=s['build']['evaluation']
    highest=max(m[a]['question_equivalent_correct'] for a in ARMS)
    highest_names='·'.join(NAMES[a] for a in ARMS if m[a]['question_equivalent_correct']==highest)
    least_input=min(ARMS,key=lambda a:t[a]['total'])
    headline=table(['방식','정답 / 96','정답률','대표 시간','p95','평균 근거 토큰','평균 총 입력 토큰','전체 파일 대비 입력 절감'],[
        [NAMES[a],count(m[a]['question_equivalent_correct']),f"{100*m[a]['accuracy']:.1f}%",f"{m[a]['mean_query_seconds']:.2f}초",f"{m[a]['request_p95_seconds']:.2f}초",f"{t[a]['context']:.1f}",f"{t[a]['total']:.1f}",f"{t[a]['saving_total_vs_full_pct']:.1f}%"] for a in ARMS])
    context_table=table(['방식','평균 선택 호출 입력','평균 답변 호출 입력','질문 내 최대 호출 입력의 평균','8,192토큰 중 평균 점유'],[
        [NAMES[a],f"{t[a]['selector']:.1f}",f"{t[a]['answer']:.1f}",f"{t[a]['peak']:.1f}",f"{t[a]['window_pct']:.2f}%"] for a in ARMS])
    contrasts=table(['비교','정답률 차이','탐색적 95% 구간','보정 p값','개선 / 악화 / 동일 문제'],[
        [f"{NAMES[c['higher']]} − {NAMES[c['base']]}",f"{c['delta_pp']:+.1f}%p",f"{c['ci95_pp'][0]:+.1f} ~ {c['ci95_pp'][1]:+.1f}%p",f"{c['holm_p_three_quality_contrasts']:.3f}",f"{c['win']} / {c['loss']} / {c['tie']}"] for c in s['comparisons'].values()])
    first=s['historical_matched_questions']['original48'];firstc=s['historical_matched_questions']['original48_C']['C']
    historical=table(['방식','최초 작은 파일: 같은 48문제','이번 큰 파일: 같은 48문제','나머지 48문제: 큰 파일'],[
        [NAMES[a],count(first[a]['old_correct']) if a in first else f"{count(firstc['old_correct'])} (후속 1회 재확인)" if a=='C' else '최초 실험 없음',
         count(s['populations']['original48']['metrics'][a]['question_equivalent_correct']),count(s['populations']['additional48']['metrics'][a]['question_equivalent_correct'])] for a in ARMS])
    second=s['historical_matched_questions']['additional48']
    second_table=table(['01번 보고서의 2차와 동일한 별도 48문제','당시 작은 파일 정답','이번 큰 파일 정답'],[
        [NAMES[a],count(second[a]['old_correct']),count(second[a]['large_correct'])] for a in ['A','RH','C']])
    prep_rows=[]
    eval_projects={q['project'] for q in s['questions']}
    prep_calls=[c for c in exp.audit.rows(exp.OUT/'model_calls.jsonl') if c['purpose'].startswith('build_') and c['meta']['project'] in eval_projects]
    for purpose,label in [('build_leaf','함수 요약'),('build_level_2_batch','파일 안 중간 묶음 요약'),('build_level_2','최종 파일 요약'),('build_level_3','프로젝트 요약')]:
        b=build['by_purpose'].get(purpose,{'calls':0,'input_tokens':0,'output_tokens':0,'model_wall_seconds':0})
        maximum=max((c['input_tokens'] for c in prep_calls if c['purpose']==purpose),default=0)
        prep_rows.append([label,b['calls'],f"{b['input_tokens']:,}",f"{b['output_tokens']:,}",f"{maximum:,}",f"{b['model_wall_seconds']/60:.1f}분"])
    prep=table(['준비 단계: 평가용 6개 프로젝트','실제 생성 수','입력 합계','출력 합계','한 호출 최대 입력','모델 호출 시간 합계'],prep_rows)
    prep_peak=max(c['input_tokens'] for c in prep_calls)
    batches=build['by_purpose'].get('build_level_2_batch',{}).get('calls',0)
    hierarchy_actual=(f'실제로 중간 묶음 요약 {batches}개가 필요했다.' if batches else
        '이번 평가용 데이터에서는 모든 파일의 자식 요약이 입력 한도 안에 들어가 중간 묶음 요약은 0개였고, 함수→파일→프로젝트의 3단계를 사용했다.')
    assets=exp.read(exp.OUT/'assets.json');bad={};affected={}
    for project,asset in assets.items():
        lookup={x['id']:x for x in asset['summaries']}
        bad[project]={k for k,x in lookup.items() if not x['generation_ok']}
        def contains_limited(k):
            return k in bad[project] or (k in lookup and any(contains_limited(c) for c in lookup[k]['children']))
        affected[project]={k for k in lookup if contains_limited(k)}
    records=exp.audit.rows(exp.OUT/'results.jsonl')
    affected_text=' · '.join(f"{a} {sum(any(c['id'] in affected[r['project']] for c in r['chosen']) for r in records if r['arm']==a)}/288회" for a in ['RF','RH','C'])
    selected=table(['방식','함수 요약 선택 수','상위 요약 선택 수','요약이 들어간 문제 / 96','상위 요약이 들어간 문제 / 96','지정 원문 평균 포함률'],[
        [NAMES[a],m[a]['selected_levels'].get('1',0),sum(m[a]['selected_levels'].get(k,0) for k in ['2','3']),m[a]['questions_with_summary'],m[a]['questions_with_higher_summary'],f"{100*m[a]['raw_evidence_recall']:.1f}%"] for a in ['R0','RF','RH','C']])
    cr=s['comparisons']['C-RH'];comp=s['compaction']
    categories={'single_function':'한 함수의 계산','cross_file':'여러 파일을 잇는 계산','boundary':'경계 조건',
        'semantic':'자연어로 설명한 동작','change_impact':'설정 변경의 영향','architecture':'함수 호출 구조'}
    category_table=table(['질문 종류','문제 수','R0','RF','RH','C'],[
        [label,m['R0']['by_category'][key]['unique_questions']]+[count(m[a]['by_category'][key]['question_equivalent_correct']) for a in ['R0','RF','RH','C']]
        for key,label in categories.items()])
    limittext=' · '.join(f"{'파일 전체' if a=='FULL' else a} {m[a]['output_limit_calls']}회" for a in ARMS)
    stable=all(v['different_raw_output_questions']==0 for v in s['repeat_stability'].values())
    stability=('새 세 방식도 각 문제의 세 출력이 모두 같았다. 따라서 정답 수는 반복을 제외한 96문제 기준이다.' if stable else '새 방식 일부에서 반복 출력이 달랐다. 정답 수는 문제별 3회 정답 비율의 합계이므로 소수가 될 수 있다. 반복을 독립 문제로 취급하지 않았다.')
    interpretation=[]
    for key,phrase in [('RF-R0','함수 요약 추가'),('RH-RF','파일·프로젝트 요약 추가'),('C-RH','입력 정리')]:
        c=s['comparisons'][key];h,b=c['higher'],c['base'];diff=m[h]['question_equivalent_correct']-m[b]['question_equivalent_correct']
        sig='보정 검정에서 차이가 관찰되었다' if c['holm_p_three_quality_contrasts']<.05 else '보정 검정에서 정확도 차이를 확정하지 못했다'
        difference=('+' if diff>0 else '')+count(diff)
        interpretation.append(f"- **{phrase}({b}→{h}):** 정답 {count(m[b]['question_equivalent_correct'])}→{count(m[h]['question_equivalent_correct'])}개({difference}개). {sig}.")
    examples=[]
    for label,pred in [('요약을 추가해 맞힌 사례',lambda q:q['arms']['RF']['correct'] and not q['arms']['R0']['correct']),
                       ('요약을 추가해 틀린 사례',lambda q:q['arms']['R0']['correct'] and not q['arms']['RF']['correct']),
                       ('정리 후 판정이 달라진 사례',lambda q:q['arms']['RH']['correct']!=q['arms']['C']['correct'])]:
        candidates=[q for q in s['questions'] if pred(q)]
        if candidates:
            q=candidates[0]
            examples.append(f"**{label}** — `{q['task_id']}`\n\n{q['question']}\n\n"+table(['항목','판정용 답변'],[['정답',literal(q['expected'])]]+[[NAMES[a],'JSON 형식 오류' if q['arms'][a]['failure']=='invalid_json' else literal(q['arms'][a]['parsed_answer'])] for a in ['R0','RF','RH','C']]))
    return f'''## 9. 같은 큰 파일에 RF·RH·C를 추가한 실제 실험

### 9.1 첫 실험과 결과가 달라 보이는 이유부터 구분하면

01번 보고서의 최초 실험은 **48문제**, 최근 비교는 그 문제와 추가 48문제를 합친 **96문제**다. 정답 개수를 분모 없이 비교하면 개선 폭을 오해할 수 있다. 아래는 질문 문장과 정답이 같은 최초 48문제로 맞춘 비교다.

{historical}

최초 실험에는 C와 파일 전체 방식이 없었다. C의 48문제 수치는 01번 보고서에 기록된 **후속 재확인 1회**이며, 이번에는 3회 실행했다. 파일을 키울 때 원래 기능은 유지했지만 관계없는 함수·검색 후보와 줄 위치도 함께 바뀌었다. 요약 역시 커진 파일에서 새로 생성했다. 따라서 아래 차이는 파일 크기 하나만의 인과 효과가 아니다. 최초 실험의 시간은 일부 호출 비용을 공유·합산했으므로 이번 실측 시간과 직접 비교하지 않는다.

01번 보고서 2차의 **A 9개·RH 10개·C 11개**는 위 표의 ‘나머지 48문제’에 해당한다. 이 문제들끼리만 맞춰 비교하면 다음과 같다. RF는 당시 이 별도 48문제로 평가하지 않았다.

{second_table}

### 9.2 이번에 새로 실행한 범위

| 항목 | 고정한 조건 |
|---|---|
| 원문·질문 | 8절과 바이트까지 동일한 큰 파일, 동일한 96문제·정답. 평가용 6개 합성 프로젝트, 파일당 4,099~4,157토큰 |
| 새 평가 | RF·RH·C 각각 96문제 × 3회 = **864개 실제 답변** |
| 비교 기준 | 8절의 A·B·R0·파일 전체 **1,152개 실제 답변을 보존**하여 함께 제시 |
| 모델·생성 | 같은 Qwen2.5-Coder-7B Q5_K_M, M3 Pro, 컨텍스트 8,192, 출력 128, temperature 0, seed 1, 입력 계산 재사용 끔 |
| 정답 판정 | JSON 정답 값·자료형·요구한 목록 순서까지 일치해야 정답. 형식 실패와 출력 한도 종료도 오답에 포함 |
| 근거 선택 | RF·RH는 최대 1,024토큰. C는 RH의 동일 선택 결과를 정리하고 여유 공간을 채우지 않음. 파일 전체는 원문 전체를 전달 |
| 요약 | 질문·정답을 입력하지 않고 원문에서 새로 생성. 함수 요약은 출력 최대 256토큰·100단어 이내 지시, 상위 요약도 같은 지시·한도 |
| 실행 순서 | 매 반복에서 세 방식의 6가지 순서를 각각 16번씩 배치. 질문 블록 순서는 고정 시드로 무작위화 |
| 별도 개발 확인 | 평가와 다른 8문제 × 3방식 = 24답변. 주 점수에서 제외 |

RF·RH·C는 같은 세션에서 번갈아 실행했지만, A·B·R0·파일 전체는 앞선 세션이다. **새 세 방식 사이의 시간 비교는 같은 세션이며, 이전 네 방식과의 시간 차이는 세션 상태까지 통제한 결과가 아니다.** RF·RH·C의 검색 규칙과 답변 지시문은 01번 실험의 해당 방식을 유지했다. 토큰 계산과 모델 파일은 8절의 큰 파일 실험과 같다.

파일 단위 상위 요약이 입력 한도에 들어가지 않을 때만 중간 묶음 요약을 추가하도록 **생성 전에 규칙을 고정**했다. 자식 요약을 잘라 버리지 않는다. 이 처리까지 포함한 변형이며, 원 논문 구현 전체를 재현한 것은 아니다.

{hierarchy_actual}

이전 요약 준비 코드는 요약 실패 시 중단한다. 이번에는 사전에 정한 규칙에 따라 **출력 한도에서 끝난 비어 있지 않은 요약도 생성 기록에 상태를 남기고 후보로 보존**한다. 생성 조건의 이 차이도 공개하며, 해당 횟수·비용과 실제 답변에 선택됐는지는 9.6절에 제시한다.

### 9.3 일곱 방식의 정답·시간·입력량

{headline}

이 96문제의 관측값에서 **정답 수가 가장 많은 방식은 {highest_names}({count(highest)}/96)**이고, **질문당 총 입력이 가장 적은 방식은 {NAMES[least_input]}({t[least_input]['total']:.1f}토큰)**이다. 정확도와 입력량 중 무엇을 우선하느냐에 따라 선택이 달라진다. 통계적 불확실성은 9.5절, 사전 요약 비용은 9.6절에서 함께 살펴본다.

{stability} 대표 시간은 문제별 세 번의 중앙값을 구한 뒤 평균한 값이며, p95는 전체 요청의 95%가 끝나는 시간이다. ‘근거’는 코드·요약·출처 제목 등을 포함한 선택 자료이고, ‘총 입력’에는 질문·지시문·대화 형식과 A·B의 함수 선택 호출도 포함한다. 사전 요약 생성과 출력 토큰은 이 입력 표에서 제외하고 9.6절에 별도로 제시한다.

출력 최대 128토큰에서 끝난 평가 호출: **{limittext}**. 이 응답들은 오답으로 포함했으며 성공한 재시도로 대체하지 않았다. 입력 잘림이나 전송 실패 여부는 검증 기록에서 확인했다. 파일 전체 방식의 21회 제한 종료라는 8절의 조건도 그대로 유지된다.

### 9.4 A의 목적에 맞춰 컨텍스트 윈도우를 비교하면

{context_table}

RF·RH·C는 질문당 답변 호출 1회이므로 답변 입력=총 입력=한 호출 입력이다. A·B의 선택 호출과 답변 호출은 별도 컨텍스트를 사용하므로 누적 입력을 한 번의 점유량으로 읽으면 안 된다. ‘최대 호출 입력의 평균’은 각 질문에서 가장 큰 호출을 고른 뒤 평균한 값이다. 위 점유율은 입력만이며 출력 공간은 별도 확보한다.

전체 파일 대비 입력 절감률은 **1 − 방식의 평균 총 입력 / 전체 파일의 평균 총 입력**으로 계산했다. RF·RH도 1,024토큰 상한을 두므로 큰 파일 전체보다 짧다는 사실 자체는 예상되는 결과다. 요약의 가치 여부는 같은 상한의 R0보다 얼마나 더 정확한지와 준비 비용까지 함께 봐야 한다.

### 9.5 요약과 정리에서 각각 얼마나 달라졌나?

{contrasts}

이번 추가 실험에서 미리 지정한 세 비교에 대해서만 Holm 보정을 적용했다. 6개 프로젝트 단위의 46,656가지 재표집으로 95% 구간을, 프로젝트별 부호 뒤집기로 p값을 계산했다. 두 계산법이 달라 구간과 검정 결과를 동일시하지 않는다. 같은 문제의 세 반복은 독립된 세 문제가 아니며, 이 작은 합성 표본은 탐색적 근거다.

**검정의 제약:** 프로젝트가 6개이면 이 양측 부호 검정의 최소 p값은 2/64이고, 세 비교를 Holm 보정한 최소값은 0.09375다. 따라서 이 설계만으로 0.05 기준의 우위를 확정할 수 없다. 보정 p값이 크다는 사실을 ‘효과가 없다’거나 ‘성능이 같다’는 증거로 읽지 않고, 관측 차이와 추정 구간을 함께 본다.

{chr(10).join(interpretation)}

C는 RH보다 근거 입력을 **{comp['context_reduction_pct']:.1f}%**, 전체 입력을 **{comp['input_reduction_pct']:.1f}%** 줄였다. 같은 세션에서 대표 응답 시간은 **{m['RH']['mean_query_seconds']:.2f}→{m['C']['mean_query_seconds']:.2f}초**, 변화율은 **{cr['latency_reduction_pct']:.1f}% 단축**이었다. 단축률이 음수이면 더 오래 걸렸다는 뜻이다. 속도 변화의 탐색적 95% 구간은 {cr['latency_reduction_ci95_pct'][0]:.1f}~{cr['latency_reduction_ci95_pct'][1]:.1f}%다. 독립 검증에서 RH와 C의 **288쌍 모두 선택 자료가 같고, 고유 코드·import·요약 본문이 보존됨을 확인했다.**

문제별 판정에서는 C가 RH보다 개선된 문제가 **{cr['win']}개**, 악화된 문제가 **{cr['loss']}개**다. 총정답 수만으로 개별 문제의 결과까지 같다고 판단하면 안 된다.

실제로 어떤 종류의 근거를 골랐는지도 확인했다. ‘선택 수’는 288번의 호출에서 선택한 항목 수 합계로, 고유한 요약 문서 수와 다르다.

{selected}

원문 포함률은 필요한 원문 코드가 실제 입력에 들어간 비율이다. 요약의 출처 목록에 함수가 들어 있다는 이유만으로 그 함수의 내용을 모두 전달했다고 계산하지 않았다. 요약이 맞는 내용을 전달할 수도 있으므로, 원문 포함률만으로 요약 방식의 답변 품질을 판정할 수도 없다.

질문 종류별 정답 수는 다음과 같다. 종류별 표본이 작으므로, 이 표만으로 특정 종류에 대한 우위를 일반화하지 않는다.

{category_table}

### 9.6 요약을 미리 만드는 비용

{prep}

평가용 요약 생성은 총 **{build['summary_calls']:,}회**, 입력 **{build['input_tokens']:,}토큰**, 출력 **{build['output_tokens']:,}토큰**, 모델 호출 시간 합계 **{build['model_wall_seconds']/60:.1f}분**이었다. 단일 서버에서 순서대로 생성했으며, 이 시간은 각 요청의 토큰 계산부터 모델 응답을 받을 때까지의 합계다. 서버 시작·파일 준비·그룹 구성·로그 쓰기까지 포함한 전체 준비 시간은 더 길다. 개발용 프로젝트는 별도 {s['build']['development']['summary_calls']}회이고 위 표에서 제외했다.

사전 요약 중 한 호출의 최대 입력은 **{prep_peak:,}토큰**, 8,192토큰의 **{100*prep_peak/8192:.1f}%**였다. 출력 공간은 별도로 필요하다. 질문할 때의 입력이 작아졌다고 해서 색인을 만들 때도 같은 작은 컨텍스트만 필요하다는 뜻은 아니다.

RF에는 함수 요약까지만 필요하다. RH·C는 그 요약을 공유하고 파일·프로젝트 요약을 추가로 사용한다. 세 방식 각각의 비용인 것처럼 공유 요약 비용을 세 번 더하지 않았다. 사전 요약에서 출력 한도에 도달한 호출은 **{build['output_limit_calls']}회**이며, 중단 시점까지 생성된 요약 본문을 그대로 저장하고 상태를 표시하도록 사전에 정했다.

출력이 중단된 요약 또는 그것을 재료로 삼은 상위 요약이 실제 선택된 평가 호출은 **{affected_text}**였다. 이는 선택된 자료의 출처 연결까지 따라가 확인한 횟수다. 요약의 생성 상태와 실제 답변에 전달됐는지를 구분해 기록했다.

A·B·R0·파일 전체에는 이 사전 LLM 요약 생성 단계가 없다. 색인·참조 관계·단어 가중치를 계산하는 컴퓨터 처리 비용과, 질문 중 사용하는 LLM 호출은 별개의 비용이다.

질문이 늘면 일회성 준비 비용은 여러 질문에 나누어 볼 수 있다. 예를 들어 질의당 상각 입력은 `질의 입력 + 해당 방식의 준비 입력 / 재사용한 질문 수`다. 실제 코드 변경에 따른 재생성 횟수·갱신 비용·비용 회수 시점은 이번 실험에서 측정하지 않았다.

### 9.7 같은 질문의 실제 답변

표는 첫 번째 반복의 답변에서 읽어낸 판정용 JSON값이다. JSON으로 읽을 수 없는 응답은 ‘JSON 형식 오류’로 표시했다. 응답 원문과 판정 실패 사유는 평가 원자료에 함께 보존했다.

{(chr(10)*2).join(examples)}

위 사례는 판정이 바뀐 질문 중 ID 순서로 처음 나타난 것을 골라 보여 준 것이다. 어느 문장이나 요약 오류가 답변 변화를 일으켰는지는 따로 제거 실험을 하지 않았으므로 원인으로 단정하지 않는다.

{mechanism_interpretation(s,facts)}

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
    facts=exp.read(out/REVISION/'mechanism_facts.json')
    assert all(exp.v1.sha(path)==h for path,h in facts['source_hashes'].items())
    original=(out/'history/report_before_raptor_large.md').read_text()
    manifest=out/'report_manifest.json'
    allowed={exp.audit.digest(original)}
    if manifest.exists():allowed.add(exp.read(manifest)['report_digest'])
    assert exp.audit.digest(exp.REPORT.read_text()) in allowed,'Report edited externally; reconcile instead of overwriting'
    example=exp.read(out/'index_example/generated.json')
    text=original.replace('# 현재 색인(A)·파일 간 확장(B)·원문 검색(R0)·파일 전체 입력: 실제 실험 비교',
        '# 코드 검색·RAPTOR 요약·파일 전체 입력: 실제 실험 비교')
    text=text.replace('질문: 코드 일부를 골라 보내는 방식은 파일 하나를 통째로 보내는 것보다 컨텍스트를 아끼면서 더 잘 답하는가?',
        '질문: 코드 일부나 요약을 골라 보내면 파일 하나를 통째로 보내는 것보다 컨텍스트를 아끼면서 더 잘 답하는가?')
    date=datetime.fromisoformat(s['created_at_utc']).astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y년 %m월 %d일')
    intro=(f'**최신 추가 실험 — {date} 집계:** 8절과 동일한 큰 파일·96문제에서 RF(함수 요약)·RH(계층 요약)·C(계층 요약 정리)를 '
           '**864회 새로 실행**했다. 일곱 방식의 비교와 첫 실험과 같은 48문제의 비교는 **9절**, 색인·요약의 구체적 예시는 **1절**에 있다.\n\n')
    m=s['populations']['all96']['metrics'];t=s['populations']['all96']['tokens']
    intro+=(f"**새 결과 요약:** 정답 수는 RF **{count(m['RF']['question_equivalent_correct'])}개**, RH **{count(m['RH']['question_equivalent_correct'])}개**, C **{count(m['C']['question_equivalent_correct'])}개**다. "
        f"같은 96문제의 원문 검색(R0)은 {count(m['R0']['question_equivalent_correct'])}개였다. 질문당 총 입력은 RF {t['RF']['total']:.1f}, RH {t['RH']['total']:.1f}, C {t['C']['total']:.1f}토큰이며, "
        '사전 요약 생성 비용은 9.6절에서 별도로 다룬다.\n\n')
    intro+='**설명 보강:** 각 방식이 파싱·규칙 계산·LLM 중 무엇으로 자료를 만드는지는 **1절**, 생성 방식과 정답률을 연결한 확인 사실과 합리적 추측은 **9.8절**에 정리했다.\n\n'
    text=text.replace('\n\n**추가 실험:**','\n\n'+intro+'**앞선 큰 파일 실험:**',1)
    text=text.replace('실험일: 2026년 10월 24일 · 동일한 96문제 × 방식별 3회 · 네 방식 모두 RAPTOR 요약 없음',
        '기존 네 방식 실험일: 2026년 10월 24일 · 동일한 96문제 × 방식별 3회 · A·B·R0·파일 전체는 RAPTOR 요약 없음')
    text=text.replace('## 1. 같은 원본 파일로 A·B·R0의 색인을 비교하면','## 1. 같은 원본 파일로 색인과 RAPTOR 요약을 비교하면')
    text=text.replace('### 먼저, 원본 파일은 이렇게 생겼다',construction(facts)+'### 먼저, 원본 파일은 이렇게 생겼다',1)
    text=text.replace('예제의 LLM 답변을 만든 것은 아니며, 실제 정답률은 3절의 별도 실험에서 측정했다.',
        '이 예제에서는 질문에 대한 LLM 답변은 생성하지 않았다. 요약과 검색 자료는 실제 구현으로 생성했으며, 정답률은 3절·8절·9절의 평가에서 측정한다.')
    marker='### 파일 전체 방식까지 나란히 비교하면'
    text=text.replace(marker,explanation(example)+marker,1)
    text=text.replace('이 질문에서 답변에 넣는 코드의 범위','이 질문에서 답변에 넣는 자료의 범위',1)
    text=text.replace('| 파일 하나 전체 | 파일 경로만 제공;',
        '| RF | R0 원문 후보 + 함수·관련 코드 요약 | 단어 검색으로 고른 원문·함수 요약 일부 |\n'
        '| RH | RF 자료 + 파일·프로젝트 요약 | 여러 단계의 원문·요약 중 선택된 일부 |\n'
        '| C | RH와 같은 자료 | RH와 같은 선택 결과를 중복 제거·출처 축약 후 전달 |\n'
        '| 파일 하나 전체 | 파일 경로만 제공;',1)
    text=text.replace('R0과 파일 전체 방식은 답변 호출만 있다.','R0·RF·RH·C와 파일 전체 방식은 질문당 답변 호출만 있다. RF·RH·C의 사전 요약 생성 호출은 이 질의당 횟수와 별도다.',1)
    text=text.replace('세 색인 방식 모두 RAPTOR 요약을 사용하지 않는다.','A·B·R0은 RAPTOR 요약을 사용하지 않는다.',1)
    text=text.replace('## 작은 파일 실험의 확인 자료와 재현',results(s,facts)+'## 작은 파일 실험의 확인 자료와 재현',1)
    text,content_map=reorganize_report.reorganize(text)
    exp.v1.dump(out/reorganize_report.REVISION/'content_map.json',content_map)
    text=clarify_report_context.clarify(text)
    section_path=out/add_index_build_section.REVISION/'section.md'
    text=add_index_build_section.insert(text,section_path.read_text())
    tfidf_revision='revisions/tfidf_explanation_20261025'
    tfidf_path=out/tfidf_revision/'replacement.json'
    tfidf_edit=exp.read(tfidf_path)
    assert text==(out/tfidf_revision/exp.REPORT.name).read_text()
    assert text.count(tfidf_edit['old'])==1
    text=text.replace(tfidf_edit['old'],tfidf_edit['new'],1)
    candidate_revision='revisions/candidate_definition_20261025'
    candidate_path=out/candidate_revision/'replacement.json'
    candidate_edit=exp.read(candidate_path)
    assert text==(out/candidate_revision/exp.REPORT.name).read_text()
    assert text.count(candidate_edit['old'])==1
    text=text.replace(candidate_edit['old'],candidate_edit['new'],1)
    query_revision='revisions/query_processing_20261025'
    query_path=out/query_revision/'edits.json'
    query_edits=exp.read(query_path)
    assert text==(out/query_revision/exp.REPORT.name).read_text()
    for edit in query_edits['edits']:
        assert text.count(edit['old'])==1
        text=text.replace(edit['old'],edit['new'],1)
    walkthrough_revision='revisions/r0_walkthrough_20261027'
    walkthrough_path=out/walkthrough_revision/'replacement.json'
    walkthrough_edit=exp.read(walkthrough_path)
    assert text==(out/walkthrough_revision/exp.REPORT.name).read_text()
    assert text.count(walkthrough_edit['old'])==1
    text=text.replace(walkthrough_edit['old'],walkthrough_edit['new'],1)
    hybrid_metadata={}
    hybrid_out=exp.v1.DEFAULT_OUT/'hybrid_index_20261027'
    if (hybrid_out/'verification.json').exists():
        import report_hybrid
        text=report_hybrid.augment(text)
        hybrid_metadata={
            'additional_experiment':'hybrid_index_20261027',
            'hybrid_summary_sha256':exp.v1.sha(hybrid_out/'summary.json'),
            'hybrid_verification_sha256':exp.v1.sha(hybrid_out/'verification.json'),
            'hybrid_generator_sha256':exp.v1.sha(report_hybrid.__file__),
            'hybrid_report_generation_sha256':exp.v1.sha(hybrid_out/'report_generation.json'),
        }
    exp.REPORT.write_text(text)
    exp.v1.dump(manifest,{'generated_at_utc':exp.audit.now(),'report_sha256':exp.v1.sha(exp.REPORT),'report_digest':exp.audit.digest(text),
        'summary_sha256':exp.v1.sha(out/'summary.json'),'verification_sha256':exp.v1.sha(out/'verification.json'),
        'generator_sha256':exp.v1.sha(__file__),'editorial_revision':walkthrough_revision,
        'r0_walkthrough_sha256':exp.v1.sha(walkthrough_path),
        'r0_worked_example_sha256':exp.v1.sha(out/walkthrough_revision/'worked_example.json'),
        'query_processing_sha256':exp.v1.sha(query_path),
        'candidate_definition_sha256':exp.v1.sha(candidate_path),
        'tfidf_explanation_sha256':exp.v1.sha(tfidf_path),
        'layout_generator_sha256':exp.v1.sha(reorganize_report.__file__),
        'reader_context_generator_sha256':exp.v1.sha(clarify_report_context.__file__),
        'index_build_chapter_sha256':exp.v1.sha(section_path),
        'index_build_inserter_sha256':exp.v1.sha(add_index_build_section.__file__),
        'mechanism_revision':REVISION,
        'mechanism_facts_sha256':exp.v1.sha(out/REVISION/'mechanism_facts.json'),
        **hybrid_metadata})
    print('Updated report:',exp.REPORT,'characters:',len(text))

if __name__=='__main__':main()
