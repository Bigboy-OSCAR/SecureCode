# H 결합 방식 실험의 실행·검증 기록

이 폴더는 2026년 10월 27일에 실행한 **TF-IDF → 본문 없는 목록 → 원문 지정 → 답변** 실험의 증거를 보존한다. 질문·코드·기준 답은 기존 큰 파일 실험과 같다. 새 실행은 B·R0·H 세 방식이며, 다른 방식은 과거 실제 기록을 참조한다.

## 저장한 내용

| 파일 | 의미 |
|---|---|
| `protocol.json`, `source_snapshot/` | 본 평가 전 고정한 설정, 실행 소스, 이전 자료의 해시 |
| `tasks.json`, `dev_tasks.json`, `gold_operations.json` | 평가 질문 96개, 별도 연습 질문 8개, 기준 답 실행 규칙 |
| `projects/`, `assets.json` | 기존 큰 파일 프로젝트 및 원문·참조·검색 후보. 원본을 변경하지 않고 복사 |
| `symbol_metadata.json` | 함수·상수의 본문 없는 메타데이터. 질문별로 이 중 일부를 표시 |
| `analysis_plan.json` | 본 평가 전 저장한 비교·분석 코드의 해시 |
| `environment.json`, `session_*.json` | 모델·서버 지문과 실행 세션, 벡터 준비 시간 |
| `model_calls.jsonl` | 선택·답변·준비 응답을 포함한 실제 LLM 요청과 응답, 토큰·시간·종료 상태 |
| `results.jsonl`, `results_dev.jsonl` | 질문별 검색 순위, 목록, 요청한 원문, 실제 입력, 답변과 채점 |
| `completed_eval.json` | 실행이 정상 종료한 시점과 전체 결과 파일 해시 |
| `summary.json` | 사전에 정한 정답·토큰·시간·프로젝트 단위 비교 |
| `verification.json`, `offline_token_counts.json` | 원문·선택·토큰·채점·통계를 다시 계산한 검증 |
| `report_materials/`, `report_edits.json` | 보고서 추가 본문과 이전 문서로 되돌릴 수 있는 편집 목록 |
| `history/` | 수정 전 3번 보고서와 당시 보고서 관리 기록 |

## 현재 결과를 다시 검증하는 순서

아래 명령은 저장된 기록을 읽으며 **새 모델 답변을 생성하지 않는다.** 작업 위치는 `/Users/oscar/Desktop/SecureCode`이다. 집계를 다시 저장하면 그 해시가 바뀌므로 반드시 아래 순서로 검증과 보고서 생성을 마친다.

```sh
python3 -B 2nd/experiments/symbol_raptor/analyze_hybrid.py
python3 -B 2nd/experiments/symbol_raptor/verify_hybrid.py
python3 -B 2nd/experiments/symbol_raptor/diagnose_hybrid.py
python3 -B 2nd/experiments/symbol_raptor/report_raptor_large.py
python3 -B 2nd/experiments/symbol_raptor/audit_raptor_report.py
python3 -B 2nd/experiments/symbol_raptor/audit_hybrid_report.py
```

`verify_hybrid.py`는 모델 파일을 **토크나이저로만** 사용해 실제 입력 길이를 재계산한다. 기존 원문·그래프, TF-IDF, H 목록·선택·원문 조합, 기준 답, 통계를 별도로 대조한다. B의 후보 목록과 고정된 선택 지시문은 보존된 생성기와 일치하는지 확인한다. 이는 자체 재현성 검증이며 외부 검증을 의미하지 않는다.

`diagnose_hybrid.py`의 조건부 비용·실패 원인 분석은 **사후 기술 분석**이며, 사전에 고정한 전체 정답률·비용·통계를 대체하지 않는다. 선택에 성공한 질문들만 따로 보면 표본이 달라지므로 별도 성능 우위의 증거로 쓰지 않는다.

`summary.json`의 토큰 필드 `index`는 **H의 새 목록 본문**을 별도로 기록한 값이다. 다른 방식의 이 필드가 0인 것은 해당 목록 길이를 이 필드로 따로 기록하지 않았다는 뜻이다. B가 목록 없이 실행됐다는 뜻은 아니며, B의 목록·질문·지시문 비용은 `selector`와 `total`에 모두 포함된다.

## 새 추론을 다시 실행할 때

기존 결과 폴더를 지우거나 같은 행을 새 답변으로 교체하지 않는다. 새로운 실험 폴더와 소스 사본에서 `OUT`과 분석·보고서의 참조 경로를 정한 다음, 계획을 새로 고정하고 `prepare → dev → run`을 수행해야 한다. 이번 코드의 `prepare`는 이미 계획이 있는 폴더에서 덮어쓰기를 거부한다. 중단 후 같은 프로토콜로 이어 실행하는 기능은 있으나, 이번 실행의 완료 여부와 세션 수는 기록으로 확인한다.

사용한 로컬 서버는 Qwen2.5-Coder-7B-Instruct Q5_K_M, 컨텍스트 8,192, 동시 슬롯 1, 프롬프트 캐시 비활성 설정이다. 모델 경로·서버 실행 설정·바이너리 해시는 `environment.json`에 있다. 선택과 답변의 출력 한도는 각각 96·128이며, `temperature=0`, `seed=1`이다.

이 실험은 이미 관찰한 합성 질문을 재사용한다. 재현에 성공해도 새 저장소·한국어 질문·긴 함수에서 같은 성능을 보장하지 않는다. 보고서의 기존 A·파일 전체·RF·RH·C 수치는 과거 실행값이며, 새 B·R0·H와 같은 세션의 시간 비교로 사용하지 않는다.
