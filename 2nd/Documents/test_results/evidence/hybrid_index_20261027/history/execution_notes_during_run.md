# 진행 상태 — 최종 결과 아님

현재 목표는 H 결합 방식을 기존 큰 파일·96문제 조건으로 실제 평가하고 3번 보고서에 추가하는 것이다. `get_goal`에서 ACTIVE를 확인했다. 완료 전 목표를 complete로 표시하지 않는다.

## 실행 중인 세션

- 평가 실행: exec session **81532**, PID **69786**, 시작 2026-10-26 18:29 UTC. B/R0/H × 96문제 × 3회 = 864답변. 상태는 `work_status.json`. 완료 표시는 `completed_eval.json`.
- 로컬 llama-server: exec session **42520**, PTY. 서버 로그 `server.log`, localhost:8766. 이 작업이 시작한 서버다. 평가가 끝난 뒤 이 세션에 Ctrl-C를 보내 종료한다. 서버를 재시작하거나 활성 평가를 중복 실행하지 않는다.
- 후처리: exec session **89984**. `completed_eval.json`을 기다린 뒤 순서대로 `analyze_hybrid.py`, `verify_hybrid.py`, `diagnose_hybrid.py` 실행. 진행은 `postprocessing_status.json`, 로그는 `postprocessing.log`. 완료 뒤 manual 분석을 중복 실행해 해시를 바꾸지 않는다. 실패 시 검증 구현을 점검하되 고정한 실험·분석 소스/결과는 변경하지 않는다.

## 고정된 파일

`experiment_hybrid.py`, `analyze_hybrid.py`, protocol/analysis_plan에 있는 모든 기존 소스·자료는 변경하지 않는다. 연습 24개 완료, 첫 평가 반복 288개 완료. 통신/잘림/캐시 오류 없음. 이후 성적을 보고 설정을 바꾸지 않았다.

H는 R0 raw TF-IDF로 각 항목의 자기 출발 묶음/단독 점수 중 max를 부여한다. 자식에게 조상 점수를 전파하지 않는다. 양수 상위24 중 512토큰 목록. 함수/상수 합계 최대8개를 LLM이 지정. 단일 원문만1024한도에 전달; 자동 의존 확장/추가읽기/재시도 없음. 두 호출 모두 입력 집계. 잘못된 선택도 실패로 남기고 빈 원문으로 답변 호출까지 실행한다.

## 준비한 코드/문서

- 새 `verify_hybrid.py`: 독립 AST/TF-IDF/메타데이터/선택/pack/오프라인 토큰/채점/프로젝트 통계 재계산. 연습자료의 AST,선택,TF-IDF2493값을 사전 점검함. 전체는 후처리에서 실행.
- 새 `diagnose_hybrid.py`: 선택 오류 분류 및 정상선택 등 조건부 비용. **사후 기술분석**임을 명시. 기본분석을 대체하지 않음.
- 새 `report_hybrid.py`: 기존 보고서에1.11 H,2절H표,8절추가실험,앞부분읽는순서 등을 추가. 기존자료변경은 report_edits.json으로 되돌릴 수 있도록 함.
- `report_raptor_large.py`: H verification이 있으면 마지막에 report_hybrid.augment 적용하도록 연결함. 아직 보고서를 생성하지 않음.
- 새 `audit_hybrid_report.py`: 전체 이전보고서 복원, 숫자/링크/사례/호출수를 확인.
- `report_materials/method.md`, `design.md`, `cases.md` 준비 완료. **opening.md와 interpretation.md는 전체 결과를 본 뒤 작성해야 함.** interpretation.md는8.5추가해석→cases.md의8.6→8.7최종판단 순서로 작성. 생성기가8.8증거를 뒤에 붙임.
- `reproduce.md` 있음. 실제 본문 생성/감사는 아직 안 했음.

## 실제 사례

사전 분석 규칙(1회차, ID순 첫 HgainR0/HlossR0)으로 `report_examples.json` 저장. `cases.md`는 이 기록에 근거한다.
- H gain: eval_cache__negative_ttl, expected0. H0/868입력/87원문/필수포함25%; R0 300오답/1145입력/1021원문/100%; B30오답/478입력/176원문/100%. H는cache_ttl만 골랐고 상수값없음. 정답 원인을 추정하지 않음.
- H loss: eval_authorization__direct_calls. H가session_valid를빼먹음,927입력/122원문/필수포함100%. R0와B정답. authorize실제원문에세호출모두보임. 원문누락으로 설명하지 않음.

## 완료할 일

1. 864개 실행과 후처리 성공을 확인. 완료 후 소유 서버 종료.
2. summary와posthoc,실제응답을 검토. H의 전체토큰 감소가 선택실패로 원문0인건에 의존하는지 구분. 유효선택 조건부 비교는 사후 기술분석으로 표기. 역사적A/FULL/RF/RH/C와 새B/R0/H 구분.
3. opening.md, interpretation.md 작성. cases.md는 그대로 포함. H방법한계를 확인사실과 추정으로 구분. 필요한 참조 주소가목록화살표에있어도 번호행에없으면고를수없다는제약은1.11에이미설명.
4. report_raptor_large.py → audit_raptor_report.py → audit_hybrid_report.py. 오류는 실제원자료/코드와대조해수정. 보고서의누락/표/링크/수치를검토.
5. report자료 스냅샷과 최신매니페스트/완료상태 정리. 이전 보고서관리기록은history/previous_report_metadata에 이미보존. 기존실험원자료는절대덮어쓰지않음.
6. 최종보고서를열고 결과·절감률·정확도대가를간결한한국어로답변. 진짜완료뒤goal complete.

원래 보고서 경로: /Users/oscar/Desktop/SecureCode/2nd/Documents/test_results/03_현재색인_A와_파일간확장_B_재실험_비교보고서.md
보고서 생성 전 SHA: 0a2624f7999f81dd44c1d6c55b023caeb8478c5f65e21004534b8de49f17b2e5
