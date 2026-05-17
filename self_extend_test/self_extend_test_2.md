# llama.cpp Self-Extend 2차 실험 보고서

## 1. CLI를 통한 테스트 실행 방법

이번 2차 실험은 이전 `Vicuna-7B-v1.5 Q4_K_M` 실험의 후속 실험이다. 이전 실험에서는 passkey retrieval만 수행했고, Self-Extend를 켰을 때 긴 입력은 수용되지만 정답 회수는 실패했다. 이번에는 모델을 논문 조건에 더 가까운 `Llama-2-7B-chat`으로 바꾸고, `Q4_K_M`과 `Q5_K_M` 양자화를 비교했으며, passkey 외에 PG-19 PPL과 코드 어시스턴스 전용 benchmark를 추가했다.

PG-19 test split 다운로드 및 샘플 생성:

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode

uv run python -m self_extend_test.download_pg19_test \
  --max-books 8 \
  --max-chars-per-book 12000
```

Llama-2-7B-chat passkey Self-Extend 실험:

```bash
uv run python -m self_extend_test.run_llama2_selfextend_passkey
```

PG-19 PPL 실험:

```bash
uv run python -m self_extend_test.run_pg19_ppl \
  --ctx-sizes 2048 4096 \
  --chunks 1 \
  --timeout 1800
```

코드 어시스턴스 전용 benchmark:

```bash
uv run python -m self_extend_test.run_code_assistance_bench \
  --models q4_k_m q5_k_m \
  --groups 1 2 4 \
  --noise-files 5 \
  --noise-functions 8 \
  --timeout 420 \
  --out-prefix llama2_code_assistance
```

개별 CLI 예시는 다음과 같다.

Self-Extend off:

```bash
llama-passkey \
  -m /Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q4_K_M.gguf \
  --junk 160 \
  --pos 80 \
  --keep 32 \
  --predict 64 \
  --temp 0 \
  --seed 1
```

Self-Extend on:

```bash
llama-passkey \
  -m /Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q5_K_M.gguf \
  --junk 320 \
  --pos 160 \
  --keep 32 \
  --grp-attn-n 2 \
  --predict 64 \
  --temp 0 \
  --seed 1
