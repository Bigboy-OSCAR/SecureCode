# 2차 실험 종합 설명서

이 문서는 프로젝트 배경지식이나 LLM 사전지식이 없는 사람도 네 가지 실험을 이해할 수 있도록 정리한 설명서이다.

참고한 원문 보고서는 다음 네 개이다.

- `runtime_pointer_test/runtime_pointer_test.md`
- `self_extend_test/self_extend_test_2.md`
- `source_pointer_test/source_pointer_test.md`
- `symbol_test/symbol_test_2.md`

## 목차

1. 이 실험들이 다루는 문제
2. 네 실험의 전체 요약
3. Runtime Pointer 실험
4. Self-Extend 2차 실험
5. Source Pointer 실험
6. Symbol Bundle / Filtered Selector 2차 실험
7. 네 실험을 함께 보면 알 수 있는 점
8. 코드 어시스턴트에 적용하는 구조
9. 용어 설명

## 1. 이 실험들이 다루는 문제

LLM은 사용자가 준 글, 코드, 로그, 문서 등을 읽고 답을 만든다. 하지만 한 번에 읽을 수 있는 양에는 제한이 있다. 이 제한을 `context window`라고 한다.

코드 어시스턴트가 실제 개발 작업을 도와주려면 다음처럼 큰 자료를 자주 다뤄야 한다.

- 전체 코드베이스
- 긴 테스트 실패 로그
- 큰 JSON 응답
- 운영 로그
- 프로젝트 문서
- 실행 중 생성된 tool output

이런 자료를 전부 LLM에게 그대로 넣으면 문제가 생긴다.

1. 너무 길어서 아예 처리하지 못한다.
2. 처리하더라도 시간이 오래 걸린다.
3. 긴 내용 속에서 중요한 부분을 놓칠 수 있다.
4. 관련 없는 정보가 많아져서 오답을 낼 수 있다.

이번 네 가지 실험은 이 문제를 서로 다른 방향에서 확인한다.

- `source pointer`: disk에 이미 있는 큰 외부 파일을 직접 넣지 않고 필요한 부분만 읽을 수 있는가?
- `runtime pointer`: 실행 중 생긴 큰 결과물을 직접 넣지 않고 필요한 부분만 읽을 수 있는가?
- `symbol bundle`: 전체 코드나 전체 symbol 목록을 넣지 않고 필요한 코드 조각 묶음만 읽을 수 있는가?
- `Self-Extend`: LLM이 한 번에 읽을 수 있는 길이 자체를 늘리면 문제를 해결할 수 있는가?

## 2. 네 실험의 전체 요약

| 실험 | 핵심 질문 | 핵심 결과 |
|---|---|---|
| Runtime Pointer | 실행 중 생긴 큰 tool output을 `runtime://...` pointer로 다룰 수 있는가? | 가능했다. pointer 방식은 small/medium 모두 3개 task를 전부 맞혔고, 전체 output을 넣는 방식은 1/3만 성공했다. |
| Self-Extend 2차 | context 길이를 늘리면 긴 입력 속 정답 회수도 좋아지는가? | 길이 수용은 늘었지만 정답 회수는 실패했다. 현재 조건에서는 기본 retrieval 방식으로 쓰기 어렵다. |
| Source Pointer | disk에 있는 큰 외부 파일을 `source://...` pointer로 다룰 수 있는가? | 가능했다. pointer 방식은 small/medium 모두 3개 task를 전부 맞혔고, 전체 파일을 넣는 방식은 1/3만 성공했다. |
| Symbol Bundle | 전체 코드 index 대신 관련 symbol 묶음만 읽어도 되는가? | selector 비용과 prompt 크기는 크게 줄었다. 다만 필요한 코드가 들어와도 LLM의 계산 실수로 최종 정확도는 1/3이었다. |

가장 중요한 결론은 다음과 같다.

```text
긴 정보를 전부 LLM에게 넣는 것보다,
필요한 정보만 찾아서 작게 넣는 구조가 더 안정적이다.
```

Self-Extend처럼 context window 자체를 늘리는 방식은 overflow를 피하는 데 도움을 줄 수 있다. 하지만 이번 결과 기준으로는 "긴 입력을 받는 것"과 "긴 입력 속에서 정답을 정확히 찾는 것"은 다른 문제였다.

## 3. Runtime Pointer 실험

### 3.1 실험 목적

Runtime Pointer 실험은 실행 중 생성된 큰 데이터를 LLM context에 직접 넣지 않고, 짧은 pointer로 관리할 수 있는지 확인한 실험이다.

예를 들어 테스트 실행 tool이 60만 글자짜리 로그를 만들었다고 하자. 이 로그 전체를 LLM에게 주는 대신, 프로그램 내부 저장소에 로그를 저장하고 다음 같은 짧은 주소만 전달한다.

```text
runtime://log/collect_checkout_trace/0001
```

그 다음 필요한 경우 전용 tool이 이 pointer를 열어서 필요한 줄이나 section만 추출한다.

### 3.2 실험 환경

| 항목 | 값 |
|---|---|
| Machine | M3 MacBook Pro |
| Backend | llama.cpp / Metal |
| LLM | Qwen2.5 Coder 7B Instruct GGUF Q5_K_M |
| Context size | 32768 |
| Generation limit | 128 |
| Temperature | 0 |
| Seed | 1 |
| Timeout | 300초 |

