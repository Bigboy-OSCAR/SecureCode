# 1차 테스트 종합 정리

졸업프로젝트 관련 교수님 면담에서 설명하기 쉽도록 4개 테스트를 같은 구조로 정리했다. 각 테스트는 진행방식, 결과, 한계, 발전 방향 순서로 구성했다.

참고한 원문:

- `runtime_pointer_test/runtime_pointer_test.md`
- `self_extend_test/self_extend_test.md`
- `source_pointer_test/source_pointer_test.md`
- `symbol_test/symbol_test.md`

## 1. Runtime Pointer Test

### 1.1 진행방식

Runtime Pointer Test는 실행 중 생성되는 큰 tool output을 LLM context에 직접 넣지 않고, `runtime://...` 형태의 pointer로 관리할 수 있는지 확인한 실험이다.

실험에서는 runtime producer가 큰 데이터를 생성한 뒤, 그 데이터를 `RuntimeStore`에 저장하고 짧은 runtime pointer만 LLM에게 전달했다. 이후 후속 tool이 pointer를 resolve해서 필요한 부분만 추출했다.

RuntimeStore는 이번 실험에서 만든 “실행 중 임시 메모리 저장소”이다.

쉽게 말하면, tool이 큰 결과를 만들었을 때 그 결과를 LLM context에 바로 넣지 않고, 프로그램 내부 메모리에 저장해 둔 뒤 짧은 pointer만 발급하는 객체이다.

-ex-
collect_checkout_trace()
-> 608KB짜리 로그 문자열 생성
-> RuntimeStore에 저장
-> runtime://log/collect_checkout_trace/0001 pointer 발급
-> LLM에는 전체 로그 대신 이 pointer만 전달


비교한 방식은 다음 세 가지다.

| 방식 | 설명 |
|---|---|
| `full_runtime` | runtime tool output 전체를 prompt에 직접 삽입 |
| `runtime_pointer_oracle` | 필요한 extraction tool call을 이미 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `runtime_pointer_select` | LLM이 runtime memory catalog와 tool spec을 보고 적절한 tool call을 선택한 뒤, 추출 결과로 답변 |

사용한 runtime 데이터는 checkout trace log, operations runbook markdown, tenant snapshot JSON/dict였다. 추출 도구는 `grep_runtime_log`, `extract_runtime_doc_section`, `extract_runtime_json_path`로 구성했다.

### 1.2 결과

핵심 결과는 runtime pointer 방식이 큰 runtime output을 직접 넣는 방식보다 정확도, token 사용량, 실행 시간에서 모두 유리했다는 점이다.

Small scale 결과:

| 방식 | 정확도 | 평균 prompt tokens | 평균 wall time |
|---|---:|---:|---:|
| `full_runtime` | 0.333 | 18,785 | 4.961s |
| `runtime_pointer_oracle` | 1.000 | 311 | 2.768s |
| `runtime_pointer_select` | 1.000 | 756 | 7.050s |

Medium scale 결과:

| 방식 | 정확도 | 평균 prompt tokens | 평균 wall time |
|---|---:|---:|---:|
| `full_runtime` | 0.333 | 131,136 | 26.270s |
| `runtime_pointer_oracle` | 1.000 | 311 | 2.610s |
| `runtime_pointer_select` | 1.000 | 757 | 6.891s |

`full_runtime`은 small과 medium 모두 log, JSON task에서 context overflow가 발생했다. 반면 pointer 방식은 데이터 크기가 small에서 medium으로 커져도 prompt token 수가 거의 변하지 않았고, 모든 task에서 정답을 맞혔다.

Medium 기준으로 `runtime_pointer_oracle`은 prompt 문자 수를 약 99.8%, wall time을 약 90.1% 줄였다. `runtime_pointer_select`도 prompt 문자 수를 약 99.5%, wall time을 약 73.8% 줄였다.

### 1.3 한계

이번 실험은 synthetic runtime output을 기준으로 진행했다. 실제 test log, build log, API response, static analysis report처럼 더 복잡한 output에서는 extractor 품질과 schema 안정성이 정확도에 직접 영향을 줄 수 있다.

`runtime_pointer_select`는 LLM 호출이 selector 호출과 최종 답변 호출로 2번 필요하다. 따라서 아주 작은 데이터에서는 oracle 방식보다 느릴 수 있다.

또한 JSON selector가 sibling field path를 comma 형태로 합치는 출력이 있었다. 이번 extractor는 이를 허용해서 정답을 맞혔지만, 실제 시스템에서는 tool call schema 검증과 path normalization이 필요하다.

