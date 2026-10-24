"""Update the requested existing Markdown report with verified A/B/R0 evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import experiment_r0 as exp
from report_ab import CATEGORIES, PROJECTS, pct, ncorrect


def table(headers, rows):
    return "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n" + "\n".join(
        "| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |" for row in rows)


def build(out):
    s, v = exp.read(out / "summary.json"), exp.read(out / "verification.json")
    assert s["status"] == "COMPLETE" and v["status"] == "PASS"
    assert exp.original.sha(out / "summary.json") == v["source_hashes"]["summary.json"]
    pop = s["by_population"]["all96"]
    ms, cs, arms = pop["metrics"], pop["comparisons"], ["A", "B", "R0"]
    a, b, r = [ms[k] for k in arms]
    stable = all(m["different_output_questions"] == 0 for m in ms.values())
    count_note = ("각 문제·방식의 최종 답은 세 번 모두 같았다. 아래 정답 수는 반복을 빼고 서로 다른 96문제를 기준으로 표시한다."
                  if stable else "반복에 따라 답이 달라진 문제가 있으므로 정답률은 문제별 3회 성공률의 평균이고, 정답 수는 그 비율을 문제 수로 환산한 값이다.")
    overview = (f"전체 96문제에서 **A는 {ncorrect(a)}개({pct(a['accuracy'])}), B는 {ncorrect(b)}개({pct(b['accuracy'])}), "
                f"R0은 {ncorrect(r)}개({pct(r['accuracy'])})**를 맞혔다. 대표 응답 시간은 각각 "
                f"**{a['mean_query_seconds']:.2f}초, {b['mean_query_seconds']:.2f}초, {r['mean_query_seconds']:.2f}초**였다.")
    observations = []
    for base in ["A", "B"]:
        c = cs[f"R0-{base}"]
        observations.append(f"{base} 대비 정답률 {c['delta_pp']:+.1f}%p, 관측 시간 {c['latency_delta_seconds']:+.2f}초 "
                            f"({-c['latency_reduction_pct']:+.1f}%)")
    overview += " R0은 " + "; ".join(observations) + "였다."
    metric_rows = []
    for label, fn in [
        ("정답 수 / 96문제", ncorrect), ("정답률: 높을수록 좋음", lambda m: pct(m["accuracy"])),
        ("대표 응답 시간: 짧을수록 좋음", lambda m: f"{m['mean_query_seconds']:.2f}초"),
        ("느린 요청의 시간: p95", lambda m: f"{m['request_p95_seconds']:.2f}초"),
        ("전달한 코드 길이: 요청당 평균", lambda m: f"{m['mean_context_tokens']:.1f}토큰"),
        ("전체 입력량: 실제 AI 호출의 합", lambda m: f"{m['mean_input_tokens']:.1f}토큰"),
        ("지정 원문 근거의 평균 포함률", lambda m: pct(m["raw_evidence_recall"])),
        ("지정 원문 근거를 모두 포함한 비율", lambda m: pct(m["all_raw_evidence"])),
        ("전달한 원문의 파일 수: 평균", lambda m: f"{m['mean_source_files']:.2f}개"),
    ]:
        metric_rows.append([label, *[fn(ms[arm]) for arm in arms]])
    metric_rows.append(["질문당 AI 호출 수", "2회: 함수 선택 + 답변", "2회: 함수 선택 + 답변", "1회: 답변"])
    main_table = table(["지표", "현재 색인(A)", "파일 간 확장(B)", "원문 검색(R0)"], metric_rows)
    contrasts = []
    for key in ["B-A", "R0-A", "R0-B"]:
        c = cs[key]
        contrasts.append([key.replace("-", " − "), f"{c['delta_pp']:+.1f}%p",
                          f"{c['ci95_pp'][0]:+.1f} ~ {c['ci95_pp'][1]:+.1f}%p",
                          f"{c['win']} / {c['loss']} / {c['tie']}"])
    contrast_table = table(["정답률 비교", "차이", "탐색적 95% 추정 구간", "앞 방식 승 / 패 / 동률 문제 수"], contrasts)
    p_note = (f"프로젝트 단위 보조 검정의 p값은 기존 B−A가 {cs['B-A']['unadjusted_project_signflip_p']:.3f}, "
              f"새 비교 R0−A는 {cs['R0-A']['holm_p_two_new_quality_contrasts']:.3f}, "
              f"R0−B는 {cs['R0-B']['holm_p_two_new_quality_contrasts']:.3f}이다. "
              "새 두 비교는 여러 비교로 우연한 차이를 고를 가능성을 줄이도록 Holm 보정을 적용했다. "
              "p값이 0.05보다 크면 이 검정만으로 차이가 있다고 확정하지 않으며, 성능이 같다는 증명도 아니다.")
    for key in ["R0-A", "R0-B"]:
        c = cs[key]
        if c["ci95_pp"][0] > 0 and c["holm_p_two_new_quality_contrasts"] > .05:
            p_note += (f" {key.replace('-', '−')}의 재표집 구간은 0을 포함하지 않지만, 보정한 프로젝트 단위 검정에서는 "
                       "차이를 확정하지 못했다. 추정 방법이 다르고 프로젝트가 6개뿐이라는 한계 때문에 이를 일반적인 우위의 증명으로 읽지 않는다.")
    subsets = []
    for key,label in [("original48", "기존 문제 48개"), ("additional48", "추가 문제 48개")]:
        mm = s["by_population"][key]["metrics"]
        subsets.append([label, *[f"{ncorrect(mm[x])} / 48" for x in arms],
                        *[f"{mm[x]['mean_query_seconds']:.2f}초" for x in arms]])
    subset_table = table(["문제 집합", "A 정답", "B 정답", "R0 정답", "A 시간", "B 시간", "R0 시간"], subsets)
    category_rows, project_rows = [], []
    for key,label in CATEGORIES.items():
        cc = [ms[arm]["by_category"][key] for arm in arms]
        category_rows.append([label, cc[0]["unique_questions"], *[f"{x['question_equivalent_correct']:g}" for x in cc],
                              f"{cc[2]['question_equivalent_correct']-cc[1]['question_equivalent_correct']:+g}"])
    for key,label in PROJECTS.items():
        cc = [ms[arm]["by_project"][key] for arm in arms]
        project_rows.append([label, *[f"{x['question_equivalent_correct']:g} / 16" for x in cc]])
    category_table = table(["질문 종류", "문제 수", "A 정답", "B 정답", "R0 정답", "R0 − B"], category_rows)
    project_table = table(["프로젝트 주제", "A 정답", "B 정답", "R0 정답"], project_rows)
    deltas = {key: r["by_category"][key]["question_equivalent_correct"] - b["by_category"][key]["question_equivalent_correct"] for key in CATEGORIES}
    highest, lowest = max(deltas,key=deltas.get), min(deltas,key=deltas.get)
    category_note = (f"B와 비교하면 R0의 정답 수는 **{CATEGORIES[highest]}에서 {deltas[highest]:+g}문제**, "
                     f"**{CATEGORIES[lowest]}에서 {deltas[lowest]:+g}문제** 차이가 났다. "
                     "전체 정답 수의 차이가 모든 질문 종류에서 일관된 우위를 뜻하지는 않는다.")
    def seconds(x):
        return "0.001초 미만" if x < .001 else f"{x:.3f}초"
    stage_table = table(["처리 단계", "A 평균", "B 평균", "R0 평균"], [
        ["후보 구성·AI의 출발 함수 선택", seconds(a["mean_select_seconds"]), seconds(b["mean_select_seconds"]), "없음"],
        ["질문별 참조 확장", seconds(a["mean_expansion_seconds"]), seconds(b["mean_expansion_seconds"]), "없음: 묶음은 사전 준비"],
        ["원문 후보의 검색 점수 계산", "해당 없음", "해당 없음", seconds(r["mean_retrieval_seconds"])],
        ["길이 확인·전달 자료 구성", *[seconds(ms[x]["mean_packing_seconds"]) for x in arms]],
        ["AI의 최종 답변 처리", *[seconds(ms[x]["mean_answer_seconds"]) for x in arms]],
    ])
    timing = table(["비교", "관측 시간 차이", "증감률", "해석"], [
        [key.replace("-", " − "), f"{cs[key]['latency_delta_seconds']:+.2f}초",
         f"{-cs[key]['latency_reduction_pct']:+.1f}%", "같은 세션에서 교차 실행" if key == "B-A" else "다른 세션 간 관측 비교"]
        for key in ["B-A", "R0-A", "R0-B"]])
    qmap = {q["task_id"]: q for q in s["questions"]}
    examples = []
    selected = ["eval_inventory__v2_partial_depletes_available", "eval_authorization__v2_duplicate_write_permission"]
    # Keep both original examples and show one counterexample to R0 when present.
    losses = [q for q in s["questions"] if q["arms"]["R0"]["score"] < max(q["arms"][x]["score"] for x in ["A", "B"])
              and q["task_id"] not in selected]
    selected_has_loss = any(qmap[t]["arms"]["R0"]["score"] < max(qmap[t]["arms"][x]["score"] for x in ["A", "B"]) for t in selected)
    if losses and not selected_has_loss:
        selected.append(sorted(losses, key=lambda q: (q["category"] != "cross_file", q["task_id"]))[0]["task_id"])
    titles = ["재고 계산: 세 방식이 서로 다른 값을 답한 사례", "권한 계산: 더 깊은 정의까지 포함한 R0의 답변", "R0이 놓친 문제도 함께 확인"]
    for title,tid in zip(titles,selected):
        q = qmap[tid]
        show = lambda value: "`" + json.dumps(value,ensure_ascii=False,sort_keys=True) + "`"
        rows = [["실제 답변", *[show(q["arms"][x]["answer"]) for x in arms]],
                ["정답 여부", *["정답" if q["arms"][x]["score"] == 1 else "오답" if q["arms"][x]["score"] == 0 else "반복별 차이" for x in arms]],
                ["전달 코드 길이", *[f"{q['arms'][x]['context_tokens']}토큰" for x in arms]],
                ["원문 파일", *[", ".join(q["arms"][x]["source_files"]) for x in arms]]]
        detail = ""
        if tid == selected[0]:
            detail = ("재고 9개에서 이미 잡힌 1개와 안전재고 3개를 빼면 판매 가능량은 5개다. "
                      "8개를 요청해도 부분 예약은 5개만 이루어지므로 남는 수량은 0개다. "
                      "A에는 같은 파일의 코드가, B에는 판매 가능량 계산과 안전재고 값이 추가로 전달됐다.")
        elif tid == selected[1]:
            detail = ("권한의 공백·대문자를 정리하고 중복을 제거하면 유효한 쓰기 권한이 남는다. "
                      "세션 경과 시간도 1,799초로 제한 3,600초보다 짧아 정답은 true다. "
                      "B의 두 차례 확장에는 권한 정규화 함수 등의 더 깊은 정의가 빠져 있었다.")
        else:
            detail = "같은 질문에서 R0보다 A 또는 B가 잘 답한 실제 반례다. 원문을 더 많이 전달해도 정확한 답이 보장되지는 않는다."
        task = next(t for t in exp.read(out / "tasks.json") if t["id"] == tid)
        sources = set(q["arms"]["R0"]["sources"])
        if set(task["required_uris"]) <= sources:
            detail += " R0에는 이 문제에 지정된 원문 근거가 모두 포함됐다."
            if q["arms"]["R0"]["score"] == 0:
                detail += " 그럼에도 답은 틀렸으므로, 지정 근거를 확보하는 것만으로 정답이 보장되지 않는 사례다."
        if tid == selected[1] and {"memory://symbol/rules.py::normalized_scopes", "memory://symbol/policy.py::MAX_SESSION_AGE"} <= sources:
            detail += " R0에는 권한 정규화 함수와 세션 제한값도 전달됐다."
        examples.append(f"### {title}\n\n질문: `{q['question']}`  \n정답: {show(q['expected'])}\n\n" +
                        table(["항목", "A", "B", "R0"], rows) + f"\n\n{detail} "
                        "각 방식의 검색 범위·묶음 깊이·표시 순서가 함께 달라지므로, 이 사례만으로 오답의 원인이나 개선 요인의 기여도를 확정할 수 없다."
                        f"\n\n기록 식별자: `{tid}`.")
    best = max(arms,key=lambda x: ms[x]["accuracy"])
    names = {"A": "현재 색인(A)", "B": "파일 간 확장(B)", "R0": "원문 검색(R0)"}
    quality_conclusion = f"이 자료에서 관측 정답률이 가장 높은 방식은 **{names[best]}**다."
    if r["accuracy"] > max(a["accuracy"],b["accuracy"]):
        quality_conclusion += " R0은 정확도를 우선하는 후속 검증 대상으로 볼 수 있다."
    elif r["accuracy"] < max(a["accuracy"],b["accuracy"]):
        quality_conclusion += " 이번 결과는 R0으로 전면 교체할 정확도 근거를 제공하지 않는다."
    else:
        quality_conclusion += " R0의 전면 교체 여부를 정답 수만으로 결정하기 어렵다."
    uncertain = [key.replace("-", "−") for key in ["R0-A", "R0-B"] if cs[key]["ci95_pp"][0] <= 0 <= cs[key]["ci95_pp"][1]]
    if uncertain:
        quality_conclusion += " " + "·".join(uncertain) + "의 정답률 차이 추정 구간은 0을 포함하므로, 해당 비교의 정확도 우위는 확정하지 않는다."
    coverage_note = (f"R0의 지정 근거 평균 포함률은 **{pct(r['raw_evidence_recall'])}**였지만 정답률은 **{pct(r['accuracy'])}**였다. "
                     "원문 확보량의 증가가 그대로 정답률 증가로 이어지지는 않았다.")
    if r["all_raw_evidence"] == 1:
        coverage_note += (" 이번 96문제에서는 지정한 목록의 원문 누락이 관측되지 않았다. "
                          "따라서 검색 누락 외에도 코드 해석·계산·답변 형식과 불필요한 원문 전달의 영향을 함께 점검할 필요가 있다. "
                          "각 원인이 오답에 얼마나 기여했는지는 이번 비교에서 분리하지 않았다.")
    content = f'''# 현재 색인(A)·파일 간 확장(B)·원문 검색(R0): 재실험 비교 보고서

**질문: 코드 질문에 답할 원문을 고르는 세 방식 중, 무엇이 더 정확하고 얼마나 오래 걸리는가?**  
실험일: 2026년 10월 24일 · R0 추가 반영 · 세 방식 모두 RAPTOR 요약 사용 없음

{overview}

**시간 해석 주의:** A·B는 한 세션에서 번갈아 측정했고, R0은 같은 장비·모델·설정으로 이후 별도 세션에서 측정했다. R0의 시간 차이에는 세션별 장비 상태의 영향이 섞일 수 있다. 아래 수치는 관측값이며 검색 방식만의 순수한 속도 효과로 확정하지 않는다.

## 1. A·B·R0은 각각 무엇인가?

`symbol_index`는 함수 등의 이름과 코드 위치를 정리한 **코드 주소록**이다. 함수는 계산이나 작업을 수행하는 코드 단위이고, 원문은 프로그램에 실제 작성된 코드다. A·B는 이 주소록에서 AI가 출발 함수를 고른 뒤 관련 원문을 수집한다.

**원문 검색 방식(R0, 끝 글자는 숫자 0)**은 질문의 단어와 코드 원문에 등장하는 단어를 비교해, 관련성이 높은 **원문 후보 여러 개를 고르는 방식**이다. 후보에는 함수·상수 하나의 원문과, 그 코드가 참조하는 다른 코드까지 미리 묶은 원문이 있다. AI가 출발 함수 하나를 선택하는 단계 없이 검색 프로그램이 후보를 정렬하고, 마지막에 AI가 선택된 원문을 읽어 답한다.

| 항목 | 현재 색인(A) | 파일 간 확장(B) | 원문 검색(R0) |
|---|---|---|---|
| 무엇을 먼저 고르나? | 색인 후보 최대 24개 중 AI가 출발 함수 선택 | A와 같은 선택 규칙 | 알려진 대상 프로젝트의 원문 후보를 검색 점수순으로 정렬 |
| 관련 코드를 모으는 방법 | 같은 파일의 함수·상수 참조 확장 | import 연결을 통해 다른 파일의 참조까지 확장 | 단일 원문과 사전 준비된 참조 묶음을 함께 검색 |
| 관계를 따라가는 범위 | 두 차례 확장, 함수 등 최대 8개; 상수 별도 | 두 차례 확장, 함수 최대 8개; 상수 별도 | 묶음 준비 시 출발점에서 참조 연결 최대 3단계; 8개 함수 제한 없음 |
| 실제 전달량 제한 | 원문 합계 최대 1,024토큰 | 같음 | 같음 |
| 질문당 AI 호출 | 출발 함수 선택 + 답변 | 출발 함수 선택 + 답변 | 답변만 |
| RAPTOR 요약 | 사용하지 않음 | 사용하지 않음 | 사용하지 않음 |

### R0이 동작하는 과정

1. **사전 준비:** 코드를 함수·상수 단위로 나눈다. 각각의 원문과, 다른 파일을 포함해 참조 연결을 최대 3단계 따라 모은 원문 묶음을 후보로 만든다. 묶음에 코드가 여러 개 있으면 출발 코드 하나만 담은 후보도 함께 둔다.
2. **질문과 비교:** 질문과 후보의 단어를 비교한다. 여러 후보에 흔한 단어보다 드문 단어에 더 높은 가중치를 주는 TF-IDF 점수와 코사인 유사도를 사용한다. 여기서 ‘유사도’는 **단어 구성의 유사도**이며, 의미를 학습한 임베딩 검색이 아니다.
3. **길이 안에 담기:** 점수가 높은 후보부터 전체를 넣어 본다. 합계 1,024토큰을 넘는 후보는 건너뛰고 다음 후보를 검토한다. 이미 포함된 코드만으로 이루어진 후보도 건너뛴다. 일부만 겹치는 후보는 코드가 중복될 수 있다. 최소 검색 점수 기준은 없어 공간이 남으면 낮은 점수의 후보도 들어간다.
4. **답변 생성:** 선택한 원문을 A·B와 동일한 답변 모델에 전달한다. 검색 과정은 정답이나 정답용 코드 목록을 보지 않는다.

따라서 R0을 ‘파일 전체를 단순 문자열 검색하는 방식’이나 ‘아무 사전 색인도 없는 방식’으로 이해하면 부정확하다. 이 실험의 R0은 **참조 묶음을 준비한 뒤 원문을 단어 기반으로 검색하는 구현**이다.

```mermaid
flowchart TD
    Q["코드에 대한 질문"] --> S["A·B: 색인 후보에서 AI가 출발 함수 선택"]
    S --> A["A: 같은 파일의 관련 원문 수집"]
    S --> B["B: 다른 파일의 참조까지 두 차례 확장"]
    P["사전 준비: 단일 원문 + 최대 3단계 참조 묶음"] --> R["R0: 질문과 원문의 단어를 비교해 후보 정렬"]
    Q --> R
    A --> C["최대 1,024토큰 안에 자료 구성"]
    B --> C
    R --> C
    C --> M["동일한 AI가 답변"]
    M --> E["정답·시간·근거 포함률 측정"]
```

### A·B와 R0의 차이를 재고 코드로 보면

`service.py`의 잔여 수량 함수 `remaining_after()`는 `rules.py`의 판매 가능량 함수 `sellable()`을 부르고, 이 함수는 `policy.py`의 안전재고 값 `SAFETY_STOCK`을 사용한다.

| 방식 | 해당 코드에 접근하는 과정 |
|---|---|
| A | AI가 `remaining_after()`를 고르면 같은 파일의 `reserve()` 등도 수집한다. 다른 파일의 `sellable()` 정의는 따라가지 않는다. |
| B | 같은 출발점에서 import와 이름 참조를 따라 `sellable()`, 다음 확장에서 `SAFETY_STOCK`까지 수집할 수 있다. |
| R0 | `remaining_after()`의 관련 코드 묶음도 후보지만, 다른 함수·상수의 후보와 함께 검색 점수로 경쟁한다. 점수와 남은 길이에 따라 여러 후보를 조합한다. |

A도 함수 하나만 읽는 방식은 아니다. B의 관계 추적은 AI가 다음 파일을 고르는 과정이 아니라 코드 분석으로 만든 연결을 프로그램이 따라가는 과정이다. R0도 같은 종류의 연결을 묶음 준비에 쓰지만, 질문을 받은 뒤 원문을 고르는 규칙이 다르다.

## 2. 같은 실험을 어떻게 적용했나?

기존 재실험의 **A·B 각 96문제 × 3회 = 576답변을 그대로 유지**하고, 이번에 **R0도 같은 96문제 × 3회 = 288답변을 새로 생성**했다. 비교 대상은 합계 864답변이다. 과거 다른 실험의 R0 점수를 가져오지 않았다.

| 설계 항목 | 실제 조건 |
|---|---|
| 평가 자료 | 같은 합성 Python 프로젝트 6개, 프로젝트당 파일 5개·질문 16개 |
| 문제 구성 | 기존 48개 + 추가 48개; 한 함수 계산 12, 여러 파일 계산 24, 경계 조건 12, 자연어 동작 24, 변경 영향 12, 호출 구조 12 |
| 모델·장비 | Qwen2.5-Coder-7B-Instruct Q5_K_M · Apple M3 Pro · 메모리 36 GiB |
| 공통 제한 | 근거 1,024토큰, 답변 최대 128토큰, 모델 전체 문맥 8,192토큰 |
| 반복 조건 | temperature 0, seed 1, 방식별 각 질문 3회 |
| 함수 선택 | A·B는 매번 실제 AI 호출, 최대 96토큰; R0에는 이 단계가 없음 |
| 실행 순서 | A·B는 무작위 질문 쌍 안에서 선후 순서를 균형 배치; R0은 동일한 질문·반복 블록 순서를 따름 |
| 세션 | A·B 공동 세션 / R0 별도 세션. 모델 파일·서버 실행 파일·주요 설정의 동일성 확인 |
| 캐시 | 모델 입력 계산 재사용 끔; 토큰 수 계산 캐시는 질문마다 비움 |
| 정답 검증·채점 | 96개 기준 답 재확인; JSON 값·자료형·요구한 목록 순서까지 일치해야 정답 |

{count_note} 개발용 8문제는 각 방식의 실행 점검에만 사용했고 점수에서 제외했다. A·B의 출발 함수는 기존 288개 실행 쌍 모두에서 같았다. R0은 출발 함수를 선택하지 않으므로 이 일치율의 비교 대상이 아니다.

**비교 범위:** 세 방식은 원문 선택 규칙뿐 아니라 참조 깊이·원문 표시·순서·실제 전달량도 다르다. 이는 **구현 전체의 비교**이며 파일 간 확장, 검색 점수, 깊이 중 한 요소의 효과만 분리한 실험은 아니다. RAPTOR 추가 효과도 측정하지 않았다.

## 3. 정답·시간·전달 자료의 정량 비교

{main_table}

대표 응답 시간은 **문제별 3회 시간의 중앙값을 구한 뒤 96문제에 걸쳐 평균**한 값이다. 검색 시작부터 답변 완료까지 실제 시간을 측정하며 선택·수집·길이 확인·작은 호출 로그 기록을 포함한다. 모델 시작, 사전 색인·참조 관계·원문 후보·검색 벡터 준비와 채점은 제외한다.

**p95**는 해당 방식의 288개 요청 중 약 95%가 완료되는 시간이다. **토큰**은 AI가 글을 처리하는 작은 단위다. 전체 입력량은 A·B의 경우 함수 선택과 답변 입력의 합이며, R0은 답변 입력만 있다.

**근거 포함률**은 문제별로 미리 지정한 코드 목록 중 전달된 원문의 비율이다. 이 목록은 진단용이며 반드시 필요한 최소 코드 집합과 같지는 않다. 포함률이 높아도 AI가 정확히 계산하거나 답했다는 뜻은 아니다.

{coverage_note}

### 얼마나 더 맞혔고, 차이는 얼마나 확실한가?

{contrast_table}

`%p`는 두 정답률의 단순 차이다. 승·패는 같은 문제에서 앞 방식의 점수가 뒤 방식보다 높거나 낮은 경우다. 추정 구간이 0을 포함하면, 이 표본으로 정확도 우위를 확정하기 어렵다.

{p_note}

추정 구간은 **6개 프로젝트를 묶음으로 다시 뽑는 46,656가지 조합**으로 계산했다. 864답변을 독립된 864문제로 취급하지 않았다. 프로젝트 수가 적고 구조도 비슷하므로 탐색적 추정이다.

### 두 문제 집합의 결과

{subset_table}

A·B 값은 보존한 기존 재실험 결과이고 R0 값은 이번 추가 측정 결과다. 두 문제 집합은 같은 프로젝트를 공유하고 이미 알려진 문제이므로, 별도의 새 저장소 검증으로 해석하지 않는다.

## 4. 어떤 질문에서 차이가 났나?

{category_table}

{category_note}

{project_table}

각 칸의 문제 수가 작으므로 종류별 우열을 확정하지 않는다. 함수의 연결을 나열하는 문제와 여러 파일의 규칙을 적용해 정확한 값을 계산하는 문제도 구분해서 봐야 한다.

## 5. 응답 시간과 처리량은 어떻게 달라졌나?

{timing}

{stage_table}

단계별 값은 288요청 전체의 평균이다. 앞서 제시한 ‘문제별 중앙값의 평균’과 집계 방식이 달라 합계가 정확히 같을 필요는 없다. AI의 답변 처리에는 입력을 읽는 계산과 출력 생성이 모두 포함된다.

R0은 출발 함수 선택 호출을 생략하지만, 후보를 차례로 길이 확인하고 선택한 원문 전체를 답변 모델에 전달한다. **호출 횟수가 적다는 사실만으로 전체 응답 시간이 짧아지지는 않는다.** 실제 시간과 입력량을 함께 비교해야 한다.

길이 상한 때문에 후보가 하나 이상 제외된 요청은 A {a['queries_with_rejected_fragments']} / 288, B {b['queries_with_rejected_fragments']} / 288, R0 {r['queries_with_rejected_fragments']} / 288이었다. R0은 많은 후보를 끝까지 검토하므로, 후보 제외 자체가 필요한 근거 누락이나 검색 실패를 뜻하지는 않는다. 세 방식 모두 같은 상한을 받았지만 상한을 가득 채우도록 강제하지 않았다.

R0의 시간 비교는 별도 세션이라는 한계가 있다. 같은 설정을 확인했어도 장비 부하·열 상태 등의 영향을 제거한 것은 아니다. 처리량 차이와 함께 해석할 수 있는 **관측 속도 비교**이며, 순수한 속도 효과를 확정하려면 세 방식을 같은 세션에서 무작위로 번갈아 실행해야 한다.

## 6. 실제 답변 사례

이전 보고서의 개선·실패 사례 두 개를 유지해 R0 결과를 함께 붙였다. 두 사례에 R0의 반례가 없을 때만 별도 반례를 추가한다. 각 표의 실제 답변·원문은 첫 번째 반복 기록이며, 전체 결과를 대표하는 사례는 아니다.

{(chr(10)*2).join(examples)}

목록 원소가 같고 순서만 틀린 답을 허용하는 보조 채점에서는 A {pct(a['order_tolerant_accuracy'])}, B {pct(b['order_tolerant_accuracy'])}, R0 {pct(r['order_tolerant_accuracy'])}다. 이 진단은 앞의 엄격한 주 점수를 대체하지 않는다.

## 7. 판단과 한계

{quality_conclusion} 정답률 차이의 크기와 추정 구간, 응답 시간 요구를 함께 봐야 한다. **원문을 더 많이 모으는 것과 정확한 답을 만드는 것은 별개의 문제**다.

전체 정답률은 A {pct(a['accuracy'])}, B {pct(b['accuracy'])}, R0 {pct(r['accuracy'])}였다. 이번 상대 비교만으로 어느 방식이 실사용에 충분히 신뢰할 수 있다고 판단하지 않는다.

평가는 영어 질문, 구조가 비슷한 합성 Python 프로젝트 6개, 한 모델·한 장비에 한정된다. 질문이 속한 프로젝트를 알고 시작한다. 실제 저장소에서 프로젝트를 찾는 성능, 한국어 질문, 복잡한 import·동적 호출, 코드 수정이나 보안 취약점 탐지 성능은 평가하지 않았다. 질문 재사용과 R0의 별도 실행 세션도 한계다.

후속 검증에서는 세 방식을 같은 세션에서 교차 실행하고, 독립된 실제 저장소를 사용해야 한다. 또 원문 표시와 탐색 깊이를 고정한 비교를 별도로 해야 검색 규칙 자체가 얼마나 기여했는지 구분할 수 있다. 이 보고서는 아직 실행하지 않은 평가의 효과를 결과에 포함하지 않는다.

## 확인 자료와 재현

R0의 실행 완전성, 모델·캐시·시간 기록, 정답 재채점, 원문 후보·검색 순위·길이 제한 재구성, 별도 토큰 계산과 주요 통계 재계산을 확인해 **{v['count']}개 점검을 통과**했다. A·B의 기존 점수와 원자료가 유지되는지도 확인했다. 이는 로컬 기록의 일관성 검증이며 외부 인증은 아니다.

| 확인할 내용 | 파일 |
|---|---|
| 세 방식의 통합 집계·질문별 비교 | [A·B·R0 통합 결과](evidence/r0_20261024/summary.json) |
| 새 R0 실험 규칙·고정 입력 | [R0 실험 계획](evidence/r0_20261024/protocol.json) |
| R0 질문별 원문·검색 점수·답변·시간 | [새 288회 실행 기록](evidence/r0_20261024/results.jsonl) |
| 정답과 검증 결과 | [96개 정답 재확인](evidence/r0_20261024/gold_recheck.json) · [R0 검증](evidence/r0_20261024/verification.json) |
| R0 실행 환경 | [환경 기록](evidence/r0_20261024/environment.json) |
| 기존 A·B 자료 | [576회 실행 기록](evidence/ab_20261024/results.jsonl) · [기존 집계](evidence/ab_20261024/summary.json) · [기존 검증](evidence/ab_20261024/verification.json) |
| 원문 선택의 실제 구현 | [R0의 raw_items·Retriever·pack 및 B의 확장](evidence/r0_20261024/source_snapshot/experiment.py) · [A의 확장](evidence/r0_20261024/source_snapshot/indexer.py) |
| 재현 방법 | [R0 실행·집계·검증 안내](evidence/r0_20261024/reproduce.txt) |
| R0 반영 전 보고서 | [기존 보고서 보관본](evidence/r0_20261024/history/report_before_R0.md) |

사용자가 지정한 기존 Markdown 파일을 갱신했다. A·B 원자료와 갱신 전 보고서는 보존했고, R0의 새 자료는 별도 폴더에 저장했다.
'''
    exp.REPORT.write_text(content)
    exp.original.dump(out / "report_manifest.json", {"created_at_utc": exp.audited.now(), "report": str(exp.REPORT),
        "report_sha256": exp.original.sha(exp.REPORT), "summary_sha256": exp.original.sha(out / "summary.json"),
        "verification_sha256": exp.original.sha(out / "verification.json"), "generator_sha256": exp.original.sha(__file__)})
    print(json.dumps({"report": str(exp.REPORT), "characters": len(content)},ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=exp.DEFAULT_OUT)
    build(p.parse_args().out)