문법 검증은 다음 명령으로 수행했다.

```bash
uv run python -m compileall runtime_pointer_test
```

### 3.3 테스트 방식

실험은 세 가지 방식을 비교했다.

| mode | 설명 |
|---|---|
| `full_runtime` | 실행 중 생긴 큰 output 전체를 prompt에 직접 넣는다. |
| `runtime_pointer_oracle` | 필요한 추출 tool call을 이미 알고 있다고 가정하고, tool이 뽑은 일부만 prompt에 넣는다. |
| `runtime_pointer_select` | LLM이 작은 runtime catalog와 tool 설명을 보고 어떤 tool을 쓸지 고른 뒤, 추출 결과로 답한다. |

사용한 runtime output은 세 종류이다.

| runtime output | small raw chars | medium raw chars | 질문 |
|---|---:|---:|---|
| checkout trace log | 79,071 | 608,116 | 특정 `request_id`의 `reason`, `retry_after_ms` 찾기 |
| operations runbook markdown | 9,007 | 59,599 | 특정 section의 `max_retries`, `jitter_percent` 찾기 |
| tenant snapshot dict | 134,023 | 891,159 | 특정 tenant의 `runtime_pointer_enabled`, `max_context_policy` 찾기 |

사용한 추출 tool은 다음과 같다.

| tool | 역할 |
|---|---|
| `grep_runtime_log` | 긴 runtime log에서 특정 패턴 주변 줄만 추출한다. |
| `extract_runtime_doc_section` | 긴 markdown 문서에서 질문과 가까운 section만 추출한다. |
| `extract_runtime_json_path` | 큰 JSON/dict에서 필요한 path만 추출한다. |

전체 흐름은 다음과 같다.

```text
runtime producer 실행
-> 큰 runtime output 생성
-> RuntimeStore에 저장하고 runtime:// pointer 발급
-> full_runtime은 전체 output을 prompt에 삽입
-> pointer mode는 pointer와 추출 tool output만 prompt에 삽입
-> LLM 답변이 기대 문자열을 포함하는지 평가
```

`runtime_pointer_select`는 LLM을 두 번 호출했다.

```text
1차 호출: 질문 + 작은 runtime catalog + tool 설명 -> tool call 선택
2차 호출: 선택된 tool call의 추출 결과 -> 최종 답변
```

측정한 지표는 정확도, 실행 시간, prompt 글자 수, prompt token 수, prompt 평가 시간, selector 정확도, tool output 크기이다.

### 3.4 결과

Small 결과:

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy | mean tool output chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| `full_runtime` | 3 | 0.333 | 4.961 | 18,785 | 8,940.97 | | 0 |
| `runtime_pointer_oracle` | 3 | 1.000 | 2.768 | 311 | 1,021.06 | 1.000 | 365 |
| `runtime_pointer_select` | 3 | 1.000 | 7.050 | 756 | 2,390.06 | 1.000 | 430 |

Small에서 `full_runtime`은 log와 JSON에서 context window를 초과했다. 문서 task는 성공했지만 pointer 방식보다 훨씬 많은 token과 시간이 필요했다.

성공한 문서 task만 비교하면 다음과 같다.

| mode | doc wall s | doc prompt tokens |
|---|---:|---:|
| `full_runtime` | 10.652 | 2,872 |
| `runtime_pointer_oracle` | 2.113 | 239 |
| `runtime_pointer_select` | 6.221 | 641 |

Medium 결과:

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy | mean tool output chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| `full_runtime` | 3 | 0.333 | 26.270 | 131,136 | 73,757.09 | | 0 |
| `runtime_pointer_oracle` | 3 | 1.000 | 2.610 | 311 | 988.99 | 1.000 | 365 |
| `runtime_pointer_select` | 3 | 1.000 | 6.891 | 757 | 2,361.86 | 1.000 | 430 |

Medium에서 `full_runtime`은 log와 JSON에서 context overflow로 실패했다. 문서 task는 성공했지만 18,377 prompt tokens와 75.64초가 필요했다.

Medium 기준으로 pointer 방식은 전체 주입 대비 다음만큼 줄였다.

| mode | prompt char reduction | wall time reduction |
|---|---:|---:|
| `runtime_pointer_oracle` | 99.8% | 90.1% |
| `runtime_pointer_select` | 99.5% | 73.8% |

또한 데이터 크기가 small에서 medium으로 커져도 pointer mode의 prompt token은 거의 변하지 않았다.

| mode | small prompt tokens | medium prompt tokens |
|---|---:|---:|
| `runtime_pointer_oracle` | 311 | 311 |
| `runtime_pointer_select` | 756 | 757 |

### 3.5 해석과 한계

Runtime pointer 방식은 이번 조건에서 유효했다. 큰 runtime output을 직접 넣으면 context overflow가 발생하거나 시간이 많이 걸렸지만, pointer와 추출 tool을 사용하면 필요한 정보만 작게 전달할 수 있었다.

한계도 있다.

- 실험 데이터는 synthetic runtime output이다.
- 실제 tool output에서는 extractor 품질과 schema 안정성이 정확도에 직접 영향을 준다.
- `runtime_pointer_select`는 LLM 호출이 두 번 필요하므로 아주 작은 데이터에서는 oracle보다 느릴 수 있다.
- JSON selector가 sibling field를 comma 형태로 합치는 출력이 있었다. 실제 시스템에서는 schema 검증과 path normalization이 필요하다.
- 현재 `RuntimeStore`는 process-local memory store이다. 실제 적용에는 session lifecycle, TTL, eviction, 권한 검사, 민감정보 처리, memory 상한이 필요하다.

