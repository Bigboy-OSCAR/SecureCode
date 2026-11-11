# LocalDesk Mac 완성 작업 — 2026-11-11

상태: COMPLETED — 2026-11-11 19:06 KST. 기존 완료 항목 재검증, Figma UI·모델 교체·Mac 앱 빌드와 직접 조작 인수를 완료했다. 최종 판정은 docs/release/ACCEPTANCE_REPORT.md를 따른다.

## 초기 감사

- 시작 commit: `106d30c0`. 사용자 미커밋 변경 없음. 작업 branch: `codex/localdesk-macos-completion`.
- 대표 미완료: 1.6, 2.3, 3.8. 2.3은 실제 설계 검토/인수표/수정 요청/증거가 보존되어 있고, `docs/progress/tasks/2.3.md`가 COMPLETED다. 1.6 기록과 Git 이력에서 후속 수정의 체크 누락을 확인하여 2.3의 네 체크를 복원했다. 이는 최종 UI 통과 판정과 별개다.
- 1.6 잔여: 새로고침 후 선택·세션 복구, 대화/실행 복구, 일부 오류·접근성·포인터 필터 검증.
- 기존 UI는 카드형 3열이며 Figma의 사이드바/대화/모델 선택/팝업 구성과 다르다. 실제 API를 유지하면서 UI를 재구성한다.
- 기존 모델 설정은 시작 시 고정되어 UI에서의 실제 모델 교체가 필요하다.
- 이 Mac의 설치된 의존성이 lock과 달랐고 Python pypdf가 누락되어 있었다. 고정 의존성 설치 후 시험을 재실행한다.
- 기존 Qwen3.8 27B MLX 모델과 LM Studio, llama.cpp를 확인했다. 공식 Qwen2.5 7B Instruct GGUF Q4_K_M을 추가로 내려받아 교체를 검증한다. 모델 파일/로컬 설정/사용자 데이터는 Git에 넣지 않는다.

## 실행 원칙

사용한도 리셋권은 사용하지 않는다. 완료된 작업 단위마다 commit/push하며, 검증되지 않은 항목은 체크하지 않는다. 실제 모델 시험과 fixture 자동 시험을 구분한다. 최종 앱을 computer use로 직접 조작하여 결과를 기록한다.

## 후속 증거

최종 자동 시험·실 모델·화면 조작·패키징 결과는 작업 기록과 `docs/release/ACCEPTANCE_REPORT.md`에 연결한다. 현재 최종 인수는 미완료다.

## 실제 모델 및 입력량 측정

- Qwen2.5 7B Instruct Q4_K_M의 실제 llama.cpp provider + SDK 통합 12개 검사 통과. 모델 자리의 fixture 없이 코드 근거 답변, 승인 명령, Runtime 저장/검색, PDF 지정 페이지, 취소, 부적합 자료 차단을 실행했다.
- 최초 실행은 도구 호출 3개 항목이 실패했다. llama.cpp grammar 생성기가 도구 정의의 큰 maxLength 반복 제한을 처리하지 못한 원인을 확인했다. 서버에 보내는 generation hint만 제거하고 SDK/실행 검증은 유지했으며, 변환 후 전송 본문을 예산 게이트가 계수한다. 수정 후 동일 시험은 첫 시도에 전부 통과했다.
- 계수 대조: 한글 chat 34=34, 도구 정의/호출 이력 203=203 (계수기 대 실제 provider usage).
- 관련 원문 수정 후 재실행한 실제 SDK 요청 7회의 최대 입력 5,399토큰, 누적 입력 32,054토큰. 동일 프레임/도구/이력에 선택 코드 대신 전체 fixture 소스, 저장 descriptor 대신 원래 로그, PDF 2쪽 대신 전체 쪽을 넣은 계수 전용 대조군은 최대 535,104, 누적 2,683,291토큰이다. 대조군은 모델에 추론 요청하지 않았으며 정확도·실행속도 향상을 주장하지 않는다.
- 재현: `SECURECODE_LIVE_SMOKE=1 node --import tsx scripts/acceptance/measureContext.ts` (로컬 llama.cpp 실행 및 `.env` 설정 필요).
- 최종 상세: [context-measurement.json](../../artifacts/verification/localdesk-mac/context-measurement.json). 최초 실패 기록: [context-measurement-initial-failure.json](../../artifacts/verification/localdesk-mac/context-measurement-initial-failure.json).
- native 앱에서 폴더 선택→프로젝트 등록→별도 시험 폴더의 5언어 1,009개 파일 색인(revision 1)→실제 질문/답변·근거 표시를 computer use로 확인했다. 전체 화면 인수는 계속 진행 중이다.
