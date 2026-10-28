# 논문과 공식 구현을 대조한 문서 벤치마크 실험 근거

확인일: 2026-10-27. 현재 비교 대상은 **A, B, R0, FULL**이다. 이 문서는 연구 자료이며 실험 결과는 아니다. 다운로드 버전·스키마·공식 평가 함수는 [research_sources.md](research_sources.md)에 정리되어 있다.

## 1. RAPTOR 논문에서 실제로 검증한 범위

1차 문헌: Sarthi et al., **RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval**, ICLR 2024. [학회 페이지](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html), [최종 논문](https://proceedings.iclr.cc/paper_files/paper/2024/file/8a2acd174940dbca361a6398a4f9df91-Paper-Conference.pdf).

| 확인 항목 | 최종 논문에서 확인한 내용 | 위치 |
|---|---|---|
| 데이터셋 | NarrativeQA, QASPER, QuALITY **3종**. QMSum·HotpotQA·MuSiQue·MultiFieldQA-en은 해당 실험에 없다. | §4, p.6 |
| 원문 분할 | 약 100토큰, 문장 경계를 고려한다. | §3, p.3 |
| 트리 생성 | SBERT `multi-qa-mpnet-base-cos-v1` 임베딩 → UMAP → GMM 소프트 군집 → GPT-3.5-turbo 요약 → 반복. | §3, pp.3–4 |
| 검색 | 모든 층의 원문·요약 노드에서 질문 임베딩과 코사인 유사도로 선택하는 collapsed-tree. | §3, pp.5–6 |
| 검색 예산 | 일반 2,000토큰; UnifiedQA는 400토큰. 비교 검색기에도 같은 예산. | p.6 |
| 탐색 방식 결정 | QASPER의 20문서 실험으로 비교. 이것을 전체 평가표본 20개라고 해석하면 안 된다. | Figure 3 |
| 답변 모델 | GPT-3, GPT-4, UnifiedQA-3B. 검색 항목을 고르는 별도 LLM 호출은 제안 검색 단계에 없다. | §4, §6 |
| NarrativeQA 지표 | BLEU-1/4, ROUGE-L, METEOR. AllenNLP 평가에 평활화·BLEU4 가중치·METEOR 토큰화 수정. **SCROLLS F1과 다르다.** | §4, Appendix H |
| QASPER 지표 | 답변 F1. | §4 |
| QuALITY 지표·분할 | Table 4는 dev 정확도, Table 7은 test 및 hard 정확도. | Tables 4, 7 |

논문에서 모든 평가를 “SCROLLS 검증 세트”라고 지정한 근거는 찾지 못했다. 데이터별 완전한 평가 ID 목록·샘플링 시드·모든 표의 분할 대응·API 날짜 고정 모델명도 확인되지 않았다. 따라서 그 조건들을 추정해서 채우면 안 된다.

## 2. 발표 당시 공식 코드와 논문의 차이

논문이 연결한 [원저자 저장소](https://github.com/parthsarthi03/raptor)의 2024-05-01 이전 마지막 커밋을 확인했다. 해당 커밋은 **`2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845`**, 기록 시각은 2024-03-21이다. 현재 검색되는 현대화된 RAPTOR 저장소의 기본값을 2024년 논문 설정으로 소급하지 않는다.

| 코드 위치 | 확인된 동작 | 재현상 의미 |
|---|---|---|
| [tree_builder.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/tree_builder.py) | 기본 토크나이저 `cl100k_base`, 조각 100토큰, 최대 5층; 기본 임베딩은 OpenAI. | 논문의 SBERT 실험을 재현하려면 명시적으로 교체해야 한다. |
| [EmbeddingModels.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/EmbeddingModels.py) | OpenAI 기본 `text-embedding-ada-002`; SBERT 클래스도 제공. | 공식 코드 실행만으로 논문과 동일한 임베딩이 선택되는 것은 아니다. |
| [utils.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/utils.py) | `split_text` 기본 중첩 0; 긴 문장은 쉼표·세미콜론·콜론으로 추가 분할. | “모든 원문 조각이 정확히 100토큰”이라고 서술하면 부정확하다. |
| [cluster_utils.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/cluster_utils.py) | 군집 입력 기본 한도 3,500토큰, 차원 10, 군집 확률 임계값 0.1; 초과 군집 재분할. | 군집 요약 입력 한도와 질의 검색 예산은 별개다. |
| [tree_retriever.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/tree_retriever.py) | 기본 `top_k=10`, `max_tokens=3500`; 순위순 후보가 한도를 넘으면 `break`. | 논문 2,000토큰 설정과 다르며, 초과 후보만 건너뛰는 `continue` 정책도 아니다. |
| [QAModels.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/QAModels.py) | GPT 계열 답변은 temperature 0. GPT-4/GPT-3.5 래퍼는 `max_tokens` 인자를 받지만 실제 chat 요청에 전달하지 않는다. UnifiedQA는 `allenai/unifiedqa-v2-t5-3b-1363200`. | 함수 시그니처의 150을 실제 출력 상한이라고 오인하면 안 된다. 실험은 실제 요청값을 기록해야 한다. |
| [SummarizationModels.py](https://github.com/parthsarthi03/raptor/blob/2e3e83e5c4aa6a9b5f2d8359f5b71a9159c20845/raptor/SummarizationModels.py) | GPT-3.5-turbo 요약, 호출 시 출력 한도 전달; temperature는 명시하지 않음. | 답변의 temperature 0을 요약에도 적용했다고 가정하지 않는다. |

해당 커밋의 파일 목록에는 완전한 벤치마크 실행기, 고정 평가 ID 목록, 논문 표별 예측 파일이 없었다. 따라서 **알고리즘을 구현할 수 있다는 것과 논문 수치를 그대로 재현할 수 있다는 것은 별도 판단**이다. 현재 실험은 로컬 모델과 A/B/R0를 평가하므로 RAPTOR 논문의 성능 수치를 직접 재현하는 실험이 아니다.

## 3. SCROLLS에서 가져올 규칙

1차 문헌: Shaham et al., **SCROLLS: Standardized CompaRison Over Long Language Sequences**, EMNLP 2022. [논문 페이지](https://aclanthology.org/2022.emnlp-main.823/), [PDF](https://aclanthology.org/2022.emnlp-main.823.pdf), §3.1–3.3.

SCROLLS는 원본 데이터셋의 분할을 유지하며 공통 텍스트 입력/출력으로 변환한다. 질문이 있는 과제는 질문을 원문 앞에 놓고 빈 줄 두 개로 분리한다. QuALITY는 질문에 네 선택지를 포함한다. Qasper·NarrativeQA의 여러 정답은 동일 질문 ID의 참조 답안으로 함께 채점한다. 공개 검증 세트를 평가할 수 있으며 공식 test의 정답은 비공개다.

| 이 실험의 과제 | 입력에서 보존할 것 | 답변/지표 | 평가 단위 |
|---|---|---|---|
| QMSum | 사용자 질의와 회의록; 화자·발언 순서 | 질의에 맞춘 요약; ROUGE-1/2/L 및 기하평균 | 질의 1개 |
| Qasper | 질문과 논문; 제목·초록·절 제목 | 짧은 답변, yes/no, unanswerable; 최대 참조 F1 | 질문 ID 1개 |
| NarrativeQA | 질문과 책/대본 **원문** | 짧은 답변; 최대 참조 F1 | 질문 ID 1개 |
| QuALITY | 질문·선택지 네 개와 기사/이야기 | 정답 선택지 텍스트; 정규화 EM | 질문 1개 |

표의 전처리·정규화·집계 세부 기준은 내려받은 [공식 평가 구현](official_sources/scrolls/metrics/scrolls.py)에 따른다. NarrativeQA를 책의 외부 요약본으로 대체하지 않는다. QuALITY에서 모델이 문자만 답하게 하려면 선택지 문자→원문 매핑을 모든 방식에 동일하게 적용하고 원시 출력과 매핑 결과를 함께 보존한다. `is_hard`가 있다면 전체 EM과 hard 하위집합 EM을 분리해서 표시할 수 있다.

SCROLLS의 7개 과제 전체 점수와, 여기서 선택한 4개 과제 점수를 혼동하면 안 된다. 특히 이번 7종은 **SCROLLS 4종 + LongBench 3종**이므로 “공식 SCROLLS 전체 점수”라는 단일 합계를 만들 수 없다.

## 4. LongBench에서 가져올 규칙

1차 문헌: Bai et al., **LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding**, ACL 2024. [논문 페이지](https://aclanthology.org/2024.acl-long.172/), [PDF](https://aclanthology.org/2024.acl-long.172.pdf), §3.2, §4.1–4.2, Appendix A–B.

| 과제 | 구성과 필요한 능력 | 이 실험에서 사용할 판본/지표 |
|---|---|---|
| HotpotQA | 여러 위키 문서에 흩어진 단서를 결합하는 다단계 질의응답 | LongBench v1 test 200문항, F1 |
| MuSiQue | 여러 단계를 이어야 답할 수 있는 질의응답 | LongBench v1 test 200문항, F1 |
| MultiFieldQA-en | 다양한 분야의 긴 문서에서 답할 근거를 찾는 질의응답 | LongBench v1 test 150문항, F1 |

LongBench의 다문서 QA는 원본 지지 문단을 포함하는 전체 위키 문서와 방해 문서를 넣고 문서 순서를 섞는다. 원본 데이터셋의 전체 dev/test와는 다른 배포 판본이다. 일반 LongBench는 자연스러운 길이 분포를 표본 추출하고, LongBench-E는 길이 구간별로 비교적 균등하게 추출하므로 서로 교체하면 안 된다. 길이 통계는 영어 단어 수다.

논문은 greedy decoding을 사용하며 모델 한도를 넘는 입력은 가운데를 잘라 앞·뒤를 보존한다. 검색 압축 실험은 200단어×7조각 또는 500단어×3조각을 비교한다. 이것을 RAPTOR의 100토큰 조각이나 현재 코드 실험의 1,024토큰 예산과 같은 설정으로 서술하면 안 된다.

실제 질문 프롬프트와 출력 한도는 고정한 [공식 프롬프트](official_sources/longbench/LongBench/config/dataset2prompt.json), [출력 한도](official_sources/longbench/LongBench/config/dataset2maxlen.json)를 확인한다. HotpotQA·MuSiQue는 32, MultiFieldQA-en은 64 생성 토큰이다. F1은 [공식 metrics.py](official_sources/longbench/LongBench/metrics.py)의 정규화와 최대 참조 집계를 적용한다.

## 5. 이번 A/B/R0/FULL 비교에 적용할 원칙

다음은 논문의 주장을 그대로 옮긴 것이 아니라, 위 근거에 따라 정해야 할 **이 프로젝트의 실험 설계**다.

1. **질문·정답·원문은 공식 데이터에서 가져온다.** 질의와 원문 경계 파싱을 검증하고, 정답은 색인 생성·검색·선택 프롬프트에 넣지 않는다.
2. **A/B는 문서용으로 어떻게 바꿨는지 밝힌다.** 이 데이터에는 함수와 import가 없다. 문서 조각의 주소·제목·관련 문서 관계를 쓰면 그것은 코드 색인의 문서용 대응물이다. 인접 조각 연결이나 단어 겹침 연결을 실제 import 관계라고 부르지 않는다.
3. **R0는 TF-IDF 기반 원문 검색이라는 정체성을 유지한다.** RAPTOR의 SBERT·군집·재귀 요약을 구현하지 않은 R0를 RAPTOR 재현으로 부르지 않는다. 단독 조각/묶음 후보, 묶음의 최대 깊이, 중복 제거, 후보 초과 시 처리, 전송 예산을 명시한다.
4. **A/B/R0에는 같은 원문 예산을 적용한다.** 선택기 등 추가 호출은 전부 합산한다. 예산 수치와 토크나이저 선택은 이 실험의 설정임을 밝힌다. RAPTOR가 같은 검색 예산으로 비교한 원칙을 참고할 수 있지만 수치 자체를 임의로 같다고 주장할 수는 없다.
5. **FULL을 실제로 호출한다.** 원문이 한도 내에 들어가는 문항에서 전체 문서를 전달한 답변·토큰·시간을 측정한다. 초과 문항은 별도로 기록한다. LongBench식 가운데 자르기를 추가하면 `FULL-truncated`라고 표시해야 하며 완전 원문 실험을 대체하지 않는다.
6. **결과의 분모를 일치시킨다.** 전체 문항의 방법별 성능과 처리 가능률을 보여주고, FULL이 들어가는 공통 문항에 대한 짝지은 비교를 별도로 낸다. FULL이 실행되지 않은 문항을 정상 평가로 조용히 제외하지 않는다.
7. **데이터셋마다 실제 문항 수·고유 문서 수·길이·출력 형식·점수 의미를 제시한다.** 표본만 실행했다면 선택 규칙/ID/분포와 미실행 수를 명시한다. 반복 실행이나 같은 문서의 여러 질문을 독립 문서 수로 세지 않는다.
8. **품질과 비용을 함께 보고한다.** 질문당 누적 입력, 최대 단일 요청 입력, 출력, 호출 수, 시간, 전처리 비용을 구분한다. F1/ROUGE를 정답률로 부르지 않는다. 모델과 표본이 다르면 논문 숫자와 우열을 직접 주장하지 않는다.

이 구조라면 “논문에서 확인한 평가 원칙을 적용한 새 비교 실험”이라고 설명할 수 있다. “RAPTOR 논문의 7개 검증 데이터셋을 그대로 재현했다”는 설명은 현재 확인한 근거와 맞지 않는다.