### 3.6 적용 방향

코드 어시스턴트에서는 큰 test output, build log, API response, static analysis report를 message history에 직접 넣지 않는 것이 좋다. 대신 다음 구조가 적합하다.

```text
tool 실행
-> output이 크면 RuntimeStore에 저장
-> LLM에는 runtime:// pointer와 짧은 설명만 전달
-> 후속 tool이 pointer를 열고 필요한 부분만 추출
-> 추출된 작은 증거를 바탕으로 원인 분석 또는 코드 수정
```

## 4. Self-Extend 2차 실험

### 4.1 실험 목적

Self-Extend 실험은 LLM이 한 번에 읽을 수 있는 길이를 늘리는 방식이 실제 정답 회수에도 도움이 되는지 확인한 실험이다.

1차 실험에서는 Vicuna-7B-v1.5 Q4_K_M으로 passkey retrieval만 확인했다. 그 결과 Self-Extend를 켜면 긴 입력은 들어가지만 정답 회수는 실패했다.

2차 실험에서는 조건을 더 넓혔다.

- 모델을 논문 조건에 더 가까운 `Llama-2-7B-chat`으로 변경했다.
- `Q4_K_M`과 `Q5_K_M` 양자화를 비교했다.
- passkey 외에 PG-19 PPL과 코드 어시스턴스 benchmark를 추가했다.

### 4.2 실험 환경

| 항목 | 값 |
|---|---|
| base model | Llama-2-7B-chat |
| GGUF repo | TheBloke/Llama-2-7B-Chat-GGUF |
| quantization | Q4_K_M, Q5_K_M |
| train context length | 4096 |
| 주요 CLI | `llama-passkey`, `llama-completion`, `llama-perplexity`, `llama-tokenize` |
| backend | Homebrew llama.cpp, Metal/CPU |
| sampling | `--temp 0`, `--seed 1` |

도구별 Self-Extend 옵션 지원 여부도 확인했다.

| 도구 | Self-Extend 관련 옵션 |
|---|---|
| `llama-passkey` | `--grp-attn-n` 지원 |
| `llama-completion` | `--grp-attn-n`, `--grp-attn-w` 지원 |
| `llama-perplexity` | `--grp-attn-n` 미지원 |

`Q8_0`도 후보였지만 이번에는 실행 시간과 다운로드 현실성을 고려해 `Q4_K_M`, `Q5_K_M`만 비교했다.

### 4.3 테스트 방식

2차 실험은 세 부분으로 구성됐다.

첫째, passkey retrieval이다. 긴 무의미 텍스트 중간에 5자리 passkey를 숨기고, 마지막에 그 값을 묻는다.

| 변수 | 값 |
|---|---|
| 모델 | Q4_K_M, Q5_K_M |
| group attention | off, G=2, G=4 |
| 입력 길이 | `junk=160`, `180`, `320` |
| passkey | `16808` |
| 정답 판정 | 출력에 `16808`이 포함되는지 확인 |

입력 길이의 의미는 다음과 같다.

| 설정 | prompt tokens | 의미 |
|---|---:|---|
| `junk=160` | 약 3907 | 기본 4k 근처 |
| `junk=180` | 약 4387 | 기본 4k 초과 |
| `junk=320` | 약 7747 | 확장 context 필요 |

둘째, PG-19 PPL이다. PG-19는 긴 문학 텍스트를 바탕으로 언어 모델이 다음 단어를 얼마나 자연스럽게 예측하는지 보는 benchmark이다. 이번에는 test split 100개 파일을 다운로드하고, 앞 8권에서 각 12000자씩 잘라 샘플을 만들었다.

다만 `llama-perplexity`가 `--grp-attn-n`을 지원하지 않았기 때문에 PG-19는 Self-Extend on/off 비교가 아니라 Q4/Q5 baseline PPL 측정으로 진행했다.

셋째, 코드 어시스턴스 benchmark이다. 긴 repo context 안에서 필요한 코드 사실을 찾을 수 있는지 봤다.

| task | 질문 | 기대 정답 |
|---|---|---|
| `function_definition` | `derive_rotation_marker("apac", 7)`의 반환값 | `ROTATE::APAC::0007` |
| `symbol_reference` | `derive_rotation_marker`를 호출하는 함수명 | `schedule_rotation` |
| `test_failure_cause` | failing test의 원인 | `.lstrip("0")` 때문에 zero padding 제거 |

코드 benchmark의 prompt token 수는 약 4843에서 4855 tokens였다. group별 context 설정은 다음과 같다.

| 조건 | context size |
|---|---:|
| off | 4096 |
| G=2 | 8192 |
| G=4 | 16384 |

### 4.4 결과

Passkey 결과:

