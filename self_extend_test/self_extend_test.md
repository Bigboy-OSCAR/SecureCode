# llama.cpp Self-Extend 테스트 보고서

## 1. CLI를 통한 테스트 실행 방법

이번 테스트는 `llama.cpp`의 `llama-passkey` 예제를 사용했다. `llama-cli`에는 현재 설치된 Homebrew 빌드 기준으로 `--grp-attn-n` 옵션이 노출되지 않았고, `llama-passkey`에는 Self-Extend에 해당하는 group attention 옵션이 제공되었다.

Self-Extend off 실행 예시는 다음과 같다.

```bash
llama-passkey \
  -m /Users/oscar/.cache/huggingface/hub/models--TheBloke--vicuna-7B-v1.5-GGUF/snapshots/8b4a138d6ba32660c42b5df6dad7ad5c23b80c8c/vicuna-7b-v1.5.Q4_K_M.gguf \
  --junk 160 \
  --pos 80 \
  --keep 32 \
  --predict 64 \
  --temp 0 \
  --seed 1
```

Self-Extend on 실행 예시는 다음과 같다.

```bash
llama-passkey \
  -m /Users/oscar/.cache/huggingface/hub/models--TheBloke--vicuna-7B-v1.5-GGUF/snapshots/8b4a138d6ba32660c42b5df6dad7ad5c23b80c8c/vicuna-7b-v1.5.Q4_K_M.gguf \
  --junk 180 \
  --pos 90 \
  --keep 32 \
  --grp-attn-n 2 \
  --predict 64 \
  --temp 0 \
  --seed 1
```

전체 실험 배치는 다음 명령으로 실행했다.

```bash
uv run python selfextend_test/run_vicuna_selfextend_passkey.py
```

최초 모델은 Hugging Face에서 `TheBloke/vicuna-7B-v1.5-GGUF:Q4_K_M`를 받아 사용했다. 다운로드 이후 실제 로컬 경로의 GGUF 파일을 직접 지정했다.

## 2. 테스트를 진행한 방식

참고 논문 `Documents/6_Self-Extend.pdf`는 Self-Extend를 PPL, passkey retrieval, LongBench/L-Eval로 평가한다. 로컬에서 가장 직접 재현 가능한 항목은 synthetic long-context retrieval인 passkey retrieval이므로, `llama.cpp`의 `llama-passkey` 예제를 사용했다.

테스트 모델은 4k RoPE 기반 조건에 맞추기 위해 Vicuna 7B v1.5 GGUF를 사용했다. 실행 로그에서 확인된 주요 메타데이터는 다음과 같다.

| 항목 | 값 |
|---|---:|
| architecture | `llama` |
| base name | `LLaMA v2` |
| context length | `4096` |
| RoPE freq base | `10000.0` |
| quantization | `Q4_K_M` |

`llama-passkey`는 의미 없는 haystack 텍스트 중간에 5자리 passkey를 삽입하고, 마지막에 해당 passkey를 물어본다. 이번 테스트에서는 passkey `16808`이 생성되었고, 모델 출력에 이 숫자가 포함되면 성공으로 판정했다.

실험 변수는 다음과 같이 구성했다.

| 변수 | 값 |
|---|---|
| Self-Extend off | `--grp-attn-n` 미사용, group = 1 |
| Self-Extend on | `--grp-attn-n 2`, `--grp-attn-n 4` |
| 입력 길이 | `--junk 160`, `180`, `320` |
| passkey 위치 | 각 길이의 10%, 50%, 90% |
| sampling | `--temp 0`, `--seed 1` |

`junk=160`은 약 3907 prompt tokens로 4k 근처이지만 실행 가능했다. `junk=180`은 약 4387 prompt tokens로 기본 4k 컨텍스트를 초과한다. `junk=320`은 약 7747 prompt tokens로 확장 컨텍스트가 필요한 조건이다.

## 3. 실행 방식 및 파일 설명

준비한 테스트 파일은 다음과 같다.

