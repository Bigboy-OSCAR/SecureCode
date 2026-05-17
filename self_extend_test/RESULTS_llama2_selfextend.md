# Llama-2-7B-chat Self-Extend 재실험 결과

## 실행 조건

- 모델: `TheBloke/Llama-2-7B-Chat-GGUF`
- 양자화: `Q4_K_M`, `Q5_K_M`
- 로컬 모델 경로:
  - `/Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q4_K_M.gguf`
  - `/Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb/llama-2-7b-chat.Q5_K_M.gguf`
- llama.cpp tools:
  - `llama-passkey`: `--grp-attn-n` 지원
  - `llama-completion`: `--grp-attn-n`, `--grp-attn-w` 지원
  - `llama-perplexity`: `--grp-attn-n` 미지원
- PG-19: DeepMind 공식 `deepmind-gutenberg/test` split 100개 파일 다운로드
  - 참고: https://github.com/google-deepmind/pg19

## 추가한 파일

| 파일 | 설명 |
|---|---|
| `self_extend_test/llama2_selfextend_common.py` | 모델 경로, 결과 디렉터리, 공통 파서 |
| `self_extend_test/download_pg19_test.py` | PG-19 test split 다운로드 및 PPL 샘플 생성 |
| `self_extend_test/run_llama2_selfextend_passkey.py` | Llama-2 Q4/Q5 passkey Self-Extend 실험 |
| `self_extend_test/run_pg19_ppl.py` | PG-19 PPL 실험 |
| `self_extend_test/run_code_assistance_bench.py` | 긴 repo context 코드 어시스턴스 벤치마크 |

## 실행 명령

```bash
uv run python -m self_extend_test.download_pg19_test --max-books 8 --max-chars-per-book 12000
uv run python -m self_extend_test.run_llama2_selfextend_passkey
uv run python -m self_extend_test.run_pg19_ppl --ctx-sizes 2048 4096 --chunks 1 --timeout 1800
uv run python -m self_extend_test.run_code_assistance_bench \
  --models q4_k_m q5_k_m \
  --groups 1 2 4 \
  --noise-files 5 \
  --noise-functions 8 \
  --timeout 420 \
  --out-prefix llama2_code_assistance
```

## Passkey 결과

| 모델 | 조건 | 성공 | prompt tokens | 로그상 n_ctx | 해석 |
|---|---:|---:|---|---|---|
| Q4_K_M | off | 2/3 | 3907, 4387 | 4320 | 3907 tokens는 성공, 4387 tokens는 context overflow |
| Q4_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | 입력은 수용하지만 passkey retrieval 실패 |
| Q4_K_M | G=4 | 0/2 | 7747 | 16608 | 입력은 수용하지만 `<unk>` 반복 |
| Q5_K_M | off | 2/3 | 3907, 4387 | 4320 | 3907 tokens는 성공, 4387 tokens는 context overflow |
| Q5_K_M | G=2 | 0/6 | 3907, 4387, 7747 | 8416 | Q4와 같은 retrieval 실패 |
| Q5_K_M | G=4 | 0/2 | 7747 | 16608 | Q4와 같은 출력 붕괴 |

Q5_K_M으로 양자화 품질을 올려도 passkey retrieval은 회복되지 않았다. 이번 환경에서는 Self-Extend가 처리 가능한 context 길이는 늘렸지만, 답을 회수하는 능력은 오히려 무너졌다.

Raw results:

- `self_extend_test/results/llama2_selfextend_passkey.json`
- `self_extend_test/results/llama2_selfextend_passkey.csv`
- `self_extend_test/results/llama2_passkey_logs/`

## PG-19 PPL 결과

`llama-perplexity`는 현재 설치된 Homebrew 빌드에서 `--grp-attn-n`을 받지 않는다. 따라서 PPL은 Self-Extend on/off 비교가 아니라, 같은 Llama-2-7B-chat Q4/Q5에서 PG-19 test split 샘플을 사용한 baseline PPL로 기록했다.