| 모델 | 조건 | 성공 | prompt tokens | 로그상 `n_ctx` | 설명 |
|---|---:|---:|---|---|---|
| Q4_K_M | off | 2/3 | 3907, 4387 | 4320 | 3907 tokens는 성공, 4387 tokens는 context overflow |
| Q4_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | 입력은 수용했지만 passkey 회수 실패 |
| Q4_K_M | G=4 | 0/2 | 7747 | 16608 | 입력은 수용했지만 `<unk>` 반복 |
| Q5_K_M | off | 2/3 | 3907, 4387 | 4320 | Q4와 동일한 패턴 |
| Q5_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | Q4와 동일하게 회수 실패 |
| Q5_K_M | G=4 | 0/2 | 7747 | 16608 | 출력 붕괴 |

해석하면 Self-Extend는 context 수용량을 약 2배 또는 4배로 늘렸다. 하지만 긴 입력을 받아도 passkey를 맞히지 못했다. Q5_K_M은 Q4_K_M보다 높은 양자화 품질이지만 결과를 개선하지 못했다.

PG-19 PPL 결과:

| 모델 | `-c` 값 | 실제 prompt tokens | PPL | prompt tok/s | 비고 |
|---|---:|---:|---:|---:|---|
| Q4_K_M | 2048 | 3072 | 7.8529 | 66.67 | 정상 범위 |
| Q5_K_M | 2048 | 3072 | 7.8592 | 85.13 | Q4와 거의 동일 |
| Q4_K_M | 4096 | 6144 | 304.6347 | 28.41 | train context 초과 경고 |
| Q5_K_M | 4096 | 6144 | 309.3053 | 33.22 | train context 초과 경고 |

`2048` 조건에서는 Q4와 Q5의 PPL 차이가 거의 없었다. `4096` 조건에서는 계산 chunk가 학습 context를 넘기며 경고가 발생했고 PPL이 급등했다. 이 결과는 Self-Extend 성능 저하라기보다는, group attention 없이 학습 context를 넘긴 영향으로 해석해야 한다.

코드 어시스턴스 benchmark 결과:

| 모델 | 조건 | 성공 | 실패/출력 패턴 |
|---|---:|---:|---|
| Q4_K_M | off | 0/3 | prompt too long |
| Q4_K_M | G=2 | 0/3 | `Љ` 반복 등 출력 붕괴 |
| Q4_K_M | G=4 | 0/3 | 빈 출력 |
| Q5_K_M | off | 0/3 | prompt too long |
| Q5_K_M | G=2 | 0/3 | `Љ`, 숫자/기호 반복 |
| Q5_K_M | G=4 | 0/3 | 빈 출력 |

off 조건은 약 4.8k tokens의 repo context를 처리하지 못했다. G=2/G=4 조건은 repo context를 받아들이기는 했지만 함수 정의, symbol reference, test failure 원인을 하나도 맞히지 못했다.

### 4.5 해석과 한계

이번 2차 실험의 핵심 결론은 다음과 같다.

```text
Self-Extend는 context overflow 회피 가능성은 보여줬다.
하지만 현재 환경에서는 long-context retrieval 품질을 보장하지 못했다.
```

한계는 다음과 같다.

- `llama-perplexity`가 `--grp-attn-n`을 지원하지 않아 PG-19에서 Self-Extend on/off PPL 비교를 하지 못했다.
- Homebrew llama.cpp의 group attention 구현이 논문 구현과 완전히 같다고 보장할 수 없다.
- `--grp-attn-w` 옵션은 체계적으로 sweep하지 않았다.
- Q8_0은 테스트하지 않았다.
- PG-19 PPL은 전체 test split이 아니라 앞 8권 샘플만 사용했다.
- 코드 benchmark는 synthetic repo 기반이다.
- 반복 횟수가 많지 않아 통계적으로 충분한 실험은 아니다.
- 출력 붕괴 원인이 모델, 양자화, 구현, 옵션, prompt 중 무엇인지 아직 분리하지 못했다.

### 4.6 적용 방향

현재 결과 기준으로 Self-Extend를 코드 어시스턴트의 기본 retrieval 방식으로 쓰는 것은 부적절하다. 대신 제한적인 fallback으로 두는 것이 현실적이다.

```text
사용자 요청
-> rg / symbol index / test log로 후보 파일 검색
-> 관련 함수, 클래스, 테스트 주변부를 작게 선별
-> 4k 이하이면 기본 attention으로 실행
-> 4k 초과이면 Self-Extend 후보 실행
-> 함수명, 파일명, 테스트명, 원인 line을 정확히 회수했는지 확인
-> 검증 통과 시 답변 또는 수정
-> 실패 시 더 작은 context로 다시 검색
```

코드 어시스턴트에서는 긴 context를 억지로 넣는 것보다 관련 context를 선별하는 일이 더 중요하다.

## 5. Source Pointer 실험

### 5.1 실험 목적

Source Pointer 실험은 disk에 이미 존재하는 큰 외부 데이터를 LLM context에 직접 넣지 않고, `source://...` pointer와 추출 tool만으로 필요한 정보를 얻을 수 있는지 확인한 실험이다.

예를 들어 큰 로그 파일 전체를 LLM에게 넣는 대신 다음 같은 pointer만 전달한다.

```text
source://log/logs/checkout_gateway.log
```

그 뒤 `grep_log` 같은 tool이 이 pointer가 가리키는 파일을 열고 필요한 줄만 추출한다.

Runtime pointer와 비슷하지만 대상이 다르다.

| pointer | 대상 |
|---|---|
| runtime pointer | 실행 중 생성된 임시 output |
| source pointer | disk에 이미 존재하는 외부 파일 |

### 5.2 실험 환경