```

## 2. 사용한 LLM 모델 및 환경

사용한 모델은 `TheBloke/Llama-2-7B-Chat-GGUF`이다.

| 항목 | 값 |
|---|---|
| base model | `Llama-2-7B-chat` |
| GGUF repo | `TheBloke/Llama-2-7B-Chat-GGUF` |
| quantization | `Q4_K_M`, `Q5_K_M` |
| architecture | `llama` |
| train context length | `4096` |
| RoPE freq base | `10000.0` |

로컬 모델 경로:

```text
/Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q4_K_M.gguf
/Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q5_K_M.gguf
```

실행 환경:

| 항목 | 값 |
|---|---|
| workspace | `/Users/oscar/Desktop/4th_grade/SecureCode` |
| 주요 CLI | `llama-passkey`, `llama-completion`, `llama-perplexity`, `llama-tokenize` |
| backend | Homebrew llama.cpp, Metal/CPU |
| GPU 로그 | Apple M3 Pro, unified memory |
| sampling | `--temp 0`, `--seed 1` |

도구별 Self-Extend 옵션 지원 여부:

| 도구 | Self-Extend 관련 옵션 |
|---|---|
| `llama-passkey` | `--grp-attn-n` 지원 |
| `llama-completion` | `--grp-attn-n`, `--grp-attn-w` 지원 |
| `llama-perplexity` | `--grp-attn-n` 미지원 |

`Q8_0`도 후보였지만, 이번 실험에서는 요구 조건 중 하나인 `Q5_K_M`을 선택했다. 이유는 `Q5_K_M`만으로도 Q4 대비 양자화 영향을 확인할 수 있고, 로컬 환경에서 다운로드 및 실행 시간이 현실적인 범위였기 때문이다.

## 3. 이전 실험과 비교했을 때 달라진 점

이전 실험은 `Vicuna-7B-v1.5 Q4_K_M`으로 `llama-passkey`만 실행했다. 이번 실험은 다음 점이 달라졌다.

| 항목 | 이전 실험 | 2차 실험 |
|---|---|---|
| 모델 | `Vicuna-7B-v1.5 Q4_K_M` | `Llama-2-7B-chat Q4_K_M`, `Q5_K_M` |
| 논문 조건과의 유사성 | Vicuna는 Llama 2 기반이지만 instruction tuning이 다름 | 논문 조건에 더 가까운 Llama-2-chat |
| 양자화 비교 | Q4만 사용 | Q4와 Q5 비교 |
| passkey retrieval | 있음 | 있음 |
| PG-19 PPL | 없음 | 추가 |
| 코드 어시스턴스 benchmark | 없음 | 추가 |
| 평가 관점 | 긴 입력 수용 및 passkey 회수 | 긴 입력 수용, PPL, 코드 symbol 회수, test failure 원인 회수 |

이전 실험의 핵심 결과는 Self-Extend가 context 수용량은 늘렸지만 passkey retrieval은 실패했다는 것이다. 2차 실험에서도 이 패턴은 유지되었다. 즉, 모델을 Llama-2-7B-chat으로 바꾸고 Q5_K_M으로 양자화 품질을 올려도 현재 llama.cpp 옵션 조합에서는 retrieval 품질이 회복되지 않았다.

## 4. 실행한 실험들에 대한 설명

### 4.1 Passkey Retrieval

`llama-passkey`는 긴 무의미 텍스트 중간에 5자리 passkey를 삽입하고, 마지막에 해당 passkey를 묻는 synthetic long-context retrieval 테스트다.

실험 변수:

| 변수 | 값 |
|---|---|
| 모델 | `Q4_K_M`, `Q5_K_M` |
| group attention | off, `G=2`, `G=4` |
| 입력 길이 | `junk=160`, `180`, `320` |
| passkey 위치 | 중간, 후반 위주 |
| 정답 판정 | stdout에 passkey `16808` 포함 여부 |

입력 길이별 의미:

| 설정 | prompt tokens | 의미 |
|---|---:|---|
| `junk=160` | 약 3907 | 4k 근처, 기본 context로 처리 가능 |
| `junk=180` | 약 4387 | 기본 4k 초과 |
| `junk=320` | 약 7747 | 확장 context 필요 |

### 4.2 PG-19 PPL

PG-19는 긴 문학 텍스트 기반 language modeling benchmark다. 이번 실험에서는 DeepMind 공식 `deepmind-gutenberg/test` split 100개 파일을 다운로드했고, 빠른 재현을 위해 앞 8권에서 각 12000자씩 잘라 `pg19_test_sample.txt`를 만들었다.

`llama-perplexity`는 현재 설치된 Homebrew 빌드에서 `--grp-attn-n`을 지원하지 않았다. 따라서 PG-19 PPL은 Self-Extend on/off 비교가 아니라, 같은 Llama-2-7B-chat의 Q4/Q5 baseline PPL 측정으로 진행했다.

실험 변수:

| 변수 | 값 |
|---|---|
| 모델 | `Q4_K_M`, `Q5_K_M` |
| data | `self_extend_test/work/pg19_test_sample.txt` |
| ctx size | `2048`, `4096` |
| chunks | `1` |
| 실행 backend | `--device none -ngl 0` CPU 실행 |

CPU 실행을 사용한 이유는 Metal backend에서 `llama-perplexity`가 command queue 초기화 오류를 낸 적이 있었기 때문이다. 안정적인 측정을 위해 PPL은 CPU로 고정했다.

### 4.3 코드 어시스턴스 전용 Benchmark

코드 어시스턴스 benchmark는 긴 repo context 안에서 필요한 코드 사실을 정확히 회수하는지 확인하기 위해 만들었다.

벤치마크 repo에는 다음 요소가 들어간다.

- 실제 target 함수: `derive_rotation_marker`
- 실제 호출 함수: `schedule_rotation`
- 실패하는 테스트: `test_rotation_marker_keeps_zero_padding`
- 원인 함수: `derive_rotation_marker_buggy`
- distractor noise 파일: `derive_rotation_marker_shadow_*` 등 유사 함수 다수

태스크는 3개다.

| task | 질문 | 기대 정답 |
|---|---|---|
| `function_definition` | `derive_rotation_marker("apac", 7)`의 반환값 | `ROTATE::APAC::0007` |
| `symbol_reference` | `derive_rotation_marker`를 호출하는 함수명 | `schedule_rotation` |
| `test_failure_cause` | failing test의 원인 | `.lstrip("0")` 때문에 zero padding 제거 |

실제 prompt token 수는 `llama-completion` 로그 기준 약 4843-4855 tokens였다. group별 context 설정은 다음과 같다.

| 조건 | context size |
|---|---:|
| off | 4096 |
| G=2 | 8192 |
| G=4 | 16384 |

## 5. 테스트를 진행하는데 필요한 각 파일들에 대한 설명

| 파일 | 설명 |
|---|---|
| `self_extend_test/self_extend_test.md` | 1차 Vicuna passkey 실험 보고서 |
| `self_extend_test/RESULTS_llama2_selfextend.md` | 2차 실험의 간단 결과 요약 |
| `self_extend_test/self_extend_test_2.md` | 현재 보고서 |
| `self_extend_test/llama2_selfextend_common.py` | Llama-2 모델 경로, 결과 디렉터리, JSON/CSV 저장, perf 파서 등 공통 유틸 |
| `self_extend_test/download_pg19_test.py` | DeepMind PG-19 test split 100개 파일 다운로드 및 샘플 생성 |
| `self_extend_test/run_llama2_selfextend_passkey.py` | Llama-2 Q4/Q5 passkey Self-Extend 실험 배치 실행 |
| `self_extend_test/run_pg19_ppl.py` | PG-19 PPL 실험 실행 및 결과 파싱 |
| `self_extend_test/run_code_assistance_bench.py` | synthetic repo 생성, 긴 코드 context 구성, 코드 이해 태스크 실행 |
| `self_extend_test/results/llama2_selfextend_passkey.json` | passkey raw result JSON |
| `self_extend_test/results/llama2_selfextend_passkey.csv` | passkey 결과 CSV |
| `self_extend_test/results/llama2_passkey_logs/` | passkey 개별 실행 로그 |
| `self_extend_test/results/llama2_pg19_ppl.json` | PG-19 PPL raw result JSON |
| `self_extend_test/results/llama2_pg19_ppl.csv` | PG-19 PPL 결과 CSV |
| `self_extend_test/results/pg19_ppl_logs/` | PPL 개별 실행 로그 |
| `self_extend_test/results/llama2_code_assistance.json` | 코드 어시스턴스 raw result JSON |
| `self_extend_test/results/llama2_code_assistance.csv` | 코드 어시스턴스 결과 CSV |
| `self_extend_test/results/code_assistance_logs/` | 코드 어시스턴스 개별 실행 로그 |
| `self_extend_test/work/pg19_test/` | 다운로드한 PG-19 test split 100개 텍스트 파일 |
| `self_extend_test/work/pg19_test_sample.txt` | PPL 실험용 PG-19 샘플 |
| `self_extend_test/work/code_assistant_repo/` | 코드 어시스턴스 benchmark용 synthetic repo |

## 6. 테스트 결과 및 결과에 대한 설명

### 6.1 Passkey 결과

| 모델 | 조건 | 성공 | prompt tokens | 로그상 `n_ctx` | 설명 |
|---|---:|---:|---|---|---|
| Q4_K_M | off | 2/3 | 3907, 4387 | 4320 | 3907 tokens는 성공, 4387 tokens는 context overflow |
| Q4_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | 입력은 수용했지만 passkey 회수 실패 |
| Q4_K_M | G=4 | 0/2 | 7747 | 16608 | 입력은 수용했지만 `<unk>` 반복 |
| Q5_K_M | off | 2/3 | 3907, 4387 | 4320 | Q4와 동일한 패턴 |
| Q5_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | Q4와 동일하게 회수 실패 |
| Q5_K_M | G=4 | 0/2 | 7747 | 16608 | 출력 붕괴 |

해석:

1. 기본 attention은 4k 이내 passkey retrieval을 성공했다.
2. 기본 attention은 4k 초과에서 `context_slot_overflow`로 실패했다.
3. Self-Extend는 `n_ctx`를 약 2배 또는 4배로 늘렸다.
4. 하지만 긴 입력을 받아도 passkey를 맞히지 못했다.
5. Q5_K_M은 Q4_K_M보다 높은 양자화 품질이지만 결과를 개선하지 못했다.

따라서 현재 환경에서는 Self-Extend가 "context window overflow 회피"에는 효과가 있지만, "필요 정보 회수"에는 효과가 없었다.

### 6.2 PG-19 PPL 결과

| 모델 | `-c` 값 | 실제 prompt tokens | PPL | prompt tok/s | 비고 |
|---|---:|---:|---:|---:|---|
| Q4_K_M | 2048 | 3072 | 7.8529 | 66.67 | 정상 범위 |
| Q5_K_M | 2048 | 3072 | 7.8592 | 85.13 | Q4와 거의 동일 |
| Q4_K_M | 4096 | 6144 | 304.6347 | 28.41 | train context 초과 경고 |
| Q5_K_M | 4096 | 6144 | 309.3053 | 33.22 | train context 초과 경고 |

`2048` 조건에서는 Q4와 Q5의 PPL 차이가 거의 없었다. `4096` 조건에서는 `perplexity_v2`가 6144-token 계산 chunk를 만들며 `model was trained on only 4096 context tokens` 경고가 발생했다. 이 조건의 PPL 급등은 Self-Extend 성능 저하라기보다는, `llama-perplexity`에서 group attention 없이 학습 context를 넘긴 영향으로 해석해야 한다.

중요한 제한은 `llama-perplexity`가 `--grp-attn-n`을 지원하지 않는다는 점이다. 따라서 이번 PPL 결과는 Self-Extend PPL 결과가 아니라 PG-19 baseline PPL 결과다.

### 6.3 코드 어시스턴스 Benchmark 결과

| 모델 | 조건 | 성공 | 실패/출력 패턴 |
|---|---:|---:|---|
| Q4_K_M | off | 0/3 | prompt too long |
| Q4_K_M | G=2 | 0/3 | `Љ` 반복 등 출력 붕괴 |
| Q4_K_M | G=4 | 0/3 | 빈 출력 |
| Q5_K_M | off | 0/3 | prompt too long |
| Q5_K_M | G=2 | 0/3 | `Љ`, 숫자/기호 반복 |
| Q5_K_M | G=4 | 0/3 | 빈 출력 |

해석:

1. off 조건은 약 4.8k tokens의 repo context를 처리하지 못했다.
2. G=2/G=4 조건은 repo context를 수용했다.
3. 그러나 함수 정의, symbol reference, test failure 원인을 하나도 맞히지 못했다.
4. passkey 실험에서 보인 출력 붕괴가 코드 benchmark에서도 재현되었다.

즉, Self-Extend는 코드 어시스턴스에서 필요한 "긴 repo context 안의 정확한 정보 회수"를 보장하지 못했다.

## 7. 코드 어시스턴스에 적용시킬 방법

현재 결과 기준으로 Self-Extend를 코드 어시스턴스의 기본 retrieval 방식으로 쓰는 것은 부적절하다. 다만 완전히 배제하기보다는 제한적인 fallback 또는 보조 기능으로는 사용할 수 있다.

현실적인 적용 구조는 다음과 같다.

```text
사용자 요청
  -> rg / symbol index / test log 기반 후보 파일 검색
  -> 관련 함수, 클래스, 테스트 주변부를 chunk로 선별
  -> 4k 이하이면 기본 attention으로 실행
  -> 4k 초과이면 Self-Extend 후보 실행
  -> retrieval sanity check
     - 함수명 정확히 회수?
     - 파일 경로 정확히 회수?
     - 테스트 이름 정확히 회수?
     - 원인 line 또는 symbol 정확히 회수?
  -> sanity check 통과 시 답변 또는 수정
  -> 실패 시 RAG 범위를 줄이거나 symbol oracle 방식으로 재시도
