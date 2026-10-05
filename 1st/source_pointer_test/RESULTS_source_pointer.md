# Source Pointer Benchmark Results

실행일: 2026-05-10

## 목적

`Documents/1_Solving Context Window Overflow in AI Agents.pdf`의 runtime pointer 방식은 큰 tool output을 raw text로 LLM context에 넣지 않고, memory pointer를 다음 mirrored tool에 넘긴다. 이 실험은 같은 아이디어를 disk에 이미 존재하는 외부 source file에도 적용할 수 있는지 확인했다.

참고 문서의 요구사항에 맞춰 source pointer는 하나의 범용 하위 pointer 체계로 만들지 않고, 데이터 형식에 맞는 최소 extraction tool로 검증했다.

- log: `grep_log(source://log/..., pattern, before, after)`
- document: `extract_doc_section(source://doc/..., query)`
- JSON: `extract_json_field(source://json/..., path)`

## 비교 모드

| mode | 설명 |
|---|---|
| `full_source` | 외부 파일 전체를 LLM prompt에 직접 삽입 |
| `pointer_oracle` | 필요한 tool call을 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `pointer_select` | LLM이 작은 source catalog와 tool spec만 보고 tool call을 선택한 뒤, tool output으로 답변 |

## 데이터와 질문

Synthetic disk source corpus를 생성했다.

| source | small | medium | 질문 |
|---|---:|---:|---|
| checkout gateway log | 80K | 596K | 특정 `request_id`의 `reason`, `retry_after_ms` |
| operations runbook markdown | 12K | 56K | 특정 section의 `max_retries`, `jitter_percent` |
| tenant snapshot JSON | 116K | 752K | 특정 tenant의 `source_pointer_enabled`, `max_context_policy` |

## 실행 명령

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale small \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out source_pointer_test/work/small_final_results.jsonl
```

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale medium \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out source_pointer_test/work/medium_final_results.jsonl
```

## Small 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 54.401 | 18,369 | 79,517.68 | |
| `pointer_oracle` | 3 | 1.000 | 2.472 | 286 | 866.69 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.430 | 778 | 2,370.58 | 1.000 |

`full_source` 세부 결과:

| task | result |
|---|---|
| log | context 초과 실패: 35,923 tokens > 32,764 max |
| doc | 성공: 2,626 prompt tokens, 9.18s |
| JSON | 실행은 됐지만 오답: 32,616 prompt tokens, 152.94s |

Small에서 pointer 방식은 전체 파일 주입 대비 prompt 크기를 크게 줄였다.

- `pointer_oracle`: 평균 prompt token 18,369 -> 286
- `pointer_select`: 평균 prompt token 18,369 -> 778

## Medium 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 22.117 | 120,208 | 62,090.66 | |
| `pointer_oracle` | 3 | 1.000 | 2.443 | 286 | 871.16 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.423 | 780 | 2,355.91 | 1.000 |

`full_source` 세부 결과:

| task | result |
|---|---|
| log | context 초과 실패: 275,609 tokens > 32,764 max |
| doc | 성공: 16,770 prompt tokens, 63.68s |
| JSON | context 초과 실패: 216,172 tokens > 32,764 max |

Medium에서는 전체 주입이 3개 중 2개에서 불가능했다. 반면 `pointer_oracle`과 `pointer_select`는 모두 3/3 성공했고, prompt token은 파일 크기와 거의 무관하게 286~780 수준으로 유지됐다.

## 해석

1. 큰 외부 데이터를 LLM context에 직접 넣지 않아도 되는가?

가능하다. log, document, JSON 모두 `source://...` pointer와 format-specific extraction tool만으로 정답을 만들 수 있었다. Medium log/JSON처럼 full source가 context window를 초과하는 경우에도 pointer 방식은 정상 실행됐다.

2. pointer만 넘기고 tool이 필요한 부분만 추출하면 성능이 유지되거나 좋아지는가?

이번 실험에서는 좋아졌다. `pointer_oracle`은 3개 task 모두 정확도를 유지하면서 평균 wall time이 약 2.4초였다. `pointer_select`는 selector 호출이 추가되어 약 6.4초였지만, full source의 성공 케이스인 medium document 63.68초와 비교해도 훨씬 작았다.

3. runtime pointer 논문을 source pointer에 그대로 적용할 수 있는가?

핵심 구조는 적용 가능하다. 다만 runtime memory store 대신 disk source resolver가 필요하고, raw value를 그대로 넘기는 mirrored tool보다는 파일 형식별 extraction tool이 중요하다. 즉 source pointer의 핵심은 pointer 자체가 아니라 `pointer resolve -> 필요한 부분 추출 -> 작은 context로 답변` 흐름이다.

## 한계

- Synthetic corpus 기준 결과다. 실제 PDF, HTML, CSV 등은 별도 extractor 품질이 정확도에 직접 영향을 준다.
- `pointer_select`는 selector prompt와 tool의 인자 허용 범위에 민감했다. JSON selector가 sibling field를 한 path에 합치는 출력이 나와서, extractor가 comma-separated sibling field를 처리하도록 보강했다.
- `full_source`의 overflow 케이스는 실제 prompt eval 시간이 아니라 실패까지의 wall time만 측정된다. 따라서 full-source 평균 wall time은 실제 비용을 과소평가한다.

## 결론

Source pointer 방식은 disk 외부 데이터 처리에도 유효하다. 큰 파일을 LLM context에 직접 넣는 방식은 context overflow, 긴 prompt eval, 긴 context 안의 distractor로 인한 오답 위험이 있었다. 반면 `source://...` pointer와 최소 extraction tool 조합은 정확도를 유지하면서 prompt token과 실행 시간을 크게 줄였다.