| 항목 | 값 |
|---|---|
| Machine | M3 MacBook Pro |
| Backend | llama.cpp / Metal |
| LLM | Qwen2.5 Coder 7B Instruct GGUF Q5_K_M |
| Context size | 32768 |
| Generation limit | 128 |
| Temperature | 0 |
| Seed | 1 |

문법 검증은 다음 명령으로 수행했다.

```bash
uv run python -m compileall source_pointer_test
```

### 5.3 테스트 방식

비교한 방식은 세 가지이다.

| mode | 설명 |
|---|---|
| `full_source` | 외부 파일 전체를 prompt에 직접 넣는다. |
| `pointer_oracle` | 필요한 추출 tool call을 이미 알고 있다고 가정하고, tool이 뽑은 일부만 prompt에 넣는다. |
| `pointer_select` | LLM이 source catalog와 tool 설명을 보고 tool call을 선택한 뒤, 추출 결과로 답한다. |

테스트 데이터는 synthetic corpus로 만들었다.

| source | small | medium | 질문 |
|---|---:|---:|---|
| checkout gateway log | 80K | 596K | 특정 `request_id`의 `reason`, `retry_after_ms` 찾기 |
| operations runbook markdown | 12K | 56K | 특정 section의 `max_retries`, `jitter_percent` 찾기 |
| tenant snapshot JSON | 116K | 752K | 특정 tenant의 `source_pointer_enabled`, `max_context_policy` 찾기 |

사용한 추출 tool은 다음과 같다.

| tool | 역할 |
|---|---|
| `grep_log` | 긴 log에서 특정 패턴 주변 줄만 추출한다. |
| `extract_doc_section` | 긴 문서에서 질문과 가까운 section만 추출한다. |
| `extract_json_field` | 큰 JSON에서 필요한 field나 object만 추출한다. |

데이터 형식에 맞는 tool을 쓴 점이 중요하다. 로그는 주변 줄 검색이 자연스럽고, 문서는 section 추출이 자연스럽고, JSON은 key path 추출이 자연스럽다.

### 5.4 결과

Small 결과:

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 54.401 | 18,369 | 79,517.68 | |
| `pointer_oracle` | 3 | 1.000 | 2.472 | 286 | 866.69 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.430 | 778 | 2,370.58 | 1.000 |

Small에서 `full_source`는 log task에서 context overflow로 실패했다. JSON task는 context 안에 들어갔지만 관련 값이 아니라 distractor 값인 `pointer-preferred`를 답해 실패했다.

Medium 결과:

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 22.117 | 120,208 | 62,090.66 | |
| `pointer_oracle` | 3 | 1.000 | 2.443 | 286 | 871.16 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.423 | 780 | 2,355.91 | 1.000 |

Medium에서 `full_source`는 log와 JSON task에서 context overflow로 실패했다. 문서 task는 성공했지만 16,770 prompt tokens와 63.68초가 필요했다. 같은 질문을 `pointer_oracle`로 처리하면 217 prompt tokens와 2.12초로 끝났다.

Source pointer 방식은 데이터 크기가 커져도 prompt token 수가 거의 변하지 않았다.

| mode | small prompt tokens | medium prompt tokens |
|---|---:|---:|
| `pointer_oracle` | 286 | 286 |
| `pointer_select` | 778 | 780 |

### 5.5 해석과 한계

Source pointer 방식은 disk 외부 데이터 처리에 유효했다. 큰 외부 파일을 직접 넣는 방식은 overflow, 긴 prompt 평가 시간, distractor로 인한 오답 위험이 있었다. 반면 pointer와 추출 tool을 사용하면 필요한 부분만 LLM에게 전달할 수 있었다.

한계는 다음과 같다.

- 실험 데이터는 synthetic source corpus이다.
- 실제 환경에는 PDF, CSV, HTML, DB result, build log, test output처럼 더 다양한 형식이 있다.
- source 후보가 많아지면 selector가 어려워질 수 있다.
- LLM이 tool argument나 JSON path를 자유롭게 만들면 오류가 생길 수 있다.
- 외부 데이터를 읽은 뒤에는 관련 코드 symbol을 찾아 수정하는 단계가 추가로 필요하다.

### 5.6 적용 방향

코드 어시스턴트에서는 외부 자료를 raw context로 넣지 말고, 다음 흐름을 사용하는 것이 적합하다.

```text
사용자 요청
-> 필요한 외부 데이터 유형 판단
-> source pointer catalog 조회
-> 적절한 extraction tool 선택
-> 필요한 부분만 추출
-> symbol index로 관련 코드 후보 검색
-> 원인 분석 또는 코드 수정
```

예를 들어 운영 로그에서 결제 실패 원인을 찾는 경우에는 로그 전체가 아니라 `request_id` 주변 줄만 추출하고, 그 결과를 바탕으로 결제 처리 함수로 이동하는 구조가 좋다.

## 6. Symbol Bundle / Filtered Selector 2차 실험

### 6.1 실험 목적

Symbol 실험은 코드 전체를 LLM에게 넣지 않고, 필요한 함수나 클래스 단위만 골라 읽게 하는 방향의 실험이다.

여기서 `symbol`은 코드 안의 이름 붙은 단위이다. 예를 들어 함수, 클래스, 메서드, 상수 등이 symbol이다.

이전 방식에는 한계가 있었다.