```

적용 원칙:

1. Self-Extend를 검색 대체재로 쓰지 않는다.
2. 기본은 `rg`, symbol index, 파일 단위 ranking, test log 기반 narrowing을 사용한다.
3. Self-Extend는 넓은 배경 context를 넣어보는 실험적 fallback으로만 둔다.
4. 코드 수정 전에는 반드시 retrieval 검증 질문을 먼저 던진다.
5. 모델이 함수명, 파일명, 테스트명, 원인 expression을 정확히 회수하지 못하면 수정 단계로 넘어가지 않는다.

이번 코드 benchmark 결과에서 G=2/G=4가 입력은 받았지만 답을 못 했기 때문에, 프로덕션 코드 어시스턴스에서는 "길이 확장"보다 "관련 context 선별"이 더 중요하다.

## 8. 한계점

이번 실험의 한계는 다음과 같다.

1. `llama-perplexity`가 `--grp-attn-n`을 지원하지 않아 PG-19에서 Self-Extend on/off PPL 비교를 하지 못했다.
2. Homebrew llama.cpp 빌드의 group attention 구현이 논문 구현과 완전히 같다고 보장할 수 없다.
3. `--grp-attn-w` neighbor window 계열 옵션은 체계적으로 sweep하지 않았다.
4. Q8_0은 테스트하지 않았고, Q4_K_M과 Q5_K_M만 비교했다.
5. PG-19는 test split 전체를 다운로드했지만, PPL 실행은 시간 문제로 앞 8권 샘플만 사용했다.
6. 코드 어시스턴스 benchmark는 synthetic repo 기반이므로 실제 대규모 코드베이스의 import graph, build system, test fixture 복잡도를 완전히 반영하지 않는다.
7. passkey와 코드 benchmark는 seed 1 중심의 빠른 matrix로 실행했기 때문에 통계적으로 충분한 반복 실험은 아니다.
8. Llama-2-7B-chat 자체가 최신 코드 모델이 아니므로 코드 어시스턴스 성능을 일반화하기 어렵다.
9. 출력 붕괴 원인이 모델, 양자화, llama.cpp 구현, 옵션 조합, prompt 형식 중 어느 요소인지 아직 분리하지 못했다.

## 9. 앞으로 발전시킬 방향 및 실현 가능성

다음 실험 방향은 명확하다.

1. 논문 구현 또는 Self-Extend 옵션이 더 일관되게 노출된 llama.cpp 버전을 직접 빌드한다.
2. `llama-perplexity`에서도 group attention을 적용할 수 있는 빌드로 PG-19 PPL on/off 비교를 다시 한다.
3. `--grp-attn-n`뿐 아니라 `--grp-attn-w`를 함께 sweep한다.
4. Q8_0 또는 F16에 가까운 양자화로 긴 context attention 품질이 회복되는지 확인한다.
5. passkey 실험은 seed, passkey 위치, 길이를 늘려 통계적으로 반복한다.
6. 코드 benchmark는 synthetic repo 외에 실제 오픈소스 repo의 test failure, symbol reference, 함수 정의 탐색 task로 확장한다.
7. Self-Extend, RoPE scaling, YaRN, context shifting을 같은 데이터셋에서 비교한다.
8. 코드 어시스턴스 관점에서는 full repo 주입보다 symbol index, source pointer, runtime pointer 방식과 결합해 비교한다.

실현 가능성은 중간 정도다.

긍정적인 점은 context 수용량 확장 자체는 이미 확인되었다는 것이다. `llama-passkey` 로그에서 G=2는 `n_ctx=8416`, G=4는 `n_ctx=16608`까지 확장되었다. 따라서 기술적으로 긴 prompt를 넣는 것은 가능하다.

부정적인 점은 정확도다. passkey와 코드 benchmark 모두에서 필요한 정보를 회수하지 못했다. 코드 어시스턴스에서는 틀린 함수명이나 잘못된 원인 분석이 바로 잘못된 코드 수정으로 이어질 수 있으므로, 현재 결과만으로는 기본값으로 적용하기 어렵다.

최종 판단은 다음과 같다.

```text
Self-Extend = context overflow 회피 가능성은 있음
Self-Extend = long-context retrieval 품질은 현재 환경에서 미검증 또는 실패
코드 어시스턴스 적용 = 기본값 부적합, 실험적 fallback으로만 가능
다음 단계 = 논문 구현 또는 직접 빌드한 llama.cpp에서 PG-19 PPL + 코드 benchmark 재측정
```

