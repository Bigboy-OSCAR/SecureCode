# QASPER 단일 데이터셋 실험의 자료 출처

이 문서는 자료 선정과 입력의 출처를 기록한다. 답변 품질이나 성능 결과를 담지 않는다. 이번 범위는 **SCROLLS Qasper validation의 고유 질문 984개 전체 × A·B·R0·FULL = 3,936개 결과**다. 이전 일곱 데이터셋 실행과 구분되는 새 실험이며, LongBench 데이터셋을 평가하는 실험도 아니다.

## 1. 사용한 원본과 복사 이력

| 항목 | 고정 값 |
|---|---|
| 공식 배포 | Hugging Face `tau/scrolls` |
| 리비전 | `927b875150ac8f02262ddd3b078d33a9debc935b` |
| 압축 파일 | [고정 버전 qasper.zip](https://huggingface.co/datasets/tau/scrolls/resolve/927b875150ac8f02262ddd3b078d33a9debc935b/qasper.zip) |
| 사용한 ZIP 항목 | `qasper/validation.jsonl` |
| 압축 파일 크기 / SHA256 | 23,532,127바이트 / `16d6202820d052e642190f37b4ebdf3a22e177d64572265d8b8123fe3224c9b1` |
| 추출 JSONL 크기 / SHA256 | **40,536,579바이트** / **`00d622c3fba684d4580ae9a6b4efc338a15ee0e1a745beeda34dde3fd8382c52`** |
| 원본 행 / 고유 질문 / 원문 문맥 | **1,726 / 984 / 273** |
| 새 실험의 원본 위치 | [raw/qasper.jsonl](/Users/oscar/Desktop/SecureCode/2nd/Documents/test_results/evidence/qasper_benchmark_20261027/raw/qasper.jsonl) |
| 다운로드 출처 기록 | [downloads/qasper.json](/Users/oscar/Desktop/SecureCode/2nd/Documents/test_results/evidence/qasper_benchmark_20261027/downloads/qasper.json) |

원본 JSONL과 다운로드 출처 기록은 이전 `document_benchmarks_20261027` 자료에서 새 증거 폴더로 복사했다. **새 원본 파일의 바이트 수와 SHA256이 위 값과 일치함을 독립 확인했다.** 다운로드 기록의 `archive_fully_verified=true`는 최초 취득 때 전체 압축 파일의 SHA256 및 추출 항목의 ZIP CRC를 검증했다는 이력이다. 이번 복사 단계에서 압축 파일을 새로 다운로드하거나 그 전체를 다시 검증했다는 뜻은 아니다. 기존 추론 결과를 복사한 것으로 서술하면 안 된다.

형식과 분할은 [공식 데이터 카드](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/README.md)와 [공식 로더](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/scrolls.py)를 따른다. 공개 validation을 평가하며, 숨겨진 test 평가나 공식 리더보드 제출이 아니다.

## 2. 질문·원문·정답을 어떻게 구분하는가

원본의 `id`는 질문 식별자, `pid`는 입력·정답 쌍의 식별자다. `input`에는 질문 한 줄, `\n\n` 구분자, 논문 본문이 이어지고 `output`에는 참조 답안 하나가 있다. 같은 `id`의 여러 행은 같은 질문에 대한 여러 참조 답안이다.

전수 집계에서 같은 질문 ID의 입력 불일치는 0건이었다. 참조 답안 행이 1개인 질문은 257개, 2개는 712개, 3개는 15개다. 이들을 각각 한 번만 질의하되 **모든 참조 답안과 중복 개수를 보존**한다. 질문과 본문을 분리한 뒤 원래 구분자와 함께 합치면 원본 입력이 정확히 복원되어야 한다. 색인·참조 그래프는 본문만으로 만들며 질문·정답·사람이 표시한 근거 위치를 넣지 않는다.

273개 본문 모두 한 논문으로 준비된다. 각 질문의 FULL은 그 질문에 제공된 논문 본문 전부를 뜻한다. 273개 논문 전체를 한 호출에 보내는 방식이 아니다. A/B/R0는 논문 전체를 검색 대상으로 처리하되, 답변 LLM에는 실제 선택한 원문 조각만 보낸다.

## 3. 채점과 프롬프트 출처

QASPER 채점은 **정규화한 단어의 최대 참조 F1**이다. 소문자화, ASCII 구두점 제거, 영어 관사 제거, 공백 정리를 적용하고 단어 중복 개수까지 포함해 겹침을 센다. 질문별로 모든 참조 답안 중 가장 높은 F1을 택하고, 984개 질문의 산술평균에 100을 곱한다. 겹치는 단어가 없으면 0이다. F1을 완전히 맞힌 질문의 비율로 설명하면 안 된다. [공식 F1 구현](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/f1.py), [공식 지표 래퍼](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/scrolls.py)

답변 지시는 고정한 LongBench v1 저장소의 **Qasper용 프롬프트 문자열**을 활용한다. 저장소 리비전은 `2e00731f8d0bff23dc4325161044d0ed8af94c1e`이며 [프롬프트 원본](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LongBench/config/dataset2prompt.json)을 보존한다. **프롬프트 출처가 LongBench라는 것과 평가 자료가 LongBench Qasper라는 것은 다르다.** 실제 자료는 위 SCROLLS validation 전체이며, 128토큰 출력 상한·로컬 모델·검색 예산은 이번 실험의 고정 조건이다.

의존성의 실제 버전과 공식 평가 함수와의 일치 검사는 새 실험의 `requirements.lock`, `dependencies.json`, `metrics_verification.json`에 기록한다. 이전 환경을 공유하면 그 경로와 공유 사실을 명시하되, 이전 검사 기록만으로 수정된 새 코드를 검증했다고 주장하지 않는다. SCROLLS 저장소 코드의 MIT 라이선스를 논문 본문 등 모든 포함 자료의 라이선스로 확대 해석하지 않는다. Qasper 원자료는 [AllenAI 공식 자료 카드](https://huggingface.co/datasets/allenai/qasper)의 출처·라이선스를 함께 참고한다.