```text
질문
-> 전체 symbol index를 LLM에 전달
-> 대표 symbol URI 1개 선택
-> 선택된 symbol 본문만 읽음
-> 답변
```

이 방식은 전체 index가 너무 크고, 선택된 함수 하나만으로는 답할 수 없는 문제가 있었다. 예를 들어 함수 안에서 상수를 참조하는데 상수 정의를 읽지 못하면 정확한 답을 할 수 없다.

2차 실험에서는 다음 구조를 추가했다.

```text
질문
-> 질문 기반으로 파일/symbol 후보를 먼저 줄임
-> 작은 후보 목록에서 대표 symbol URI 선택
-> 관련 상수, helper, callee, 질문에 명시된 관련 symbol까지 확장
-> symbol bundle을 LLM에 전달
-> 답변
```

### 6.2 실험 환경

| 항목 | 값 |
|---|---|
| 모델 | Qwen2.5 Coder 7B Instruct GGUF |
| Quantization | Q5_K_M |
| 실행 바이너리 | `llama-completion` |
| Backend | llama.cpp / GGML Metal backend |
| 하드웨어 | Apple M3 Pro MacBook Pro |
| 실행 옵션 | `--temp 0`, `--seed 1`, `--simple-io`, `-no-cnv`, `--no-warmup` |
| 2차 실험 ctx-size | 8192 |
| 2차 실험 n-predict | 64 |

문법 확인은 다음 명령으로 수행했다.

```bash
uv run python -m py_compile \
  symbol_test/symbol_bench/indexer.py \
  symbol_test/symbol_bench/run_benchmark.py
```

### 6.3 테스트 방식

기존 hard task 3개를 그대로 사용했다. 이 task들은 함수 하나만 읽어서는 답하기 어렵게 만들었다.

| task | 질문 의도 | 필요한 추가 context |
|---|---|---|
| `hard_auth_exact_exception_literal` | `validate_token`이 expired token에서 raise하는 정확한 문자열 확인 | `TOKEN_EXPIRED_MESSAGE` module-level constant |
| `hard_report_cache_key_composed_result` | `build_cache_key(" North/East Plan ", " TEAM-A ", 12)`의 최종 문자열 계산 | `sanitize_report_name` helper |
| `hard_billing_status_and_fee` | `invoice_status(4)`와 `compute_late_fee(4, 10000)` 결과 결합 | `invoice_status` 함수와 `InvoiceCalculator.compute_late_fee` method |

비교한 mode는 두 가지이다.

| mode | 설명 |
|---|---|
| `symbol_bundle_oracle` | 정답 target URI를 이미 알고 있다고 가정하고 바로 관련 bundle을 만든다. |
| `symbol_filtered_select_bundle` | 질문으로 후보 symbol을 줄인 뒤, LLM이 대표 URI를 고르고 관련 bundle을 만든다. |

2차 실험에서 추가된 주요 기능은 다음과 같다.

| 기능 | 설명 |
|---|---|
| `symbols_by_file` | 특정 파일에 속한 symbol만 조회한다. |
| `_module_assignments` | module-level constant/assignment를 수집한다. |
| `_ReferenceVisitor` | 선택된 symbol 내부에서 참조하는 이름과 호출 함수를 수집한다. |
| `expand_symbol_context` | primary symbol, 참조 상수, same-file helper/callee, 질문에 명시된 관련 symbol을 bundle로 구성한다. |
| `--tasks-file` | 기존 task 파일 대신 hard task 파일을 지정할 수 있다. |
| forbidden substring 검증 | 오답 패턴을 포함하면 실패로 처리한다. |

### 6.4 결과

요약 결과:

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms |
|---|---:|---:|---:|---:|---:|
| `symbol_bundle_oracle` | 3 | 0.333 | 2.298 | 369 | 1118.18 |
| `symbol_filtered_select_bundle` | 3 | 0.333 | 4.588 | 587 | 1835.71 |

Task별 결과:

| mode | task | selector 후보 수 | 선택 URI | bundle 내용 | 정답 여부 | 모델 답변 |
|---|---|---:|---|---|---:|---|
| `symbol_bundle_oracle` | `hard_auth_exact_exception_literal` | - | oracle | `validate_token` + `TOKEN_EXPIRED_MESSAGE` | 성공 | `TOKEN_EXPIRED` |
| `symbol_filtered_select_bundle` | `hard_auth_exact_exception_literal` | 6 | `validate_token` | `validate_token` + `TOKEN_EXPIRED_MESSAGE` | 성공 | `TOKEN_EXPIRED` |
| `symbol_bundle_oracle` | `hard_report_cache_key_composed_result` | - | oracle | `build_cache_key` + `sanitize_report_name` | 실패 | `report:team-a:north_east_plan:v12` |
| `symbol_filtered_select_bundle` | `hard_report_cache_key_composed_result` | 2 | `build_cache_key` | `build_cache_key` + `sanitize_report_name` | 실패 | `report:team-a:north_east_plan:v12` |
| `symbol_bundle_oracle` | `hard_billing_status_and_fee` | - | oracle | `compute_late_fee` + `invoice_status` 등 | 실패 | `status=late, fee=150` |
| `symbol_filtered_select_bundle` | `hard_billing_status_and_fee` | 4 | `compute_late_fee` | `compute_late_fee` + `invoice_status` 등 | 실패 | `status=late, fee=150` |