| 모델 | `-c` 값 | 실제 prompt tokens | PPL | prompt tok/s | 비고 |
|---|---:|---:|---:|---:|---|
| Q4_K_M | 2048 | 3072 | 7.8529 | 66.67 | 정상 범위 |
| Q5_K_M | 2048 | 3072 | 7.8592 | 85.13 | Q4와 거의 동일 |
| Q4_K_M | 4096 | 6144 | 304.6347 | 28.41 | train context 초과 경고 |
| Q5_K_M | 4096 | 6144 | 309.3053 | 33.22 | train context 초과 경고 |

4096 조건은 `perplexity_v2`가 6144-token 계산 chunk를 만들며 `model was trained on only 4096 context tokens` 경고를 냈다. 이 조건의 높은 PPL은 Self-Extend 품질이 아니라, `llama-perplexity`에서 group attention 없이 train context를 넘긴 영향으로 해석해야 한다.

Raw results:

- `self_extend_test/results/llama2_pg19_ppl.json`
- `self_extend_test/results/llama2_pg19_ppl.csv`
- `self_extend_test/results/pg19_ppl_logs/`
- `self_extend_test/work/pg19_test/`
- `self_extend_test/work/pg19_test_sample.txt`

## 코드 어시스턴스 벤치마크 결과

벤치마크 구성:

- 긴 repo context 안에 실제 target 함수와 유사 shadow 함수들을 섞음
- 태스크 3개:
  - 특정 함수 정의 값 회수
  - 특정 symbol reference 식별
  - failing test의 root cause 식별
- 실제 prompt tokens: 약 4843-4855
- group별 context:
  - off: 4096
  - G=2: 8192
  - G=4: 16384

| 모델 | 조건 | 성공 | 실패/출력 패턴 |
|---|---:|---:|---|
| Q4_K_M | off | 0/3 | prompt too long |
| Q4_K_M | G=2 | 0/3 | `Љ` 반복 등 출력 붕괴 |
| Q4_K_M | G=4 | 0/3 | 빈 출력 |
| Q5_K_M | off | 0/3 | prompt too long |
| Q5_K_M | G=2 | 0/3 | `Љ`, 숫자/기호 반복 |
| Q5_K_M | G=4 | 0/3 | 빈 출력 |

코드 어시스턴스 전용 benchmark에서도 passkey와 같은 패턴이 재현되었다. Self-Extend는 repo context를 넣을 수 있게 만들지만, 함수 정의, symbol reference, 테스트 실패 원인을 정확히 찾아내지 못했다.

Raw results:

- `self_extend_test/results/llama2_code_assistance.json`
- `self_extend_test/results/llama2_code_assistance.csv`
- `self_extend_test/results/code_assistance_logs/`
- `self_extend_test/work/code_assistant_repo/`

## 결론

1. 논문 조건에 더 가까운 Llama-2-7B-chat GGUF로 바꿔도 이전 Vicuna 실험과 같은 실패 양상이 유지됐다.
2. Q4_K_M에서 Q5_K_M으로 올려도 긴 context retrieval 품질은 개선되지 않았다.
3. PG-19 PPL은 추가했지만, 현재 `llama-perplexity`는 Self-Extend 옵션을 지원하지 않아 baseline PPL만 측정 가능했다.
4. 코드 어시스턴스 benchmark에서는 4k 초과 repo context를 수용하는 것과 정확한 코드 이해가 분리된 문제임이 확인됐다.
5. 현재 Homebrew llama.cpp의 group attention 옵션 조합은 코드 어시스턴스 기본값으로 쓰기 어렵다. 다음 실험은 논문 구현 또는 `llama-perplexity`/일반 completion에서 group attention이 일관되게 동작하는 llama.cpp 빌드를 직접 빌드해 비교해야 한다.