| 파일 | 설명 |
|---|---|
| `selfextend_test/run_vicuna_selfextend_passkey.py` | 실험 배치 실행 스크립트. off/G=2/G=4 조건과 길이/위치를 순회하며 `llama-passkey`를 호출한다. |
| `selfextend_test/results/vicuna_selfextend_passkey_results.csv` | 전체 실험 결과 CSV. 조건, 성공 여부, prompt token 수, context 크기, 속도, 실패 사유를 저장한다. |
| `selfextend_test/results/vicuna_selfextend_passkey_results.json` | 동일 결과의 JSON 버전. 후속 분석 자동화에 사용하기 쉽다. |
| `selfextend_test/results/*.log` | 각 개별 실행의 stdout/stderr 원본 로그. 모델 메타데이터, context 크기, 출력 토큰, perf 로그가 포함된다. |

스크립트는 `subprocess.run()`으로 각 CLI 명령을 실행한다. `stdout`은 모델 생성 결과, `stderr`는 llama.cpp 진행 로그와 성능 로그로 분리해서 저장했다. passkey 정답 여부는 `stdout`에 `16808`이 포함되는지로 판정했다.

초기 파싱에서는 stdout/stderr를 단순히 이어 붙여 순서가 깨지는 문제가 있었다. 이후 스크립트를 수정하여 모델 답변은 stdout 기준으로만 파싱하도록 변경했다.

## 4. 테스트 결과

요약 결과는 다음과 같다.

| 조건 | 약 3907 tokens (`junk=160`) | 약 4387 tokens (`junk=180`) | 약 7747 tokens (`junk=320`) |
|---|---:|---:|---:|
| Self-Extend off | 3/3 성공 | 0/3 실패, context overflow | 미실행 |
| Self-Extend G=2 | 0/3 성공 | 0/3 성공 | 0/3 성공 |
| Self-Extend G=4 | 0/3 성공 | 0/3 성공 | 0/3 성공 |

컨텍스트 수용량은 확장되었다.

| 조건 | 로그상 `n_ctx` | 의미 |
|---|---:|---|
| off | 4320 | 4k 모델의 기본 실행 가능 범위 |
| G=2 | 8416 | 약 2배 확장 |
| G=4 | 16608 | 약 4배 확장 |

속도는 다음과 같이 측정되었다.

| 조건 | 입력 길이 | 평균 prompt eval 속도 |
|---|---:|---:|
| off | 3907 tokens | 342.66 tok/s |
| G=2 | 3907 tokens | 331.02 tok/s |
| G=2 | 7747 tokens | 304.63 tok/s |
| G=4 | 3907 tokens | 340.33 tok/s |
| G=4 | 7747 tokens | 302.95 tok/s |

핵심 결론은 다음과 같다.

1. Self-Extend off는 4k 이내에서 passkey retrieval을 성공했다.
2. Self-Extend off는 4k 초과 입력에서 `context_slot_overflow`로 실패했다.
3. Self-Extend on은 4k 초과 입력을 처리할 수는 있었다.
4. 그러나 Self-Extend on은 passkey를 맞히지 못했다.
5. 특히 G=2/G=4 조건에서는 4k 이내 입력에서도 출력이 `green.`, `....`, `----`처럼 무너졌다.

따라서 이번 환경에서는 Self-Extend가 "처리 가능한 컨텍스트 길이"는 확장했지만, "retrieval 정확도"나 코드 어시스턴스에 필요한 실질 성능은 개선하지 못했다.

## 5. 코드 어시스턴스에 적용시킬 방법

코드 어시스턴스에서 Self-Extend를 적용하려면 단순히 컨텍스트 크기를 늘리는 기능으로만 보면 안 된다. 이번 결과처럼 긴 입력을 받아들이는 것과 필요한 정보를 정확히 회수하는 것은 별개의 문제다.

적용 가능한 형태는 다음과 같다.