중요한 점은 retrieval 자체는 의도대로 동작했다는 것이다.

- 첫 번째 task에서는 단일 symbol 방식으로 놓치던 `TOKEN_EXPIRED_MESSAGE` 상수를 bundle에 포함했고 정답을 맞혔다.
- 두 번째 task에서는 필요한 `sanitize_report_name` helper가 bundle에 포함됐지만, 모델이 문자열 변환을 잘못 계산했다.
- 세 번째 task에서는 `invoice_status`와 `compute_late_fee`가 함께 포함됐지만, 모델이 산술 계산을 잘못했다.

즉 실패 원인은 context 부족보다는 LLM의 문자열 계산과 산술 추론 오류에 가까웠다.

이전 hard test와 비교하면 개선 폭은 컸다.

| mode | accuracy | mean wall s | mean prompt tokens | selection accuracy |
|---|---:|---:|---:|---:|
| 기존 `symbol_oracle` | 0.000 | 2.451 | 225 | - |
| 기존 `symbol_select` | 0.000 | 172.170 | 33,922 | 1.000 |
| `symbol_bundle_oracle` | 0.333 | 2.298 | 369 | - |
| `symbol_filtered_select_bundle` | 0.333 | 4.588 | 587 | 1.000 |

`symbol_filtered_select_bundle`은 기존 `symbol_select` 대비 prompt token을 약 98.3%, wall time을 약 97.3% 줄였다. selector 후보도 전체 638개 symbol에서 task별 2개에서 6개 symbol로 줄었다.

### 6.5 해석과 한계

Symbol bundle 방식은 전체 index를 매번 LLM에 넣는 비용을 크게 줄였다. 또한 단일 symbol만 읽던 구조의 한계를 일부 해결했다.

하지만 정확도는 아직 1/3이다. 필요한 코드가 bundle에 들어가도 LLM이 문자열 변환이나 산술 계산을 틀릴 수 있다.

한계는 다음과 같다.

- dependency 확장이 같은 파일 중심이다.
- 실제 repo에서는 import된 함수, 다른 파일의 class, config constant, type alias까지 따라가야 할 수 있다.
- 후보 필터링이 lexical heuristic 기반이다.
- 질문이 추상적이거나 파일명과 함수명이 드러나지 않으면 후보를 놓칠 수 있다.
- 실험 corpus는 synthetic Python corpus이다.
- 실제 repo에는 dynamic import, decorator, inheritance, re-export, framework convention 등이 있다.

### 6.6 적용 방향

코드 어시스턴트에는 다음 구조가 적합하다.

```text
사용자 질문 또는 코드 수정 요청
-> repo symbol index 로드 또는 생성
-> 현재 파일, 열린 파일, 에러 로그, 테스트 실패 위치, 질문 키워드로 후보 파일 필터링
-> 후보 파일의 compact symbol outline 구성
-> LLM 또는 deterministic matcher로 대표 symbol 선택
-> expand_symbol_context로 상수/helper/callee/import 관계 확장
-> bundle context를 근거로 답변, 수정 계획, 코드 패치 생성
-> 필요 시 테스트 실행 결과를 다시 retrieval query로 사용
```

앞으로는 cross-file dependency 확장, deterministic execution 보조, file retrieval 후 symbol retrieval로 이어지는 two-stage 구조, symbol signature와 docstring 압축, bundle ranking, cache, tree-sitter 기반 다중 언어 확장이 필요하다.

특히 구체적인 입력값을 계산하는 질문은 LLM에게 머릿속 계산을 맡기기보다 작은 evaluator나 AST 기반 interpreter를 같이 쓰는 편이 안정적이다.

## 7. 네 실험을 함께 보면 알 수 있는 점

네 실험은 서로 다른 문제처럼 보이지만 같은 결론으로 이어진다.

### 7.1 전체를 넣는 방식은 약하다

Source pointer와 runtime pointer 실험에서 전체 데이터 주입 방식은 모두 1/3만 성공했다. 실패 원인은 두 가지였다.

- context window를 초과해서 아예 실행되지 않았다.
- context 안에 들어가도 긴 내용 속 distractor 때문에 잘못 답했다.

### 7.2 pointer와 extraction tool은 효과적이다

Source pointer와 runtime pointer는 small/medium 모두 3/3 성공했다. 데이터가 커져도 prompt token 수가 거의 변하지 않았다.

이것은 pointer 방식의 장점이 단순한 token 절약이 아니라는 뜻이다. 더 중요한 장점은 데이터 크기와 LLM context 크기를 분리한다는 점이다.

```text
큰 데이터는 저장소나 파일에 둔다.
LLM에는 어디를 어떻게 읽을지에 대한 작은 정보만 준다.
필요한 부분만 tool이 가져온다.
```

### 7.3 context 길이 확장만으로는 충분하지 않다

Self-Extend는 입력 수용량을 늘렸지만 passkey와 코드 benchmark에서 정답 회수에 실패했다. 코드 어시스턴트에는 "길게 넣는 능력"보다 "관련 정보를 정확히 찾고 검증하는 능력"이 더 중요하다.

### 7.4 retrieval과 reasoning은 분리해야 한다

Symbol bundle 실험은 필요한 코드 조각을 찾는 데 성공했지만, 모델이 문자열 계산과 산술 계산을 틀렸다. 따라서 좋은 코드 어시스턴트에는 두 단계가 모두 필요하다.

