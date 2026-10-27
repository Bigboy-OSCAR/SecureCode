"""Reorder report 03 without changing measured results or source examples.

The input is the pinned, already verified editorial version. Every non-empty
source line is accounted for in the content map, including headings and the
small number of introductory/concluding passages consolidated elsewhere.
"""
from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path

REVISION = 'revisions/report_reorganization_20261025'
INPUT_SHA256 = '53a1af06219a268e1325fb9f532068c081cb7ff085b5dfcdcbf3f3e8997f43b1'


def reorganize(source: str):
    assert hashlib.sha256(source.encode()).hexdigest() == INPUT_SHA256, 'Reconcile changed source before reorganizing'
    lines = source.splitlines()
    used = {}
    mapping = []
    parts = []

    refs = {
        '3절·8절·9절의 평가': '3절의 평가',
        '9절의 준비 비용 표': '4.5절의 준비 비용 표',
        '96문제의 성능 수치는 9절': '96문제의 성능 수치는 3.1절',
        '1~7절의 작은 파일 실험': '2.1절의 작은 파일 실험',
        '3절의 ‘문제별 중앙값의 평균’': '2.4절의 ‘문제별 중앙값의 평균’',
        '6절과 같은 재고 문제': '부록 B.1과 같은 재고 문제',
        '8절과 바이트까지 동일한 큰 파일': '2.2절과 바이트까지 동일한 큰 파일',
        '8절의 A·B·R0·파일 전체': '2.2절의 A·B·R0·파일 전체',
        '8절의 큰 파일 실험': '2.2절의 큰 파일 실험',
        '9.6절에 제시': '4.5절에 제시',
        '9.5절, 사전 요약 비용은 9.6절': '부록 A.6, 사전 요약 비용은 4.5절',
        '9.6절에 별도로 제시': '4.5절에 별도로 제시',
        '파일 전체 방식의 21회 제한 종료라는 8절의 조건': '파일 전체 방식의 21회 제한 종료라는 기존 실험 조건',
    }

    def raw(a, b):
        return '\n'.join(lines[a-1:b]).strip()

    def claim(a, b, destination, action, detail=None):
        for n in range(a, b+1):
            if lines[n-1].strip():
                assert n not in used, (n, used.get(n), destination)
                used[n] = destination
        mapping.append({'source_start': a, 'source_end': b,
                        'destination': destination, 'action': action,
                        'source_sha256': hashlib.sha256(raw(a,b).encode()).hexdigest(),
                        'detail': detail})

    def add(text):
        parts.append(text.strip())

    def take(a, b, destination, transform=None):
        text = raw(a,b)
        for old, new in refs.items():
            text = text.replace(old, new)
        if transform:
            text = transform(text)
        claim(a,b,destination,'moved_or_reformatted')
        mapping[-1]['output_sha256'] = hashlib.sha256(text.encode()).hexdigest()
        mapping[-1]['output_text'] = text
        add(text)

    def merged(a,b,destination,detail):
        claim(a,b,destination,'consolidated',detail)

    def heading(text, anchor=None):
        if anchor:
            add(f'<a id="{anchor}"></a>')
        add(text)

    def table(a,b,destination,columns,headers):
        rows = [line.strip().strip('|').split('|') for line in lines[a-1:b]]
        result = ['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|']
        result += ['| '+' | '.join(row[i].strip() for i in columns)+' |' for row in rows[2:]]
        add('\n'.join(result))

    # Front matter replaces accumulated change announcements, not data.
    merged(1,16,'도입·2절·3절·4절','Title/navigation replaced; dates, run counts and every headline result retained in experiment/result tables.')
    add('''# 코드 검색·RAPTOR 요약·파일 전체 입력 비교 보고서

**이 보고서의 질문은 “필요한 코드나 요약만 골라 보내면, 파일 하나를 통째로 보낼 때보다 입력을 줄이면서 더 정확하게 답할 수 있는가?”이다.** 현재 색인(A), 파일 간 확장(B), 원문 검색(R0), 함수 요약(RF), 계층 요약(RH), 계층 요약 정리(C), 파일 전체 입력을 실제 LLM 답변으로 비교했다.

기존 네 방식 실험: **2026년 10월 24일** · 큰 파일 RF·RH·C 추가 결과 집계: **2026년 10월 25일** · 각 방식의 정답 수는 **서로 다른 96문제** 기준이다.

큰 파일에서는 **R0가 25/96문제로 가장 많이 맞혔고, A가 한 호출 입력 평균 342.0토큰으로 컨텍스트를 가장 적게 썼다.** C는 RH보다 질문당 총 입력을 18.2% 줄였고 총정답 수는 같았지만, 맞히고 틀린 개별 문제는 달랐다. 관측된 차이와 일반적인 우위는 구분해야 한다.

**읽는 순서:** 결과를 먼저 보려면 [3절](#results) → [4절](#cost) → [6절](#decision)을 읽으면 된다. 방식과 배경부터 이해하려면 1절부터 순서대로 읽는다.

| 본문 | 세부 자료 |
|---|---|
| [1. 일곱 방식의 원리와 실제 색인 예시](#methods) | [부록 A. 상세 성적과 통계](#detail) |
| [2. 실험 조건과 지표를 읽는 법](#design) | [부록 B. 같은 질문의 실제 답변](#cases) |
| [3. 정답률·시간·파일 크기에 따른 결과](#results) | [부록 C. 원자료·검증·재현](#evidence) |
| [4. 토큰·컨텍스트·준비 비용](#cost) | |
| [5. 왜 이런 정답률이 나왔는가](#interpretation) | |
| [6. 목적에 따른 판단과 한계](#decision) | |''')

    heading('## 1. 일곱 방식의 원리와 실제 색인 예시','methods')
    take(18,18,'1절')
    merged(20,20,'1.1','Heading replaced.')
    heading('### 1.1 파싱, 색인, LLM 요약의 차이')
    take(22,22,'1.1')
    take(34,34,'1.1',lambda t:t.replace('따라서 **','**',1))
    # Wide construction table becomes one short vertical table per method.
    merged(24,32,'1.3~1.9','All seven method rows are retained cell-for-cell as per-method two-column tables.')
    construction_rows = {}
    for line in lines[25:32]:
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        construction_rows[cells[0]] = cells[1:]

    def process(label):
        cells=construction_rows[label]
        add('| 단계 | 처리 내용 |\n|---|---|\n' + '\n'.join(
            '| '+key+' | '+value+' |' for key,value in zip(
                ['질문 전 준비','사전 LLM 요약','질문 후 처리'],cells)))

    merged(42,42,'1.2','Heading numbered.')
    heading('### 1.2 모든 방식에 사용할 같은 원본 파일')
    take(44,73,'1.2')
    add('이제 같은 `remaining(9, 1)` 질문에 대해, 각 방식이 **무엇을 저장하고 무엇을 전달하는지** 비교한다.')

    method_parts=[
        (75,77,100,'1.3','A — 현재 색인: 이름과 위치로 필요한 원문을 찾는다','**A — 현재 색인**'),
        (102,104,132,'1.4','B — 파일 간 확장: 다른 파일의 참조까지 따라간다','**B — 파일 간 확장**'),
        (134,136,182,'1.5','R0 — 원문 검색: 원문 조각과 참조 묶음을 검색한다','**R0 — 원문 검색**'),
        (184,186,218,'1.6','RF — 함수 요약: 원문 후보에 LLM 설명을 추가한다','**RF — 함수 요약**'),
        (220,222,258,'1.7','RH — 계층 요약: 함수 설명을 파일·프로젝트로 재요약한다','**RH — 계층 요약**'),
        (260,262,276,'1.8','C — 계층 요약 정리: 같은 자료의 중복과 제목을 줄인다','**C — 계층 요약 정리**'),
    ]
    for h,a,b,number,title,label in method_parts:
        merged(h,h,number,'Heading numbered and method name expanded.')
        heading(f'### {number} {title}')
        process(label)
        if number=='1.5':
            take(36,36,number)
        if number=='1.6':
            add('**RF·RH의 공통 요약 지시와 처리 방식**')
            take(38,40,number,lambda t:t.replace('이러한 준비 과정과 실제 저장 예제를 아래에서 연결해 볼 수 있다.','아래 실제 저장 예제에서 이 과정을 확인할 수 있다.'))
        if number=='1.7':
            take(a,247,number)
            # Long English summaries should read as text, not very tall table cells.
            merged(249,252,number,'Both actual summary bodies retained verbatim, with line wrapping only, as text blocks.')
            for row in lines[250:252]:
                name,body=[v.strip() for v in row.strip().strip('|').split('|')]
                add(f'**{name} — 실제 본문**\n\n```text\n{textwrap.fill(body,88)}\n```')
            take(254,b,number)
        else:
            take(a,b,number)

    heading('### 1.9 파일 전체 입력과 일곱 방식의 전달 범위')
    process('**파일 전체**')
    merged(290,290,'1.9','Heading replaced.')
    take(292,300,'1.9')
    take(302,304,'1.9')
    merged(278,278,'1.10','Heading numbered.')
    heading('### 1.10 RAPTOR의 어떤 아이디어를 적용했나?')
    take(280,288,'1.10')

    heading('## 2. 실험 조건과 지표를 읽는 법','design')
    add('작은 파일의 네 방식 비교, 같은 코드를 확장한 큰 파일의 네 방식 비교, 그 큰 파일에 RF·RH·C를 추가한 비교를 구분한다. **새로 생성한 답변과 이전 실행에서 보존한 답변**을 아래에 명시했다.')
    merged(307,307,'2.1','Heading numbered.')
    heading('### 2.1 작은 파일: A·B·R0·파일 전체')
    take(309,326,'2.1')
    merged(477,477,'2.2','Heading numbered.')
    heading('### 2.2 큰 파일: 원래 기능을 유지하고 보조 함수를 추가')
    take(479,493,'2.2')
    take(551,553,'2.2')
    merged(646,646,'2.3','Heading numbered.')
    heading('### 2.3 같은 큰 파일에 RF·RH·C 추가')
    take(648,666,'2.3')
    heading('### 2.4 정답률·시간·근거·토큰의 뜻')
    take(343,347,'2.4')
    take(682,682,'2.4',lambda t:t.replace('새 세 방식도','RF·RH·C도').replace('이 입력 표','질문당 입력 표'))
    add('본문의 **%p**는 두 정답률을 뺀 차이다. 예를 들어 26.0%와 15.6%의 차이는 10.4%p다. 반복 답변을 별개의 문제로 세지 않으며, 통계 계산과 비교별 불확실성은 [부록 A.4~A.6](#statistics)에 모았다.')

    heading('## 3. 정답률·시간·파일 크기에 따른 결과','results')
    merged(668,668,'3.1','Heading numbered.')
    heading('### 3.1 큰 파일: 일곱 방식의 핵심 결과')
    # Keep every original cell, split accuracy/time from token cost.
    merged(670,678,'3.1·4.1','All rows and values retained; accuracy/time columns in 3.1, evidence/total/saving columns in 4.1.')
    table(670,678,'3.1',[0,1,2,3,4],['방식','정답 / 96','정답률','대표 응답 시간','p95'])
    take(680,680,'3.1')
    take(684,684,'3.1')
    take(714,716,'3.1')
    add('네 방식만의 기존 큰 파일 상세표도 [부록 A.1](#large-detail)에 유지했다. 실제 답변 사례는 [부록 B](#cases)에서 확인할 수 있다.')
    merged(328,328,'3.2','Heading numbered.')
    heading('### 3.2 작은 파일: 네 방식의 실제 결과')
    take(330,341,'3.2')
    take(361,361,'3.2')
    merged(540,540,'3.3','Heading numbered.')
    heading('### 3.3 작은 파일에서 큰 파일로 바뀌면')
    take(542,549,'3.3')
    merged(469,471,'3.3','Chronological headings replaced; explanation retained.')
    take(473,475,'3.3')
    merged(620,622,'3.4','Chronological headings replaced.')
    heading('### 3.4 01번 보고서와 비교할 때: 같은 48문제로 맞춰야 한다')
    take(624,644,'3.4')

    heading('## 4. 토큰·컨텍스트·준비 비용','cost')
    add('**컨텍스트 절약**은 한 번의 요청에서 차지하는 입력을, **처리량 절약**은 질문을 마칠 때까지 여러 호출에 쓴 입력의 합을 본다. 여기에 질문 전에 요약을 만드는 비용을 따로 더해야 한다.')
    heading('### 4.1 큰 파일: 질문당 입력과 한 호출의 점유량')
    table(670,678,'4.1',[0,5,6,7],['방식','평균 근거 토큰','평균 총 입력 토큰','파일 전체 대비 총 입력 절감'])
    take(700,700,'4.1')
    merged(686,686,'4.1','Heading consolidated.')
    take(688,698,'4.1')
    # Existing four-arm call breakdown is identical to this expanded table.
    merged(529,536,'4.1','Each selector/answer/total value appears in the two seven-method tables above; no measurement dropped.')
    take(538,538,'4.1')
    merged(363,363,'4.2','Heading numbered.')
    heading('### 4.2 작은 파일: A는 한 호출을 줄여도 누적 입력은 늘 수 있다')
    take(365,376,'4.2')
    heading('### 4.3 파일 전체 대비 증감: 작은 파일과 큰 파일')
    merged(349,349,'4.3','Heading numbered.')
    add('**작은 파일 기준**')
    take(351,359,'4.3')
    merged(517,517,'4.3','Heading consolidated.')
    add('**큰 파일 기준**')
    take(519,527,'4.3')
    merged(421,421,'4.4','Heading numbered.')
    heading('### 4.4 시간은 어느 단계에 들었나?')
    add('**작은 파일 — 요청당 평균**')
    take(423,429,'4.4')
    add('**큰 파일 — 요청당 평균**')
    take(579,585,'4.4')
    merged(744,744,'4.5','Heading numbered.')
    heading('### 4.5 사전 요약 생성 비용과 재사용')
    take(746,763,'4.5')
    heading('### 4.6 C의 입력 정리로 줄어든 비용')
    take(718,720,'4.6')

    merged(795,795,'5절','Heading numbered.')
    heading('## 5. 왜 이런 정답률이 나왔는가','interpretation')
    take(797,797,'5절')
    heading('### 5.1 방식별 확인 사실과 가능한 설명')
    for n in [799,801,803,805,807,809,811]:
        # Preserve wording; separate evidence from causal hypotheses visually.
        def format_interpretation(t):
            title,rest=t.split(' 확인:',1)
            fact,hypothesis=rest.split(' **추측:**',1)
            return title+'\n\n**확인:**'+fact+'\n\n**추측:**'+hypothesis
        take(n,n,'5.1',format_interpretation)
    heading('### 5.2 실제로 선택된 원문과 요약')
    take(722,731,'5.2')
    heading('### 5.3 검색 가중치에서 발견한 단서와 반례')
    take(813,815,'5.3')
    take(819,819,'5.3')

    heading('## 6. 목적에 따른 판단과 한계','decision')
    merged(461,467,'6.1~6.2','Small-file conclusions consolidated with large-file conclusions; figures preserved in 3.2 and 4.2~4.3.')
    merged(598,604,'6.1~6.2','Large-file conclusions consolidated with small-file conclusions; all limits retained below.')
    heading('### 6.1 무엇을 우선하느냐에 따라 판단이 달라진다')
    add('''| 우선하는 목적 | 이번 실험에서 확인한 판단 |
|---|---|
| 한 번에 쓰는 컨텍스트 최소화 | **A**의 한 호출 입력이 가장 작았다. 큰 파일에서는 평균 342.0토큰으로 파일 전체 4265.8토큰보다 92.0% 적었다. 작은 파일에서는 코드 자료 42.4%, 가장 큰 호출 입력 20.2%를 줄였지만 누적 입력은 29.2% 늘었다. |
| 이번 문제에서 더 많이 맞히기 | **R0**가 작은 파일 27.1%, 큰 파일 26.0%로 관측 정답률이 가장 높았다. 하지만 이 점수로 충분한 답변 신뢰성을 확보했다고 보기는 어렵다. |
| RH와 같은 자료를 더 짧게 전달하기 | **C**는 고유 본문을 보존하면서 RH보다 총 입력을 18.2% 줄였다. 총정답 수는 같아도 2문제 개선·2문제 악화가 있어 개별 답변까지 같지는 않았다. |

큰 파일에서는 A·B·R0 모두 파일 전체보다 총 입력을 줄였다. 작은 파일에서는 출발 함수를 고르는 A·B의 추가 호출 비용이 상대적으로 크게 작용했다. **적은 토큰, 넓은 원문 범위, 많은 검색 후보 중 어느 하나만으로 정답이 보장되지는 않는다.** 실제 정답률·입력 범위·호출 수·시간·불확실성을 함께 판단해야 한다.''')
    heading('### 6.2 이 결과로 말할 수 있는 범위')
    add('''평가는 **영어 질문, 구조가 비슷한 합성 Python 프로젝트 6개, 한 모델·한 장비**에 한정된다. 파일 전체 방식에는 대상 파일 경로를 미리 알려줬고, 방식마다 실제로 전달한 정보의 범위도 다르다. 전체 구현의 비교이며, 각 요소의 효과를 분리한 비교는 아니다.

큰 파일은 원래의 짧은 질문 대상 함수를 유지하고 관계없는 보조 함수를 추가해 만들었다. 파일 크기와 함께 검색 후보 수와 줄 위치도 바뀌었다. 따라서 **관련 함수 자체가 수천 줄인 경우, 복잡한 실제 저장소와 import, 다른 언어·한국어 질문·보안 취약점 탐지**에서 같은 절감률이나 정확도, 우위를 보장하지 않는다.

프로젝트 수가 적어 통계는 탐색적이다. 시간 비교에도 세션·장비 부하·열 상태의 한계가 있다. 관측값은 유용한 단서지만, 보정 검정에서 차이를 확정하지 못한 결과를 성능 동등성의 증거로 읽어서는 안 된다.''')
    heading('### 6.3 원인을 확인하기 위한 후속 실험')
    take(817,817,'6.3')

    heading('## 부록 A. 상세 성적과 통계','detail')
    merged(495,495,'부록 A.1','Detailed original four-method table retained in appendix.')
    heading('### A.1 큰 파일 네 방식의 상세 측정값','large-detail')
    add('3.1절의 일곱 방식 비교에 합쳐진 **기존 A·B·R0·파일 전체 실행의 상세표**다. 별도의 추가 실험을 뜻하지 않는다.')
    take(497,515,'부록 A.1')
    merged(392,392,'부록 A.2','Heading numbered.')
    heading('### A.2 작은 파일: 질문 종류·프로젝트·문제 집합별 정답')
    take(394,419,'부록 A.2')
    merged(555,555,'부록 A.3','Accuracy categories and statistical comparison separated.')
    heading('### A.3 큰 파일: 질문 종류별 정답')
    add('**A·B·R0·파일 전체** — 각 칸은 해당 종류에서 맞힌 문제 수다.')
    take(557,564,'부록 A.3')
    merged(566,566,'부록 A.3~A.5','Category explanation retained above; transition replaced.')
    add('**R0·RF·RH·C**')
    take(733,742,'부록 A.3')
    merged(378,378,'부록 A.4','Heading numbered.')
    heading('### A.4 작은 파일: 파일 전체와의 통계 비교','statistics')
    take(380,390,'부록 A.4')
    heading('### A.5 큰 파일: 네 방식 사이의 통계 비교')
    take(568,577,'부록 A.5')
    merged(702,702,'부록 A.6','Heading numbered.')
    heading('### A.6 큰 파일: 함수 요약·계층 요약·입력 정리의 통계 비교')
    take(704,712,'부록 A.6')

    heading('## 부록 B. 같은 질문의 실제 답변','cases')
    merged(431,431,'부록 B','Heading numbered.')
    take(433,433,'부록 B',lambda t:t.replace('이전 보고서의 두 사례를 유지해 새 파일 전체 결과를 나란히 붙였다.','재고·권한의 기존 두 사례와 RF·RH·C 비교 사례를 모았다.'))
    merged(435,435,'부록 B.1','Heading numbered.')
    heading('### B.1 작은 파일의 재고 계산')
    take(437,446,'부록 B.1')
    merged(587,587,'부록 B.2','Heading numbered.')
    heading('### B.2 같은 재고 문제를 큰 파일에서 물으면')
    take(589,596,'부록 B.2')
    merged(448,448,'부록 B.3','Heading numbered.')
    heading('### B.3 작은 파일의 권한 계산')
    take(450,459,'부록 B.3')
    merged(765,765,'부록 B.4','Heading numbered.')
    heading('### B.4 큰 파일: 요약 추가·입력 정리 후 답변이 달라진 사례')
    take(767,793,'부록 B.4')

    heading('## 부록 C. 원자료·검증·재현','evidence')
    add('아래 링크는 기존 실행 기록과 검증 자료다. **이번 편집은 문서의 배치·제목·표 구성을 정리한 것이며, 새 LLM 실험이나 정답률 변경은 없다.**')
    merged(835,835,'부록 C.1','Heading numbered.')
    heading('### C.1 작은 파일 실험')
    take(837,847,'부록 C.1')
    merged(606,606,'부록 C.2','Heading numbered.')
    heading('### C.2 큰 파일의 A·B·R0·파일 전체 실험')
    take(608,618,'부록 C.2')
    merged(823,823,'부록 C.3','Heading numbered.')
    heading('### C.3 큰 파일의 RF·RH·C 추가 실험')
    take(825,833,'부록 C.3')
    heading('### C.4 문서 재구성 전후 확인')
    base=f'evidence/raptor_large_20261024/{REVISION}'
    add(f'[정리 전 보고서]({base}/03_현재색인_A와_파일간확장_B_재실험_비교보고서.md) · [내용 이동·통합 대조표]({base}/content_map.json) · [누락·수치·링크 확인]({base}/verification.json)')

    missing=[i for i,l in enumerate(lines,1) if l.strip() and i not in used]
    assert not missing, ('Unaccounted source lines',missing)
    output='\n\n'.join(parts)+'\n'
    return output, {'source_sha256':INPUT_SHA256,
                    'output_sha256':hashlib.sha256(output.encode()).hexdigest(),
                    'source_nonempty_lines':len(used),
                    'unaccounted_source_lines':missing,
                    'entries':mapping}


if __name__=='__main__':
    import experiment_raptor_large as exp
    rev=exp.OUT/REVISION
    before=(rev/exp.REPORT.name).read_text()
    text,mapping=reorganize(before)
    # Standalone mode produces a reviewable draft, not an untracked overwrite.
    (rev/'draft.md').write_text(text)
    (rev/'content_map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'characters':len(text),'mapped_nonempty_lines':mapping['source_nonempty_lines'],
                      'unaccounted':mapping['unaccounted_source_lines']},ensure_ascii=False))