현재 `RuntimeStore`는 process-local memory store 수준이다. 실제 agent 시스템에서는 session lifecycle, TTL, eviction, 권한 검사, 민감정보 처리, memory 상한 같은 운영 정책이 추가되어야 한다.

### 1.4 발전 방향

우선 실제 코드 어시스턴트에서 자주 생기는 runtime output으로 확장해야 한다. 예를 들어 test/build log, stack trace, large stdout/stderr, JSON API result, CSV/table output, diff/patch output을 대상으로 extraction tool을 늘릴 수 있다.

Selector 안정성도 보강해야 한다. tool별 JSON schema를 강제하고, pointer allowlist 검증, path normalization, 실패 시 broader extraction fallback을 넣는 방식이 필요하다.

실제 적용 구조는 다음과 같이 설계할 수 있다.

```text
tool 실행
-> output이 크면 RuntimeStore에 저장
-> LLM에는 runtime:// pointer와 짧은 catalog만 전달
-> mirrored extraction tool이 필요한 부분만 추출
-> symbol/source pointer와 결합해 원인 분석 또는 코드 수정
```

최종적으로는 code pointer, source pointer, runtime pointer를 함께 사용하는 구조가 가장 현실적이다.

## 2. Self-Extend Test

### 2.1 진행방식

Self-Extend Test는 긴 context를 처리하기 위한 Self-Extend 방식이 실제로 passkey retrieval 성능을 개선하는지 확인한 실험이다.

실험은 `llama.cpp`의 `llama-passkey` 예제를 사용했다. 의미 없는 긴 haystack 중간에 5자리 passkey를 넣고, 마지막에 해당 passkey를 물어보는 방식이다. 이번 실험의 passkey는 `16808`이었고, 모델 출력에 이 값이 포함되면 성공으로 판정했다.

비교한 조건은 다음과 같다.

| 조건 | 설명 |
|---|---|
| Self-Extend off | `--grp-attn-n` 미사용 |
| Self-Extend G=2 | `--grp-attn-n 2` 사용 |
| Self-Extend G=4 | `--grp-attn-n 4` 사용 |

입력 길이는 약 3907 tokens, 4387 tokens, 7747 tokens 수준으로 구성했고, passkey 위치는 각 길이의 10%, 50%, 90%로 바꿔가며 테스트했다. 모델은 Vicuna 7B v1.5 GGUF Q4_K_M을 사용했다.

### 2.2 결과

Self-Extend는 처리 가능한 context 길이는 늘렸지만, passkey retrieval 정확도는 개선하지 못했다.

| 조건 | 약 3907 tokens | 약 4387 tokens | 약 7747 tokens |
|---|---:|---:|---:|
| Self-Extend off | 3/3 성공 | 0/3 실패, context overflow | 미실행 |
| Self-Extend G=2 | 0/3 성공 | 0/3 성공 | 0/3 성공 |
| Self-Extend G=4 | 0/3 성공 | 0/3 성공 | 0/3 성공 |

컨텍스트 수용량 자체는 확장되었다.

| 조건 | 로그상 `n_ctx` | 의미 |
|---|---:|---|
| off | 4320 | 기본 4k 범위 |
| G=2 | 8416 | 약 2배 확장 |
| G=4 | 16608 | 약 4배 확장 |

하지만 G=2, G=4 조건에서는 4k 이내 입력에서도 passkey를 맞히지 못했고, 출력이 `green.`, `....`, `----`처럼 무너지는 현상이 있었다.

따라서 이번 환경에서는 Self-Extend가 "긴 입력을 받아들이는 능력"은 보여줬지만, "필요한 정보를 정확히 회수하는 능력"은 확인되지 않았다.

### 2.3 한계

이번 실험은 Homebrew로 설치된 `llama.cpp`의 `llama-passkey`와 `--grp-attn-n` 옵션을 사용했다. 논문 구현과 완전히 동일한 조건이 아닐 수 있다.

모델도 논문에서 주로 사용한 Llama-2-chat, Mistral, SOLAR 등이 아니라 Vicuna 7B v1.5 GGUF Q4_K_M이었다. instruction tuning 방식, quantization 수준, llama.cpp 버전, group attention 구현 차이가 결과에 영향을 줄 수 있다.

또한 passkey retrieval 하나만으로 Self-Extend 전체 성능을 판단하기는 어렵다. PPL, LongBench, L-Eval, 코드 어시스턴스 전용 retrieval task 같은 추가 평가가 필요하다.

### 2.4 발전 방향

