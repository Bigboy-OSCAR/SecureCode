"""Write the requested Korean Markdown report only from completed, verified data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import experiment_ab as exp


CATEGORIES = {
    "single_function": "한 함수의 계산", "cross_file": "여러 파일을 잇는 계산",
    "boundary": "경계 조건", "semantic": "자연어로 설명한 동작",
    "change_impact": "설정 변경의 영향", "architecture": "함수 호출 구조",
}
PROJECTS = {"eval_pricing": "가격", "eval_authorization": "권한", "eval_routing": "라우팅",
            "eval_inventory": "재고", "eval_cache": "캐시", "eval_schedules": "일정"}
EXAMPLE_EXPLANATIONS = {
    "eval_inventory__v2_partial_depletes_available": (
        "질문의 뜻은 ‘재고 9개 중 1개가 이미 잡혀 있을 때 8개를 요청하고 부분 예약을 허용하면, "
        "예약 뒤 판매 가능한 수량은 얼마인가?’이다. 안전재고 3개를 빼면 처음 판매 가능량은 5개다. "
        "5개만 예약하므로 남는 판매 가능량은 **0개**다. A에는 같은 파일의 예약 코드만 전달됐고, "
        "B에는 다른 파일의 판매 가능량 계산과 안전재고 값도 전달됐다. 이 차이가 관찰되지만, "
        "탐색 범위와 표시 형식 중 어느 변화가 정답에 얼마나 기여했는지는 분리하지 않았다."),
    "eval_authorization__v2_duplicate_write_permission": (
        "질문은 ‘공백·대문자가 섞인 쓰기 권한과 같은 권한이 중복되어 있을 때, 자신의 문서를 편집할 수 있는가?’이다. "
        "코드는 권한 문자열의 공백을 제거하고 소문자로 바꾸며 중복을 제거한다. 세션 경과 시간도 "
        "1,799초로 제한 3,600초보다 짧으므로 정답은 **true**다. B는 더 많은 원문을 받았지만 false라고 답했다. "
        "B가 가져온 권한 검사 함수 안에는 아직 추가 호출이 남아 있고, 두 차례 확장 제한 때문에 "
        "권한 정규화 함수 등의 정의는 포함되지 않았다. 이는 더 넓게 찾는 것과 필요한 근거를 완전히 모으는 것이 "
        "다름을 보여 준다. 이 누락이 오답의 직접 원인인지는 별도 실험으로 확인하지 않았다."),
}


def pct(x):
    return f"{100*x:.1f}%"


def ncorrect(m):
    value = m["accuracy"] * m["unique_questions"]
    return str(round(value)) if abs(value - round(value)) < 1e-9 else f"{value:.2f}"


def build(out):
    summary = exp.read(out / "summary.json")
    verification = exp.read(out / "verification.json")
    assert summary["status"] == "COMPLETE" and verification["status"] == "PASS"
    assert exp.original.sha(out / "summary.json") == verification["source_hashes"]["summary.json"]
    population = summary["by_population"]["all96"]
    a, b = population["metrics"]["A"], population["metrics"]["B"]
    c, pairs = population["comparison_B_minus_A"], population["paired"]
    slower = -c["latency_reduction_pct"]
    delta_count = (b["accuracy"] - a["accuracy"]) * 96
    stable = a["different_output_questions"] == b["different_output_questions"] == 0
    certainty = ("정답률 차이의 추정 구간은 0을 포함한다. 이 표본만으로 B가 더 정확하다고 확정할 수 없다."
                 if c["ci95_pp"][0] <= 0 <= c["ci95_pp"][1] else
                 "정답률 차이의 재표집 구간은 0을 포함하지 않았다. 다만 프로젝트가 6개뿐이므로 아래의 프로젝트 단위 검정과 일반화 한계를 함께 봐야 한다.")
    overview = (f"전체 96문제에서 현재 색인(A)은 **{ncorrect(a)}문제**, 파일 간 확장(B)은 **{ncorrect(b)}문제**를 맞혔다. "
                f"B의 정답률은 {abs(c['delta_pp']):.1f}%p {'높았지만' if c['delta_pp'] > 0 else '낮았고'}, 대표 응답 시간은 "
                f"**{a['mean_query_seconds']:.2f}초 → {b['mean_query_seconds']:.2f}초**로 "
                f"{abs(slower):.1f}% {'늘었다' if slower >= 0 else '줄었다'}.")
    count_note = ("각 문제·방식의 출력은 세 번 모두 같았다. 따라서 정답 수는 반복을 빼고 서로 다른 96문제를 기준으로 표시한다."
                  if stable else "반복에 따라 답이 바뀐 문제가 있어 정답률은 문제별 3회 성공률의 평균이다. 정답 수는 이 비율을 96문제로 환산한 값이다.")
    metric_rows = [
        ("정답 수 / 96문제", ncorrect(a), ncorrect(b)),
        ("정답률 — 높을수록 좋음", pct(a["accuracy"]), pct(b["accuracy"])),
        ("대표 응답 시간 — 짧을수록 좋음", f"{a['mean_query_seconds']:.2f}초", f"{b['mean_query_seconds']:.2f}초"),
        ("느린 요청의 시간: p95", f"{a['request_p95_seconds']:.2f}초", f"{b['request_p95_seconds']:.2f}초"),
        ("전달한 코드 길이", f"{a['mean_context_tokens']:.1f}토큰", f"{b['mean_context_tokens']:.1f}토큰"),
        ("전체 입력량: 함수 선택 + 답변", f"{a['mean_input_tokens']:.1f}토큰", f"{b['mean_input_tokens']:.1f}토큰"),
        ("지정한 원문 근거의 평균 포함률", pct(a["raw_evidence_recall"]), pct(b["raw_evidence_recall"])),
        ("지정한 원문 근거를 모두 포함한 비율", pct(a["all_raw_evidence"]), pct(b["all_raw_evidence"])),
        ("출발 함수와 다른 파일의 원문을 포함한 질문 비율", pct(a["cross_file_query_fraction"]), pct(b["cross_file_query_fraction"])),
    ]
    table = "\n".join(f"| {label} | {av} | {bv} |" for label, av, bv in metric_rows)
    subset_rows = []
    for key, label in [("original48", "기존 문제 48개"), ("additional48", "추가 문제 48개")]:
        x = summary["by_population"][key]
        aa, bb = x["metrics"]["A"], x["metrics"]["B"]
        subset_rows.append(f"| {label} | {ncorrect(aa)} / 48 | {ncorrect(bb)} / 48 | {aa['mean_query_seconds']:.2f}초 | {bb['mean_query_seconds']:.2f}초 |")
    category_rows = []
    for category, label in CATEGORIES.items():
        aa, bb = a["by_category"][category], b["by_category"][category]
        category_rows.append(f"| {label} | {aa['unique_questions']} | {aa['question_equivalent_correct']:g} | {bb['question_equivalent_correct']:g} | {bb['question_equivalent_correct']-aa['question_equivalent_correct']:+g} |")
    top_category = max(CATEGORIES, key=lambda k: b["by_category"][k]["question_equivalent_correct"]-a["by_category"][k]["question_equivalent_correct"])
    top_delta = b["by_category"][top_category]["question_equivalent_correct"]-a["by_category"][top_category]["question_equivalent_correct"]
    cross_a, cross_b = a["by_category"]["cross_file"], b["by_category"]["cross_file"]
    category_observation = (f"정답 수 증가가 가장 큰 종류는 **{CATEGORIES[top_category]}**({top_delta:+g}문제)였다. "
                            f"반면 여러 파일을 잇는 계산 문제는 24개 중 A **{cross_a['question_equivalent_correct']:g}개**, "
                            f"B **{cross_b['question_equivalent_correct']:g}개**가 정답이었다. "
                            "코드의 연결을 찾아 나열하는 능력과, 여러 규칙을 적용해 정확한 값을 계산하는 능력을 구분해서 봐야 한다.")
    project_rows = []
    for project, label in PROJECTS.items():
        aa, bb = a["by_project"][project], b["by_project"][project]
        project_rows.append(f"| {label} | {aa['question_equivalent_correct']:g} / 16 | {bb['question_equivalent_correct']:g} / 16 | {bb['question_equivalent_correct']-aa['question_equivalent_correct']:+g} |")
    stage_rows = []
    for key, label in [("mean_select_seconds", "함수 후보 구성·AI의 출발 함수 선택"),
                       ("mean_expansion_seconds", "관련 코드 수집"), ("mean_packing_seconds", "길이 확인·전달 자료 구성"),
                       ("mean_answer_seconds", "AI의 최종 답변 처리")]:
        display = lambda value: "0.001초 미만" if value < .001 else f"{value:.3f}초"
        stage_rows.append(f"| {label} | {display(a[key])} | {display(b[key])} |")
    examples = []
    for kind, predicate in [("B가 맞히고 A가 틀린 사례", lambda q: q["B"]["score"] == 1 and q["A"]["score"] == 0),
                             ("A가 맞히고 B가 틀린 사례", lambda q: q["A"]["score"] == 1 and q["B"]["score"] == 0)]:
        choices = sorted((q for q in pairs["questions"] if predicate(q)),
                         key=lambda q: (q["category"] != "cross_file", q["task_id"]))
        if choices:
            q = choices[0]
            show = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True).replace("|", "\\|")
            examples.append(f"### {kind}\n\n질문: `{q['question']}`\n\n"
                            f"| 항목 | 현재 색인(A) | 파일 간 확장(B) |\n|---|---|---|\n"
                            f"| 실제 답변 | `{show(q['A']['answer'])}` | `{show(q['B']['answer'])}` |\n"
                            f"| 전달한 원문 파일 | {', '.join(q['A']['source_files'])} | {', '.join(q['B']['source_files'])} |\n"
                            f"| 전달한 코드 길이 | {q['A']['context_tokens']:g}토큰 | {q['B']['context_tokens']:g}토큰 |\n\n"
                            f"정답: `{show(q['expected'])}`. 기록 식별자: `{q['task_id']}`.\n\n"
                            f"{EXAMPLE_EXPLANATIONS.get(q['task_id'], '같은 출발점에서 수집한 원문과 최종 답을 비교한 사례다. 정확한 실패 원인을 이 사례 하나로 단정할 수는 없다.')}\n")
    quality_delta = f"{c['delta_pp']:+.1f}%p"
    quality_ci = f"{c['ci95_pp'][0]:+.1f} ~ {c['ci95_pp'][1]:+.1f}%p"
    time_ci = f"{c['latency_ci95_seconds'][0]:+.2f} ~ {c['latency_ci95_seconds'][1]:+.2f}초"
    recommendation = (f"관측 정답 수는 B가 많았지만 응답 시간이 늘었다. 증가 폭이 가장 큰 질문 종류는 {CATEGORIES[top_category]}였다. "
                      "용도별로 구분해 검토할 근거는 되지만, 현재 방식을 전부 교체할 만큼 일반적인 우월성이 입증된 것은 아니다."
                      if delta_count > 0 else "이번 실행에서 B의 전체 정답 수 이득은 관측되지 않았다. 파일 간 확장만으로 더 나은 답변을 보장할 수 없으므로, 현재 방식의 전면 교체를 뒷받침하지 않는다.")
    content = f'''# 현재 색인(A)과 파일 간 확장(B): 재실험 비교 보고서

**질문: 같은 함수를 출발점으로 삼을 때, 다른 파일의 관련 코드까지 가져오면 더 잘 답하는가?**  
실험일: 2026년 10월 24일 · 형식: Markdown · 두 방식 모두 원문만 사용하며 RAPTOR 요약은 사용하지 않음

{overview}

{recommendation}

## 1. A와 B는 각각 무엇인가?

이 프로젝트에서 `symbol_index`는 함수 등의 이름과 코드 위치를 정리한 **코드 주소록**이다. AI가 코드에 대한 질문을 받으면, 주소록을 이용해 출발 함수를 고른 다음 관련 원문을 읽고 답한다. 함수는 계산이나 특정 작업을 수행하는 코드 단위이고, 원문은 프로그램에 실제 작성된 코드다.

| 항목 | 현재 색인 방식(A) | 파일 간 확장 방식(B) |
|---|---|---|
| 출발 함수 선택 | 질문과 관련된 색인 후보 최대 24개 중 AI가 선택 | 같은 후보 구성·선택 규칙 사용 |
| 추가 원문 수집 | 선택한 함수와 **같은 파일**의 관련 함수·상수 | 참조 관계를 따라 **다른 파일**의 함수·상수까지 수집 |
| 관계를 찾는 방법 | 선택한 파일의 코드 구조에서 이름·호출 참조 확인 | 프로젝트를 미리 분석해 만든 참조 관계와 import 연결 확인 |
| 확장 제한 | 두 차례 확장, 함수·클래스 등 심벌 최대 8개 | 두 차례 확장, 함수 최대 8개; 참조한 상수도 추가 |
| 최종 답변 자료 | 관련 원문 | 관련 원문 |
| 요약 생성·사용 | 없음 | 없음 |

**A도 함수 하나만 읽는 방식은 아니다.** 같은 파일의 관련 함수와 상수를 함께 가져온다. B의 핵심 차이는 관련 코드를 찾을 때 파일 경계를 넘는 것이다.

```mermaid
flowchart TD
    question["사용자의 코드 질문"] --> candidates["색인에서 후보 최대 24개 구성"]
    candidates --> select["같은 규칙으로 출발 함수 선택: 각 방식별 AI 호출"]
    select --> local["현재 색인 A: 같은 파일의 관련 원문 수집"]
    select --> cross["파일 간 확장 B: 다른 파일의 참조까지 추적"]
    local --> cap["최대 1,024토큰 안에 원문 구성"]
    cross --> cap
    cap --> answer["같은 답변 모델이 읽고 답변"]
    answer --> check["정답·시간·전달 자료 양 측정"]
```

### B가 파일을 따라가는 과정

실험의 재고 프로젝트에서 `service.py`의 잔여 수량 함수 `remaining_after()`는 `rules.py`의 판매 가능량 계산 함수 `sellable()`을 부른다. `sellable()`은 `policy.py`의 안전재고 값 `SAFETY_STOCK`을 사용한다.

1. 두 방식 모두 색인에서 `remaining_after()`를 출발점으로 고른다.
2. A는 같은 파일의 예약 함수 `reserve()`도 가져온다. 다른 파일에 있는 `sellable()`의 정의는 따라가지 않는다.
3. B는 import문과 이름 참조로 연결을 확인한다. 첫 확장에서 `sellable()`을, 다음 확장에서 그 함수가 사용하는 안전재고 값을 가져올 수 있다.
4. 각 방식이 모은 코드를 길이 제한 안에 담아 같은 AI에게 전달한다. 파일 전체를 가져오는 것이 아니라 선택된 함수·상수의 원문을 가져온다.

관계 추적은 AI가 매번 다음 파일을 결정하는 과정이 아니라, 코드 분석으로 만든 연결을 프로그램이 따라가는 과정이다. 현재 B 구현은 특히 `from ... import ...` 형태로 정적으로 확인되는 연결을 사용하며, 모든 Python import 형태나 동적 호출을 해결하는 범용 분석기는 아니다.

질문에 이름이 직접 나온 같은 파일의 함수도 추가 대상으로 삼는다. 길이를 초과하는 코드 조각은 통째로 건너뛰며, 함수 수 제한이 같아도 실제 전달량은 같지 않을 수 있다.

## 2. 이번에는 무엇을 새로 실행했나?

이전 결과를 다시 계산하는 데 그치지 않고 **A·B 각각 96문제 × 3회, 총 576개 답변을 새로 생성**했다. 기존 실험의 48문제와 후속 실험의 추가 48문제를 고정하여 합쳤다. 두 집합은 따로도 제시한다. 모두 이미 알려진 문제이며 새로운 독립 검증 자료는 아니다.

| 설계 항목 | 실제 조건 |
|---|---|
| 평가 자료 | 6개 소규모 합성 Python 프로젝트, 프로젝트당 파일 5개·질문 16개 |
| 문제 구성 | 한 함수 계산 12, 여러 파일 계산 24, 경계 조건 12, 자연어 동작 질문 24, 변경 영향 12, 호출 구조 12 |
| 모델·장비 | Qwen2.5-Coder-7B-Instruct Q5_K_M · Apple M3 Pro · 메모리 36 GiB |
| 공통 제한 | 근거 1,024토큰, 답변 최대 128토큰, 함수 선택 최대 96토큰, 모델 전체 문맥 8,192토큰 |
| 반복 조건 | temperature 0, seed 1, 질문·방식별 3회 |
| 실행 순서 | 프로젝트별·반복별로 A 먼저 8쌍, B 먼저 8쌍. 질문 쌍의 순서는 무작위 배치 |
| 함수 선택 | A와 B 모두 매번 별도로 실행. 이전처럼 선택 결과나 실행 비용을 공유하지 않음 |
| 캐시 | 모델의 이전 입력 계산 재사용을 끄고, 토큰 수 계산 캐시는 질문마다 비움 |
| 정답 검증 | 96문제의 기준 답을 코드 실행 또는 호출 관계 분석으로 재확인 |
| 정답 채점 | JSON이라는 정해진 데이터 형식의 값·자료형·요구된 목록 순서까지 일치해야 정답 |

두 방식은 같은 선택 규칙을 썼지만, 실제 선택도 같았는지 별도로 확인했다. **{pairs['query_pairs']}개 실행 쌍 중 {pairs['same_selector_pairs']}쌍({pct(pairs['selector_agreement'])})에서 출발 함수가 같았다.**

{count_note} 개발용 8문제 × 두 방식의 16답변은 실행 점검용이며 본 점수에 포함하지 않았다.

### 비교가 의미하는 범위

이번 A와 B는 이전에 설명한 구현을 그대로 재실행했다. B는 파일 간 탐색뿐 아니라 import문 포함과 원문 표시·정렬 방식도 A와 다르다. 따라서 이 실험은 **두 구현 전체의 비교**다. 점수 차이 전부를 파일 간 탐색 하나의 효과로 단정할 수는 없다. 답변 모델이나 요약 기능의 효과를 비교한 실험도 아니다.

## 3. 정답·시간·전달 자료의 정량 비교

| 지표 | 현재 색인(A) | 파일 간 확장(B) |
|---|---:|---:|
{table}

**대표 응답 시간**은 문제마다 3회 시간의 중앙값을 구한 다음, 96문제에 걸쳐 평균한 값이다. 검색 시작부터 답변 완료까지 실제 시간을 측정했다. 함수 선택·코드 수집·토큰 계산·답변과 작은 호출 로그 기록 비용을 포함한다. 모델 시작과 사전 색인·참조 관계 준비, 채점은 제외한다.

**p95**는 해당 방식의 288개 요청 중 95%가 끝나는 시간이다. 평균과 달리 느린 요청의 경험을 보여 준다. **토큰**은 AI가 글을 처리하는 작은 단위로, 전달량을 비교하기 위한 수치다.

**근거 포함률**은 문제별로 미리 지정한 코드 목록 중 전달된 원문의 비율이다. 지정 목록이 반드시 필요한 최소 코드와 같지는 않으며, 많이 포함했다고 답을 이해하거나 맞힌 것은 아니다.

B는 지정 근거의 평균 포함률을 **{pct(a['raw_evidence_recall'])} → {pct(b['raw_evidence_recall'])}**로 높였다. 전달한 코드 길이는 약 **{b['mean_context_tokens']/a['mean_context_tokens']:.1f}배**였다. 즉, 더 많은 관련 원문을 모으는 효과는 관측됐지만 그 증가가 같은 크기의 정답률 상승으로 이어지지는 않았다.

### 얼마나 더 맞혔고, 차이는 얼마나 확실한가?

| 비교 | 이번 관측값 | 탐색적 95% 추정 구간 |
|---|---:|---:|
| B − A 정답률 | {quality_delta} | {quality_ci} |
| B − A 응답 시간 | {c['latency_delta_seconds']:+.2f}초 | {time_ci} |

정답률의 `%p`는 두 퍼센트 값의 단순 차이다. B만 더 잘 맞힌 문제는 **{c['win']}개**, A만 더 잘 맞힌 문제는 **{c['loss']}개**, 정오 성적이 같은 문제는 **{c['tie']}개**였다. 전체 정답 수 차이는 **{delta_count:+g}문제**다.

{certainty} 프로젝트별 차이의 방향을 뒤집어 보는 보조 검정의 p값은 **{c['unadjusted_project_signflip_p']:.3f}**다. {'참고 기준 0.05보다 커, 이 검정에서도 정확도 차이가 있다고 확정하지 못했다.' if c['unadjusted_project_signflip_p'] >= .05 else '참고 기준 0.05보다 작았지만, 소수 프로젝트에 대한 탐색적 결과다.'} 이는 두 방식의 성능이 같다는 증명도 아니다.

추정 구간은 6개 프로젝트를 묶음으로 다시 뽑는 46,656가지 조합으로 계산했다. 576개 답변을 독립된 576문제로 계산하지 않았다. 프로젝트들이 공통 구조를 쓰고 장비 실행 세션도 하나이므로, 이 구간은 탐색적이다.

### 두 문제 집합에서도 같은 경향인가?

| 문제 집합 | A 정답 | B 정답 | A 시간 | B 시간 |
|---|---:|---:|---:|---:|
{chr(10).join(subset_rows)}

이 표의 모든 값은 이번 재실행에서 측정했다. 과거 실행 시간과 현재 시간을 빼서 개선 효과를 계산하지 않았다. 두 문제 집합은 같은 6개 프로젝트를 공유하므로 서로 독립된 프로젝트 검증이 아니다.

## 4. 어떤 질문에서 차이가 났나?

| 질문 종류 | 문제 수 | A 정답 | B 정답 | B − A |
|---|---:|---:|---:|---:|
{chr(10).join(category_rows)}

{category_observation}

| 프로젝트 주제 | A 정답 | B 정답 | B − A |
|---|---:|---:|---:|
{chr(10).join(project_rows)}

질문 종류와 프로젝트별 수치는 차이가 어디에 모였는지 보는 보조 분석이다. 각 칸의 문제가 적으므로 종류별 우열을 확정하는 데 사용하지 않는다.

## 5. 추가 시간은 어디에서 발생했나?

| 처리 단계 | A 평균 | B 평균 |
|---|---:|---:|
{chr(10).join(stage_rows)}

이 표는 모든 요청의 단계별 평균이다. 전체 요청 평균은 A **{a['request_mean_seconds']:.2f}초**, B **{b['request_mean_seconds']:.2f}초**다. 문제별 중앙값을 먼저 구한 앞의 대표 응답 시간과 집계 방식이 다르다. 코드를 찾는 시간과 AI가 더 긴 자료를 읽고 답하는 시간을 구분해야 속도 비용을 제대로 해석할 수 있다.

서버가 기록한 입력 읽기 시간은 함수 선택·답변 호출을 합쳐 A **{a['mean_prefill_seconds']:.2f}초**, B **{b['mean_prefill_seconds']:.2f}초**였다. 답을 생성하는 시간은 각각 **{a['mean_decode_seconds']:.2f}초**, **{b['mean_decode_seconds']:.2f}초**였다. 이 값들은 위 처리 단계 안에 포함된 비용이므로 표의 시간에 다시 더하지 않는다.

원문 조각이 길이 제한 때문에 제외된 요청은 A **{a['queries_with_rejected_fragments']} / 288**, B **{b['queries_with_rejected_fragments']} / 288**이었다. 두 방식 모두 같은 상한을 받았지만 상한을 모두 채우도록 강제하지 않았다. 사전 참조 관계 구성 시간은 따로 기록했고, 한 번의 준비 관측이므로 정밀한 초기화 속도 비교로 해석하지 않았다.

## 6. 실제 답변 사례

아래는 두 방향의 차이를 모두 보여 주기 위해, 각 방식이 유리한 사례를 하나씩 고른 것이다. 우선 여러 파일 계산 문제에서 고르고, 해당하는 문제가 없으면 다른 종류에서 골랐다. 한 사례가 전체 성능을 대표하지는 않는다.

{chr(10).join(examples)}
목록 원소는 같고 순서만 틀린 답을 허용하는 보조 채점을 하면 A **{pct(a['order_tolerant_accuracy'])}**, B **{pct(b['order_tolerant_accuracy'])}**다. 주 결과의 엄격한 채점을 대체하지 않는다. 반환 형식의 실패와 내용 자체의 실패가 점수에 함께 포함된다는 점을 확인하기 위한 진단이다.

## 7. 판단과 한계

{recommendation}

전체 정답률 자체도 A **{pct(a['accuracy'])}**, B **{pct(b['accuracy'])}**였다. 어느 쪽의 상대 점수가 높든, 이 수치를 충분히 신뢰할 수 있는 코드 질의응답 성능으로 해석해서는 안 된다.

가장 중요한 한계는 자료의 규모와 대표성이다. 영어 질문, 구조가 비슷한 합성 Python 프로젝트 6개, 한 모델·한 장비에서 얻은 결과다. 이미 본 질문을 다시 실행했으므로, 새 실제 저장소·한국어 질문·복잡한 import나 동적 호출·실제 코드 수정과 보안 탐지에 대한 성능은 입증하지 않는다.

실사용 검토에서는 응답 시간 요구와 질문 종류를 함께 봐야 한다. 후속 평가로는 같은 원문 표시 형식을 유지한 채 파일 간 탐색만 바꾸는 비교, 그리고 독립된 실제 저장소에서의 평가가 필요하다. 이번 보고서는 아직 실행하지 않은 평가의 효과를 결과에 포함하지 않았다.

## 확인 자료와 재현

기록의 완전성, 독립적인 정답 재채점, 요청 시간·캐시, 근거 재구성, 별도 토큰 계산, 주요 통계의 별도 계산을 점검했다. **{verification['count']}개 점검을 통과했다.** 이는 로컬 기록의 일관성 확인이며 외부 인증이나 일반적 우월성의 증명은 아니다.

| 확인할 내용 | 파일 |
|---|---|
| 설정·고정한 입력과 실행 규칙 | [실험 계획](evidence/ab_20261024/protocol.json) |
| 새로 측정한 정답·시간·종류별 점수 | [집계 결과](evidence/ab_20261024/summary.json) |
| 질문별 원문·답변·측정 시간 | [576개 실행 기록](evidence/ab_20261024/results.jsonl) |
| 코드 실행과 호출 관계로 확인한 정답 | [정답 재확인](evidence/ab_20261024/gold_recheck.json) |
| 기록·통계·토큰 검증 결과 | [검증 기록](evidence/ab_20261024/verification.json) |
| 실행 환경과 모델 식별 정보 | [환경 기록](evidence/ab_20261024/environment.json) |
| 실험 당시 A·B의 원문 수집 구현 | [A의 같은 파일 확장](evidence/ab_20261024/source_snapshot/indexer.py) · [B의 파일 간 확장](evidence/ab_20261024/source_snapshot/experiment.py) |
| 새 디렉터리에서 다시 실행하는 방법 | [재현 안내](evidence/ab_20261024/reproduce.txt) |

기존 보고서와 원자료는 유지하고, 이번 재실험 자료는 별도 폴더에 저장했다.
'''
    dest = out.parents[1] / "03_현재색인_A와_파일간확장_B_재실험_비교보고서.md"
    dest.write_text(content)
    exp.original.dump(out / "report_manifest.json", {"created_at_utc": exp.audited.now(),
                      "report_path": str(dest), "report_sha256": exp.original.sha(dest),
                      "summary_sha256": exp.original.sha(out / "summary.json"),
                      "verification_sha256": exp.original.sha(out / "verification.json"),
                      "report_builder_sha256": exp.original.sha(__file__)})
    print(str(dest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    build(parser.parse_args().out)