1. 관련 정보를 정확히 찾는 retrieval 단계
2. 찾은 정보를 정확히 해석하거나 실행하는 reasoning 또는 deterministic tool 단계

## 8. 코드 어시스턴트에 적용하는 구조

네 실험을 합치면 다음 구조가 가장 현실적이다.

```text
사용자 요청
-> 요청 유형 판단
-> 외부 자료가 필요하면 source pointer로 증거 추출
-> 실행 결과가 필요하면 runtime pointer로 큰 output 관리
-> 코드 이해가 필요하면 symbol index와 symbol bundle 사용
-> 추출된 작은 증거 묶음을 LLM에게 전달
-> 계산형 질문은 deterministic tool로 검증
-> 답변 또는 코드 수정
-> 테스트 실행 결과를 다시 runtime pointer로 저장하고 반복
```

Pointer 종류는 다음처럼 나눌 수 있다.

| pointer type | 대상 | 예시 |
|---|---|---|
| code pointer | repo 내부 code span 또는 symbol | `memory://symbol/services/payment.py::authorize_payment` |
| source pointer | disk에 이미 존재하는 외부 자료 | `source://log/prod/checkout.log` |
| runtime pointer | 실행 중 생성된 큰 tool output | `runtime://log/run_tests/0001` |

이 구조의 목표는 LLM context를 전체 데이터 저장소로 쓰지 않는 것이다. LLM에게는 현재 reasoning에 필요한 작은 증거 묶음만 전달하고, 큰 데이터 접근은 tool과 pointer 계층이 담당한다.

## 9. 용어 설명

| 용어 | 쉬운 설명 |
|---|---|
| LLM | 많은 글을 학습해서 다음에 올 말을 예측하고 답을 만드는 언어 모델이다. ChatGPT 같은 시스템의 핵심 모델을 말한다. |
| prompt | LLM에게 입력으로 주는 글이다. 질문, 코드, 로그, tool 설명 등이 모두 prompt에 들어갈 수 있다. |
| context window | LLM이 한 번에 읽을 수 있는 최대 입력 길이이다. 이보다 길면 잘리거나 실행이 실패할 수 있다. |
| token | LLM이 글을 나눠서 읽는 작은 단위이다. 한글, 영어 단어, 기호 등이 여러 token으로 쪼개질 수 있다. |
| prompt token | prompt가 token으로 쪼개졌을 때의 개수이다. 많을수록 처리 비용과 시간이 늘어난다. |
| context overflow | 입력이 context window보다 길어서 모델이 처리하지 못하는 상황이다. |
| pointer | 큰 데이터 자체 대신 그 데이터의 위치를 가리키는 짧은 주소이다. |
| source pointer | disk에 이미 존재하는 파일을 가리키는 pointer이다. 예: `source://...` |
| runtime pointer | 실행 중 생긴 큰 tool output을 가리키는 pointer이다. 예: `runtime://...` |
| code pointer | 코드베이스 안의 특정 함수, 클래스, 코드 범위를 가리키는 pointer이다. 예: `memory://symbol/...` |
| RuntimeStore | 실행 중 생긴 큰 데이터를 임시로 저장하고 runtime pointer를 발급하는 저장소이다. |
| extraction tool | 큰 데이터에서 필요한 일부만 뽑아내는 도구이다. 예: 로그 grep, 문서 section 추출, JSON path 추출 |
| selector | 여러 후보 중 어떤 파일, pointer, symbol, tool을 쓸지 고르는 단계나 모델 호출이다. |
| oracle | 정답이 되는 선택을 이미 알고 있다고 가정하는 실험 조건이다. selector 자체의 어려움을 빼고 extraction이나 bundle의 효과를 보기 위해 사용한다. |
| symbol | 코드 안의 이름 붙은 단위이다. 함수, 클래스, 메서드, 상수 등이 symbol이다. |
| symbol index | 코드베이스에 어떤 symbol이 어디에 있는지 정리한 목록이다. |
| symbol bundle | 대표 symbol 하나뿐 아니라 관련 상수, helper 함수, 호출 함수 등을 함께 묶은 작은 코드 context이다. |
| Self-Extend | 모델의 attention 방식을 조정해 기본 context보다 더 긴 입력을 받도록 하는 기법이다. |
| group attention | Self-Extend 실행에 사용한 옵션 계열이다. 실험에서는 `G=2`, `G=4`처럼 표기했다. |
| PPL | Perplexity의 줄임말이다. 언어 모델이 텍스트를 얼마나 자연스럽게 예측하는지 보는 지표이다. 낮을수록 좋다. |
| PG-19 | 긴 문학 텍스트로 구성된 언어 모델 평가용 데이터셋이다. |
| quantization | 모델을 더 작고 빠르게 실행하기 위해 숫자 정밀도를 낮추는 방식이다. 실험에서는 `Q4_K_M`, `Q5_K_M`을 비교했다. |
| synthetic data | 실제 운영 데이터가 아니라 실험 목적에 맞게 인공적으로 만든 데이터이다. |
| wall time | 실제 실행에 걸린 시간이다. |
| prompt eval time | 모델이 입력 prompt를 읽고 처리하는 데 걸린 시간이다. |
| distractor | 정답과 비슷하지만 틀린 값이다. 긴 context 속에서 모델을 헷갈리게 만들 수 있다. |