우선 논문과 더 가까운 조건으로 재실험해야 한다. Llama-2-7B-chat GGUF, Q5_K_M 또는 Q8_0 quantization, 다른 llama.cpp 버전 또는 논문 구현을 사용해 비교할 필요가 있다.

Passkey 외에도 PG-19 PPL, LongBench류 task, 코드베이스 내부 symbol/reference retrieval task를 추가해야 한다. 코드 어시스턴스에 필요한 것은 단순히 긴 입력을 받는 능력이 아니라, 긴 context 안에서 특정 함수명, 파일 경로, import 관계, 테스트 실패 원인을 정확히 찾는 능력이기 때문이다.

실제 적용 시에는 Self-Extend를 기본 검색 대체재로 쓰기보다 fallback 옵션으로 두는 것이 적절하다.

```text
사용자 요청
-> rg/symbol index로 후보 파일 검색
-> 관련 chunk 선별
-> 4k 이하이면 Self-Extend off
-> 4k 초과이고 넓은 배경이 필요하면 Self-Extend on 후보 실행
-> retrieval sanity check
-> 답변 또는 코드 수정
```

현재 결과 기준으로는 Self-Extend를 프로덕션 기본값으로 켜기보다는, 실험적 옵션 또는 긴 배경 문맥이 필요한 fallback mode로 두는 것이 안전하다.

## 3. Source Pointer Test

### 3.1 진행방식

Source Pointer Test는 disk에 존재하는 큰 외부 데이터를 LLM context에 직접 넣지 않고, `source://...` 형태의 pointer와 extraction tool만으로 필요한 정보를 얻을 수 있는지 확인한 실험이다.

이 실험은 runtime 중 생성된 output이 아니라, 이미 disk에 존재하는 외부 source file을 대상으로 했다. 즉 runtime pointer와 목적은 비슷하지만, pointer가 가리키는 대상이 실행 중 memory object가 아니라 file system의 외부 자료라는 차이가 있다.

비교한 방식은 다음 세 가지다.

| 방식 | 설명 |
|---|---|
| `full_source` | 외부 파일 전체를 prompt에 직접 삽입 |
| `pointer_oracle` | 필요한 extraction tool call을 이미 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `pointer_select` | LLM이 source catalog와 tool spec을 보고 tool call을 선택한 뒤, 추출 결과로 답변 |

사용한 외부 데이터는 checkout gateway log, operations runbook markdown, tenant snapshot JSON이었다. 형식별 extraction tool로 `grep_log`, `extract_doc_section`, `extract_json_field`를 구현했다.

### 3.2 결과

Source pointer 방식은 전체 source를 직접 넣는 방식보다 정확하고 안정적이었다.

Small scale 결과:

| 방식 | 정확도 | 평균 prompt tokens | 평균 wall time |
|---|---:|---:|---:|
| `full_source` | 0.333 | 18,369 | 54.401s |
| `pointer_oracle` | 1.000 | 286 | 2.472s |
| `pointer_select` | 1.000 | 778 | 6.430s |

Medium scale 결과:

| 방식 | 정확도 | 평균 prompt tokens | 평균 wall time |
|---|---:|---:|---:|
| `full_source` | 0.333 | 120,208 | 22.117s |
| `pointer_oracle` | 1.000 | 286 | 2.443s |
| `pointer_select` | 1.000 | 780 | 6.423s |

Small에서 `full_source`는 log task에서 context overflow가 발생했고, JSON task는 context 안에 들어갔지만 distractor 값인 `pointer-preferred`를 답해 실패했다. 즉 전체 데이터를 넣는 방식은 context overflow뿐 아니라 긴 context 안에서 관련 위치를 놓치는 문제도 있었다.

Medium에서는 `full_source`가 log와 JSON task에서 context overflow로 실패했다. 반면 `pointer_oracle`과 `pointer_select`는 small, medium 모두 3개 task를 전부 맞혔다.

특히 pointer 방식은 source file 크기가 커져도 prompt token 수가 거의 변하지 않았다. 이는 source pointer의 핵심 장점이 단순 token 절약이 아니라, 외부 데이터 크기와 LLM context 크기를 분리하는 데 있음을 보여준다.

### 3.3 한계

현재 실험은 synthetic source corpus를 사용했다. 실제 환경의 log, PDF, CSV, HTML, DB result, build log, test output은 형식이 더 다양하고 불규칙할 수 있다.

`pointer_select`는 작은 catalog에서는 성공했지만, 후보 source가 많아지면 selector prompt가 커지고 tool 선택 난이도가 올라갈 수 있다.