1. 긴 코드베이스를 한 번에 넣어야 하는 경우, Self-Extend를 "fallback mode"로만 사용한다.
2. 기본 모드는 기존 RAG, symbol index, 파일 단위 검색, chunk ranking을 유지한다.
3. 검색으로 추린 관련 파일이나 함수 주변부만 일반 컨텍스트에 넣고, Self-Extend는 넓은 배경 문맥을 보조로 넣는 방식이 적합하다.
4. 코드 변경 전에는 반드시 retrieval 검증 단계를 둔다. 예를 들어 특정 함수명, 파일 경로, import 관계, 테스트 이름을 모델이 정확히 회수하는지 확인한다.
5. Self-Extend on/off를 자동 전환한다. 짧은 입력에서는 off가 더 안정적일 수 있으므로, 입력이 4k 이하일 때는 기본 attention을 유지하는 편이 낫다.

실제 코드 어시스턴스 파이프라인에 넣는다면 다음 구조가 현실적이다.

```text
사용자 요청
  -> rg/symbol index로 후보 파일 검색
  -> 관련 chunk 선별
  -> 4k 이하이면 Self-Extend off
  -> 4k 초과이고 넓은 배경이 필요하면 Self-Extend on 후보 실행
  -> retrieval sanity check
  -> 답변/수정/테스트 실행
```

중요한 점은 Self-Extend를 "검색 대체재"로 쓰면 위험하다는 것이다. 이번 passkey 실험에서도 긴 입력을 처리하긴 했지만 핵심 값을 회수하지 못했다. 코드 어시스턴스에서는 잘못된 함수명이나 파일 경로 하나가 바로 잘못된 수정으로 이어질 수 있으므로, Self-Extend는 보조적인 컨텍스트 확장 옵션으로만 쓰는 것이 적절하다.

## 6. 앞으로 발전시킬 방향 및 실현 가능성

이번 결과만으로 Self-Extend 자체가 효과 없다고 결론내리기는 어렵다. 논문은 Llama-2-chat, Mistral, SOLAR 등 여러 모델에서 실험했고, 구현도 attention 내부를 직접 수정하는 방식이다. 반면 이번 테스트는 Homebrew llama.cpp의 `llama-passkey`에 포함된 `--grp-attn-n` 옵션만 사용했다. 모델, 양자화, llama.cpp 버전, 옵션 구현 차이가 결과에 영향을 줄 수 있다.

발전 방향은 다음과 같다.

1. 논문과 같은 Llama-2-7B-chat GGUF로 재실험한다. Vicuna v1.5는 Llama 2 기반이지만 instruction tuning과 quantization 영향이 다를 수 있다.
2. Q4_K_M 외에 Q5_K_M 또는 Q8_0 모델로 테스트한다. 긴 컨텍스트에서 attention 품질이 양자화에 민감할 수 있다.
3. `--grp-attn-n`뿐 아니라 neighbor window에 대응하는 옵션이 있는 llama.cpp 버전 또는 논문 구현을 직접 빌드해 비교한다.
4. passkey 외에 PG-19 PPL 테스트를 추가한다. 이 경우 `llama-perplexity`와 PG-19 test split이 필요하다.
5. 코드 어시스턴스 전용 벤치마크를 만든다. 예를 들어 긴 repo context 안에 특정 함수 정의, symbol reference, 테스트 실패 원인을 숨기고 정확히 찾아내는지 측정한다.
6. Self-Extend on/off, RoPE scaling, YaRN, context shifting을 같은 데이터셋에서 비교한다.

실현 가능성은 중간 정도다. 컨텍스트 수용량 확장은 이미 CLI에서 확인되었으므로 기술적으로는 적용 가능하다. 하지만 정확도 개선은 아직 확인되지 않았다. 코드 어시스턴스에 실제 적용하려면 "길이 확장"이 아니라 "필요 정보 회수율"을 기준으로 다시 평가해야 한다. 현재 결과 기준으로는 프로덕션 기본값으로 켜기보다는 실험적 옵션 또는 fallback 옵션으로 두는 것이 안전하다.