또한 LLM이 자유 형식으로 path나 tool argument를 만들면 오류가 생길 수 있다. 실제 적용에서는 selector output schema 검증, path 보정, source kind별 tool 후보 제한이 필요하다.

외부 데이터를 읽는 것만으로 실제 코드 어시스턴스 문제가 끝나지 않는다는 점도 한계다. 외부 증거를 찾은 뒤 관련 코드 symbol을 찾고, 필요한 경우 runtime test output까지 연결해야 한다.

### 3.4 발전 방향

외부 데이터 형식을 확장해야 한다. 우선순위는 build/test/runtime log, markdown/text/PDF 추출 텍스트, JSON/API result, CSV/table, HTML section 등이다.

Selector 안정성을 높이기 위해 source kind별 tool 후보 제한, catalog hint 강화, JSON path 자동 보정, selector output schema 검증, 실패 시 broader extraction fallback을 추가할 수 있다.

코드 어시스턴스에 적용할 때는 source pointer를 symbol pointer, runtime pointer와 결합하는 구조가 적절하다.

```text
source pointer로 외부 증거 추출
-> symbol index로 관련 코드 후보 검색
-> read_symbol_bundle로 관련 함수와 helper 확장
-> LLM이 원인 분석 및 patch 생성
-> test 실행 결과도 runtime pointer로 재사용
```

이 구조를 사용하면 LLM이 전체 로그, 전체 문서, 전체 JSON을 직접 context에 들고 있지 않아도 된다. 필요한 시점에 필요한 부분만 tool로 추출하는 방식으로 context overflow와 긴 prompt eval 문제를 줄일 수 있다.

## 4. Symbol Index / Symbol Selector Test

### 4.1 진행방식

Symbol Test는 코드 전체를 LLM context에 넣는 방식과, symbol index를 만든 뒤 필요한 함수/클래스만 선택적으로 읽는 방식을 비교한 실험이다.

Python AST parser로 함수와 클래스의 이름, 시작줄, 끝줄을 추출하고, 각 symbol에 `memory://symbol/file.py::qualname` 형태의 URI를 부여했다. 이후 질문에 필요한 symbol만 읽어 prompt에 넣는 방식이 전체 repo를 넣는 방식보다 효율적인지 확인했다.

비교한 방식은 다음 다섯 가지다.

| 방식 | 설명 |
|---|---|
| `full_repo` | 모든 Python 파일 내용을 한 번에 prompt에 삽입 |
| `full_file` | 정답이 들어 있는 파일 하나를 통째로 prompt에 삽입 |
| `line_span` | 타깃 함수/메서드의 줄 범위만 prompt에 삽입 |
| `symbol_oracle` | 타깃 symbol URI를 이미 알고 있다고 가정하고 해당 본문만 읽음 |
| `symbol_select` | LLM이 symbol index JSON을 보고 필요한 symbol URI를 선택한 뒤 본문을 읽음 |

### 4.2 결과

쉬운 질문과 medium 기본 질문에서는 symbol 단위 접근이 매우 효율적이었다.

Small의 간단한 테스트 결과:

| 방식 | 정확도 | wall time | prompt tokens |
|---|---:|---:|---:|
| `full_repo` | 1.00 | 14.200s | 4098 |
| `full_file` | 1.00 | 2.089s | 317 |
| `line_span` | 1.00 | 2.110s | 217 |
| `symbol_oracle` | 1.00 | 2.109s | 214 |
| `symbol_select` | 1.00 | 11.304s | 2709 |

Medium 기본 테스트에서는 `full_repo`가 65k context에서 실패했고, 131k context로 재측정한 한 케이스도 약 612.869초가 걸렸다. 반면 `symbol_oracle`은 3개 질문 모두 평균 약 2.131초에 처리했다.

Medium 기본 테스트 결과:

| 방식 | 정확도 | 평균 wall time | 평균 prompt tokens |
|---|---:|---:|---:|
| `full_repo` | 1.000 | 612.869s | 67,188 |
| `full_file` | 1.000 | 2.286s | 256 |
| `line_span` | 1.000 | 2.120s | 199 |
| `symbol_oracle` | 1.000 | 2.131s | 199 |
| `symbol_select` | 1.000 | 181.191s | 33,871 |

하지만 hard test에서는 단일 symbol만 읽는 방식의 한계가 드러났다.

Hard test 결과:

| 방식 | 정확도 | 평균 wall time | 평균 prompt tokens | selection accuracy |
|---|---:|---:|---:|---:|
| `full_repo` | 0.000 | 1.087s | 52,313 | |
| `full_file` | 0.333 | 2.604s | 281 | |
| `line_span` | 0.000 | 2.461s | 224 | |
| `symbol_oracle` | 0.000 | 2.451s | 225 | |
| `symbol_select` | 0.000 | 172.170s | 33,922 | 1.000 |

`symbol_select`는 hard test에서도 대표 symbol URI는 정확히 골랐다. 그러나 선택된 단일 symbol 안에 상수, helper 함수, 관련 함수가 모두 들어 있지 않아 최종 답변은 실패했다.

즉 symbol 단위 접근은 빠르고 효과적이지만, 실제 코드 이해 질문에서는 단일 함수 본문만으로 부족한 경우가 많다는 점을 확인했다.

### 4.3 한계

현재 `symbol_select`는 전체 symbol index를 LLM에게 그대로 전달한다. Medium corpus에서도 symbol이 638개였고, selector prompt가 커져 평균 181초 이상이 걸렸다. 실제 코드베이스에서는 이 방식이 더 비효율적일 수 있다.

또한 기존 쉬운 질문들은 단일 symbol 안에서 바로 답을 찾을 수 있는 형태였다. 그래서 `line_span`과 `symbol_oracle`이 높은 정확도를 보였지만, hard test처럼 상수, helper 함수, 다른 method를 함께 봐야 하는 질문에서는 실패했다.

현재 구조는 `read_symbol` 하나만 읽는다. 실제 코드 이해와 수정에는 선택된 symbol 주변의 module-level constant, callee/helper, caller, 같은 파일의 관련 함수, 질문에 직접 언급된 추가 symbol이 필요할 수 있다.

마지막으로 이번 구현은 Python AST parser 기반이다. 다른 언어에 적용하려면 JavaScript/TypeScript, Java, C/C++ 등에 맞는 parser 또는 tree-sitter 기반 indexer가 필요하다.

### 4.4 발전 방향

가장 중요한 발전 방향은 selector 입력을 줄이는 것이다. 전체 symbol index를 LLM에 전달하지 말고, 먼저 파일/디렉터리 단위로 후보를 줄인 뒤 관련 symbol만 selector에 전달해야 한다.

가능한 구조는 다음과 같다.

```text
질문
-> rg 또는 file outline으로 관련 파일 후보 선택
-> 해당 파일의 symbol 후보만 추림
-> LLM selector가 대표 symbol 선택
-> expand_symbol_context가 helper/constant/callee를 확장
-> 필요한 bundle만 LLM에 전달
```

`read_symbol_bundle` 또는 `expand_symbol_context`도 필요하다. 선택된 symbol 본문뿐 아니라 내부에서 참조하는 helper 함수, module-level constant, 같은 파일의 callee, 질문에 언급된 관련 symbol을 함께 묶어 반환하는 방식이다.

예를 들어 `build_cache_key`만 읽으면 `sanitize_report_name`의 동작을 알 수 없지만, bundle에 helper 함수까지 포함하면 최종 cache key를 정확히 계산할 수 있다.

추가로 symbol index 압축, selector 결과 캐싱, 질문 기반 keyword matching, import 관계 활용, tree-sitter 기반 다중 언어 확장을 진행하면 실제 코드 에이전트에서 사용할 수 있는 구조로 발전시킬 수 있다.

## 전체 결론

네 가지 테스트는 모두 같은 문제의식을 공유한다. LLM context에 모든 데이터를 직접 넣는 방식은 context overflow, 긴 prompt eval, distractor로 인한 오답, 긴 latency 문제가 있다.

각 테스트의 결론은 다음과 같이 정리할 수 있다.

| 테스트 | 핵심 결론 |
|---|---|
| Runtime Pointer | 큰 tool output은 `runtime://` pointer로 저장하고 필요한 부분만 추출하는 방식이 효과적이다. |
| Self-Extend | context 수용량은 늘릴 수 있었지만, 이번 환경에서는 retrieval 정확도 개선이 확인되지 않았다. |
| Source Pointer | 큰 외부 파일은 `source://` pointer와 형식별 extraction tool로 접근하는 방식이 효과적이다. |
| Symbol Index / Selector | 필요한 code symbol만 읽는 방식은 빠르지만, 실제 문제에는 symbol bundle 확장이 필요하다. |

졸업프로젝트 방향으로는 Self-Extend처럼 context window 자체를 무리하게 늘리는 접근보다, pointer 기반 접근과 symbol/source/runtime extraction을 결합해 LLM에게 필요한 증거만 작게 전달하는 구조가 더 실현 가능성이 높다.
