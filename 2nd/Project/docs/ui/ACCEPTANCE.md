# UI 최종 인수표

> 작업: 2.3 · 담당: 김찬우 · 작성일: 2026-11-09 (Asia/Seoul)
>
> 현재 상태: **COMPLETED — Mac UI 기능·화면 인수 및 최신 native 앱 직접 조작 재검증 완료**. VoiceOver 음성 낭독은 미검증이며, 키보드·접근성 트리·명도 대비의 확인 범위와 구별한다. 최신 판정은 이 문서 10절과 [Mac 최종 인수 보고서](../release/ACCEPTANCE_REPORT.md)를 따른다. 1~9절은 기존 fixture 검토·인계 당시 기록으로 보존한다.

## 1. 기준과 판정 규칙

- 요구 정본: [SCREEN_SPEC](SCREEN_SPEC.md), [UI_BEHAVIOR](UI_BEHAVIOR.md), [USER_SCENARIOS](USER_SCENARIOS.md), [UI_BEHAVIOR_CASES](UI_BEHAVIOR_CASES.md). `UI-01`~`UI-34`, `SC-01`~`SC-09`를 변경하지 않는다.
- 인수 ID `AC-nn`은 같은 번호의 `UI-nn`과 1:1이다. 표의 구현 담당 작업은 모두 김민지의 작업이며, 각 행은 1.6에서 검증하고 3.8에서 증거를 인수한다.
- API 입력·출력은 `contracts/` JSON Schema와 생성 타입을 따른다. 각 행의 구체적인 성공/거부 JSON 파일은 같은 `UI-nn`의 [사례·fixture 대응표](UI_BEHAVIOR_CASES.md)에 있다. 거부용 fixture를 성공 렌더 입력으로 사용하지 않는다.
- 아래 **현재 검토 결과**는 확인한 범위만 적는다. `표시 확인`은 그 화면 요소가 렌더됐다는 뜻이고, `행동 확인`은 fixture 요청/응답 흐름을 실행했다는 뜻이다. 조작·API 연결이 없으면 `부분/인계`다. 모든 행의 **실서비스 최종 결과는 미검증**이다.
- [화면 수정 요청](../handoffs/2.3-ui-review-fixes.md)의 미해결 결함을 PASS로 표시하지 않는다. 2.3은 검토와 처리 작업 지정으로 닫을 수 있지만, 1.6은 수정·재검증·실서비스 증거 없이 닫을 수 없다.

### 검증 방법 코드와 실제 증거

| 코드 | 방법과 확인 범위 | 현재 증거/제한 |
| --- | --- | --- |
| F | 계약 fixture를 검증하고 컴포넌트를 정적 렌더링해 필드·문구·disabled·ARIA 검사 | [ui.test.tsx](../../apps/ui/tests/ui.test.tsx) 10개 통과. 59개 `screen-cases`는 fixture schema와 상태 이름의 대응 검사다. **59개 사용자 흐름을 각각 실행한 결과가 아니다.** |
| C | fixture client와 RunController에서 요청 수·scope·sequence·terminal·승인 digest·재조회 검사 | [runController.test.ts](../../apps/ui/tests/runController.test.ts) 15개 통과. 실제 HTTP/SSE/provider 실행은 없음. |
| V | 실행 중 브라우저에서 실제 입력/클릭/키보드·화면 폭·모달·표시 확인 | [2.3 검증 기록](../progress/tasks/2.3.md)의 화면별 관찰을 따른다. 없는 조작을 코드 추론만으로 통과 처리하지 않는다. |
| L | 실제 host `/api/v1`·SSE와 SDK·컨텍스트 서비스 연결 후 서버 사실과 화면 대조 | 1.4/1.5 구현 후 1.6·3.8 수행. 승인 효과, 파일 보존, bounded I/O, 최종 예산, provider/history 원문 제거는 3.6/4.10 증거와 함께 확인. |

2026-11-09 재실행: `apps/ui`에서 `node --import tsx --test tests/ui.test.tsx tests/runController.test.ts` → **25 tests, 25 pass, 0 fail**. 별도 `npm test --workspace=apps/ui`는 실제 Vite proxy 1개를 포함해 **26/26** 통과했다. 이 결과는 F/C와 로컬 proxy 범위만 증명한다. 모든 사례의 최종 결과를 이 숫자로 대체하지 않는다.

## 2. 연결·프로젝트 인수

| 인수 ID / 요구·화면 | 선행 데이터 | 사용자 조작·응답 주입 | 예상 표시·버튼 및 실패 기준 | 검증 방법 | 구현 담당 | 현재 검토 결과 / 최종 조건 |
| --- | --- | --- | --- | --- | --- | --- |
| AC-01 / UI-01 / SC-01 | 인증 전 health, 유효/빈/8자 미만 연결 코드, 지연 응답 | 빈 입력 → 코드 입력 → 연결 → 성공 | 빈값/형식 오류/처리 중 연결 비활성. 진행 표시 후 프로젝트로 이동하고 코드 삭제. URL·로그·브라우저 영구 저장소에 코드 없음 | F·V·L: 입력과 network/cookie/저장소 대조 | 1.2/1.3/1.4 | 폼 형식과 코드 삭제 구현 확인. 현재 제출은 fixture 형식 확인이며 인증·화면 이동 아님. 1.4에서 실제 bootstrap 후 검증 미해결 요청: UI23-07. |
| AC-02 / UI-02 / SC-01, SC-03 | 잘못된/만료/재사용 코드, 서비스 중지, 진행 중 세션 인증 만료 | 연결 실패 → 새 코드 입력 → 기존 run 조회 | 원인별 재입력/실행 창 확인 안내. 인증 만료를 취소로 표시하지 않음. 재인증 후 기존 run snapshot 복구, 새 run 생성 0회 | F·C·V·L: 오류별 재인증/요청 수 | 1.3/1.4 | 만료 표시와 run 복구 단위 행동 확인. bootstrap 인증 만료→기존 run 연결은 미구현/인계 미해결 요청: UI23-07. |
| AC-03 / UI-03 / SC-02 | 빈 workspace 목록, 허용/없는/권한 없는 경로 | 이름·경로 입력 → 등록 거부 수정 → 성공 → 새로고침 | 인접 오류, 응답 성공 전 목록 추가 금지. 표시 이름만 목록에 유지, 서버 절대경로 되돌림 금지. 목록·선택·session 복구 | F·V·L: 목록 API와 refresh 후 화면 대조 | 1.2/1.3/1.4 | 폼/목록 예시 표시. 제출은 형식 검증만 수행하며 실제 등록/선택/복구는 1.4 인계 미해결 요청: UI23-07. |
| AC-04 / UI-04 / SC-02 | 5개 언어 각각 및 혼합 프로젝트, queued/indexing/ready 상태 | 색인 시작 → 지연 → 완료 조회 | 중복 요청 방지, 처리/제외 파일 수·revision 표시. 총량 없으면 임의 % 금지. `searchable` 응답으로 대화 허용 | F·V·L: fixture 상태 선택 후 실제 색인 API 대조 | 1.2/1.3/1.4 | 상태 selector로 표시 확인 가능. 실제 색인 시작/진행 조회·대화 gate는 1.4 및 3.6 이후 검증 미해결 요청: UI23-07. |
| AC-05 / UI-05 / SC-02 | 일부 구문 오류, 미지원 TypeScript, 전체 심볼 0개 | partial/zero/failed 색인 응답 선택·수신 | 사용/제외 수·상대 경로·이유 분리. 부분 실패를 완전 성공으로 표시하지 않음. JavaScript 색인/TypeScript 등록 자료 안내, 0개 검색 성공 꾸미기 금지 | F·V·L: 상태별 counts/diagnostics/searchable | 1.2/1.3/1.4 | partial/zero/stale 표시 입력 존재. 실제 프로젝트에서 동일 표시와 중복 색인 방지를 1.4에서 검증 미해결 요청: UI23-07. |
| AC-06 / UI-06 / SC-02 | 이전 revision 선택 후 코드 변경/삭제, 새 색인 성공/실패 | 색인 갱신 → 이전 자료 읽기 | 변경 안내 및 새 revision, 오래된 선택 제외. 이전 색인은 서버가 사용 가능으로 확인한 경우만 사용 | F·V·L: 선택→파일 변경→색인 갱신·전송 캡처 | 1.3/1.5 | stale 예시 표시만 확인. 실제 선택·preview 무효화는 1.5 인계 미해결 요청: UI23-07. |

## 3. 대화·실행·승인 인수

| 인수 ID / 요구·화면 | 선행 데이터 | 사용자 조작·응답 주입 | 예상 표시·버튼 및 실패 기준 | 검증 방법 | 구현 담당 | 현재 검토 결과 / 최종 조건 |
| --- | --- | --- | --- | --- | --- | --- |
| AC-07 / UI-07 / SC-03 | ready index, configured provider, 사용 가능한 보호·예산·session | 빈 질문 → 식별자 질문 → stream/tool → completed | 빈값 전송 비활성. 질문·이력·답변·출처가 같은 run에 연결. 서버 terminal 전 완료 표시 금지 | F·C·V·L: delta/snapshot/도구 실행 이력 | 1.2/1.3/1.4 | 완료/실패 렌더와 fixture run 생성은 확인. 도구 phase/출처 진입점, settings 전송 gate가 없고 답변은 280자 뒤 안내 없이 잘린다. 관련 인계 해결 전 해당 흐름 전체 PASS가 아님. 미해결 요청: UI23-05, UI23-07, UI23-08. |
| AC-08 / UI-08 / SC-03 | create 응답 지연/유실, active run | 연속 전송 → 재확인 → 새로고침/재접속 | 동일 idempotency key로 1회 run. active 중 새 전송 비활성. 재연결로 새 도구 효과 발생 금지 | C·V·L: client call count, 서버 run/tool count | 1.3/1.4 | fixture 중복 제출/같은 key 확인. 실제 응답 유실·reload 후 보존은 1.4 검증 미해결 요청: UI23-07. |
| AC-09 / UI-09 / SC-03, SC-05 | 식별자 불일치 또는 한국어만 있는 NO_MATCH 응답 | 관련 코드 찾기 → 무결과 → 입력 수정 | 함수명/파일명 안내. 검색 근거 없는 답변 표시, NO_MATCH를 통신 오류로 표시하지 않음. 원문 전체·자동 LLM 재검색·자동 새 run 금지 | F·V·L: 빈 candidates 및 사용자 재전송 | 1.2/1.3/1.5 | 무결과 문구는 있으나 후보와 동시에 고정 표시됨. 조건부 표시와 검색 조작은 1.5 인계 미해결 요청: UI23-01, UI23-05. |
| AC-10 / UI-10 / SC-03, SC-09 | provider/SDK 실패, 보호 미준비·모델 미설정 settings | 실행 시도/실행 중 오류 → 복구 안내 | 안전한 오류/request_id. 보호 미준비는 전송 차단, 일부 답변은 중단 전 결과로 표시. 원문 fallback 및 거짓 완료 금지 | F·C·V·L: settings gate + error snapshot | 1.3/1.4/1.5 | 실패 snapshot은 표현 가능. settings는 fixture로 별도 표시되어 실제 전송 gate 미연결; 1.4/1.5 인계 미해결 요청: UI23-07. |
| AC-11 / UI-11 / SC-03 | 실행/승인 대기 중 부분 답변, 취소 응답 지연·terminal 경합 | 취소 요청 → 지연 → terminal 확인 → 늦은 진행 이벤트 | 요청 중과 취소됨 구별, terminal 1개 유지. 승인 종료. 이미 실행된 변경의 자동 복원을 약속하지 않음 | C·V·L: pending/terminal/approval 동시 확인 | 1.3/1.4 | controller의 취소 지연·terminal 보존은 확인. 실제 앱 fixture 취소 후 질문·거절 이력 소실, 답변 자체 잘림 및 낭독 범위 문제는 미해결. SDK abort 경합은 L 필요. 미해결 요청: UI23-08, UI23-09. |
| AC-12 / UI-12 / SC-02, SC-03, SC-05, SC-06, SC-07, SC-08, SC-09 | run/index/PDF/read 중 단절, 중복/역순/sequence gap/이전 scope 응답 | 끊기 → 재연결 → 프로젝트 변경 → 늦은 응답 | 끊김≠취소. mutation 차단. run replay/snapshot, index/PDF 상태 조회, stale 자료 표시. 이전 scope가 현재 화면을 덮지 않음 | C·V·L: 중복·역순·gap·장시간 지연 및 navigation | 1.3/1.4/1.5 | controller 중복·역순·재연결·세션 전환·늦은 snapshot 회귀는 확인. 화면의 복구 도구 phase/citations, index/PDF/pointer별 재조회·실 adapter는 미연결. 미해결 요청: UI23-05, UI23-07. |
| AC-13 / UI-13 / SC-04 | 검토 가능한 명령/코드 변경, 잘린 검토 요청, 승인 유효 시각 | 전체 내용 검토 → 승인 확인 → 지연 → 수락/도구 완료 | 대상·내용·만료시각 표시. approval ID/digest 고정, 중복 결정 방지. 잘렸거나 reviewable=false면 승인 불가·거절 가능. 승인됨과 실행 완료 분리 상세창 초기 초점은 제목/검토 내용에 두고 닫으면 시작점으로 복귀. | F·C·V·L: 전체 검토 문구·단일 결정·도구 실행 수 | 1.2/1.3/1.4 | 전체 승인 본문과 결정 잠금은 확인. kind/대상/만료시각 미표시, 초기 초점이 제목/내용 아닌 닫기에 놓이고 종료 후 시작 버튼 복귀도 실패. 실제 도구 실행 수는 L 필요. 미해결 요청: UI23-04. |
| AC-14 / UI-14 / SC-03, SC-04 | 승인 대기 요청 | 거절 확인 닫기/Escape → 다시 열어 거절 | 닫기는 결정 아님. 거절한 요청만 종료, run 최종 상태는 서버 확인. 도구 실행 0회, 포괄 승인 없음 | C·V·L: 모달/결정 count/도구 이력 | 1.3/1.4 | fixture 거절이 pending만 제거하는 동작은 확인. 모달 초기·복귀 초점 미충족이며 뒤이은 취소에서 거절 이력도 사라진다. 실제 도구 미실행은 L 필요. 미해결 요청: UI23-04, UI23-09. |
| AC-15 / UI-15 / SC-04 | 만료·취소·세션 종료·입력 digest 변경·결정 응답 유실 | 늦은 결정 → 재접속 → snapshot | 만료/입력변경/처리됨 구별. 기존 승인 자동 재전송 금지. 상태 확인 전 버튼 잠금, 다른 scope 결정 거부 | F·C·V·L: 시계 고정·timeout·digest 변경·중복 호출 | 1.3/1.4 | controller 만료 미전송/timeout 복구/중복 결정 잠금은 확인. 화면의 만료 정보·확인창 초기/복귀 초점, 취소 후 결정 이력 보존은 미충족. 실제 다른 scope/digest 오류는 L 필요. 미해결 요청: UI23-04, UI23-09. |

## 4. 관련 코드·자료·부분 조회 인수

| 인수 ID / 요구·화면 | 선행 데이터 | 사용자 조작·응답 주입 | 예상 표시·버튼 및 실패 기준 | 검증 방법 | 구현 담당 | 현재 검토 결과 / 최종 조건 |
| --- | --- | --- | --- | --- | --- | --- |
| AC-16 / UI-16 / SC-05 | 함수→helper→상수, class·동적 참조, 다수 무관 심볼 | 검색 → 후보 선택 → 원문 열기 → 다음 후보 | score/파일·줄/revision/원문 hash·선택·누락 이유 표시. 깊이3·클래스 내 메서드·unresolved 한계 안내. 무제한 후보/outline/원문 금지 | F·V·L: 후보와 bundle 계약·지정 범위 비교 | 1.2/1.3/1.5 | 첫 후보/fragment/omission만 고정 표시. 검색·선택·후보 paging 및 unresolved 표시 보완을 1.5 인계 미해결 요청: UI23-02, UI23-05. |
| AC-17 / UI-17 / SC-02, SC-03, SC-05, SC-09 | 선택/preview 후 source 또는 index revision 변경 | 이전 자료 전송 → stale → 갱신·재선택 | 오래된 선택/preview 폐기, 새 본문 자동 전송 금지. 변경 후 재확인 전 전송 차단 | F·V·L: ref/revision/hash/preview_digest 비교 | 1.3/1.5 | stale 메시지 표시. 실제 선택·preview lifecycle과 run context_refs 연결은 1.5 인계 미해결 요청: UI23-01, UI23-07. |
| AC-18 / UI-18 / SC-06 | 빈/다수 source·runtime 목록, 현재/다른 session, 지연 | 종류 탭·필터 → 다음 목록 → 로딩/실패 | 빈값/필터 무결과/오류 구별. 크기/revision/TTL/제한 preview. 현재 scope만 표시하고 cursor가 있을 때만 다음 | F·V·L: scope·page cursor·network 요청 횟수 | 1.2/1.3/1.5 | Source/Runtime 카드와 빈값 예시만 표시. 탭/필터/paging과 session 연동은 1.5 인계 미해결 요청: UI23-01, UI23-02. |
| AC-19 / UI-19 / SC-06 | 허용 외부 파일, 경로 이탈/symlink/권한·크기 거부 | 명시 경로 입력 → 등록 → 오류 수정 | 지정된 허용 자료만 등록. 경로/권한/크기 오류 구분. 외부 디렉토리 자동 허용·원본 경로 되돌림 금지 | F·V·L: 원본·등록부·API 응답 대조 | 1.3/1.5 | 입력 형식 확인만 수행. 실제 경로 권한·허용 목록 및 등록 응답 처리 1.5 인계 미해결 요청: UI23-02. |
| AC-20 / UI-20 / SC-06, SC-08 | 등록 Source/PDF 및 캐시·명시 선택 | 등록 해제 확인 취소 → 재확인 → 성공/실패 | 취소는 무효과. 성공 뒤 선택·캐시 무효화, 원본 파일 유지. 실패 시 목록 유지, 원본 삭제 버튼 없음 확인창 초기 초점은 설명/돌아가기, 닫기는 시작점으로 복귀. | F·V·L: 모달 close·선택·등록부·원본 hash 확인 | 1.2/1.3/1.5 | Source 등록 해제 문구/확인창은 존재하나 의도만 기록한다. 실제 목록/선택/캐시 반영이 없으며 공용 확인창 초기 초점·닫기 복귀는 UI23-04 기준으로 수정·재검증해야 한다. 미해결 요청: UI23-02, UI23-04. |
| AC-21 / UI-21 / SC-06 | 현재 세션 Runtime 및 선택 | 저장 결과 삭제 확인 취소/성공/실패 | Runtime 저장분만 삭제. Source 문구와 구별, 선택 해제. 실패를 성공으로 표시하거나 원본 삭제 금지 확인창 초기 초점은 설명/돌아가기, 닫기는 시작점으로 복귀. | F·V·L: 해당 blob·metadata·다른 자료 보존 | 1.2/1.3/1.5 | 별도 삭제 문구/확인창은 존재하나 의도만 기록한다. 실제 삭제·목록 변경·실패 복구가 없으며 공용 확인창 초기 초점·닫기 복귀는 UI23-04 기준으로 수정·재검증해야 한다. 미해결 요청: UI23-02, UI23-04. |
| AC-22 / UI-22 / SC-05, SC-06, SC-07, SC-09 | EXPIRED/NOT_FOUND/FORBIDDEN, 열린 이전 출처·선택 | 목록/읽기/preview 요청 | 읽기 불가와 재선택 안내. 이전 내용을 유효로 재사용 금지, 다른 세션 내용/존재 세부정보 비노출 | F·V·L: scope별 오류·선택 무효화 | 1.3/1.5 | 만료/권한 오류 문구 표시. 성공 원문과 오류가 동시에 고정되어 유효성 표현·선택 무효화는 1.5 인계 미해결 요청: UI23-01. |
| AC-23 / UI-23 / SC-07 | 큰 한글 text/log·긴 한 줄, 작은 max_bytes/max_tokens 및 cursor | 범위 입력 → 읽기 → 다음 부분 → 현재 범위 선택 | 실제 범위 숫자·revision/hash/토큰/count_mode·잘림·출처. cursor 있을 때만 다음. 읽기와 선택 분리, UTF-8 보존. 전체/무한 과거 내용 저장 금지 | F·V·L: byte 범위·cursor·DOM·저장소·I/O 계측 | 1.2/1.3/1.5 | 제한 원문은 표시하나 범위 숫자·계수·선택 조작 없음. 다음 부분은 미제공 메시지만 출력. 1.5 인계 미해결 요청: UI23-02. |
| AC-24 / UI-24 / SC-06, SC-07, SC-09 | 조회 중 원본 변경·이전 cursor/selection | 다음 부분/검색/preview → SOURCE_CHANGED | 변경 배지·재등록/갱신/다시 읽기. 이전 cursor/선택 폐기, 다른 revision 원문 합치기 금지, 목록 상태 갱신 | F·V·L: 읽기 중 변경 주입·scope/hash 비교 | 1.3/1.5 | 변경 문구 표시만 확인. stale 선택/cursor 폐기와 원문 재조회는 1.5 인계 미해결 요청: UI23-01. |
| AC-25 / UI-25 / SC-07 | 정상/8 MiB 초과 JSON, invalid selector/line/byte | JSON path·줄/바이트 입력 → 읽기 → 거부 수정 | 허용 selector만 제공. 큰 JSON은 구조 조회 제한·가능한 줄/바이트 안내. 입력 오류 연결, 무제한 JSON I/O 보장 금지 | F·V·L: selector별 요청·상한·오류 응답 | 1.2/1.3/1.5 | INVALID_SELECTOR 예시만 표시, selector 입력과 JSON 제한 안내는 1.5 인계 미해결 요청: UI23-02. |
| AC-26 / UI-26 / SC-07 | 검색 match 0/1/다수, cursor·truncated | 검색어 입력 → 검색 → 다음 결과 → 일치 범위 열기 | 제한 snippet·출처·무결과 안내. 최대 결과 수·cursor 준수. 무결과와 서비스 실패 구별, 전체 자동 조회 금지 | F·V·L: matches/page·읽기 요청 한도 | 1.2/1.3/1.5 | 무결과 문구만 표시. 검색 입력/결과 목록/다음 결과/일치 범위 열기는 1.5 인계 미해결 요청: UI23-02. |

## 5. PDF·예산·설정·공통 품질 인수

| 인수 ID / 요구·화면 | 선행 데이터 | 사용자 조작·응답 주입 | 예상 표시·버튼 및 실패 기준 | 검증 방법 | 구현 담당 | 현재 검토 결과 / 최종 조건 |
| --- | --- | --- | --- | --- | --- | --- |
| AC-27 / UI-27 / SC-08, SC-07 | 유효 한글 다중 페이지 PDF, queued/running/ready job | 경로 등록 → 파싱 → job 조회 → 페이지 선택·읽기 | 등록/파싱 구별, job ID로 복구. 정확한 페이지/hash/parser version 출처, 선택 페이지 외 본문 없음 | F·V·L: job·page read·Skill 등록·provider 요청 대조 | 1.2/1.3/1.5 | 브라우저 7상태 표시 확인. stale 상시 경고와 terminal 로딩 문구(UI23-03) 인계. 실제 job 진행/페이지 입력·읽기/출처 선택은 1.5 및 4.9 인계 미해결 요청: UI23-03. |
| AC-28 / UI-28 / SC-08 | 스캔/빈/손상/암호화/50 MiB·500page 초과, partial/unsupported/failed | 파싱 결과 상태 선택·응답 → 복구 안내 | 사용 가능/제외 페이지와 이유 구분. 성공 위장 금지. 부분 보장 없으면 실패, OCR/해제/업로드 없음 | F·V·L: 실제 오류 PDF·job 상태·읽기 버튼 gate | 1.2/1.3/1.5 | partial/failed/unsupported 문구는 존재하지만 stale 경고가 상시 표시되고 failed/unsupported도 페이지 확인 중으로 잘못 표시된다. 실제 PDF 및 유효 페이지 조작은 검증 대기. 미해결 요청: UI23-03. |
| AC-29 / UI-29 / SC-08, SC-07 | 추출 후 PDF hash/parser version 변경, 이전 선택 | 기존 페이지 읽기 → stale → 재처리 | 캐시/선택 폐기 후 새 provenance. 옛 원문을 새 페이지로 표시 금지. 해제 시 원본 보존 | F·V·L: 버전·cache key·원본 보존 | 1.3/1.5 | stale 문구가 현재 job 상태와 무관하게 상시 표시된다. 실제 캐시·선택 lifecycle, 재파싱·새 provenance 연결이 없으므로 변경 복구 완료가 아니다. 미해결 요청: UI23-03. |
| AC-30 / UI-30 / SC-09 | explicit/runtime/R0 중복 hash+range, 빈 선택, plan 지연 | 선택 → preview → prompt/범위 변경 → 재확인 | 우선순위·선택/제외 및 7종 비용/잔여·계수 방식 표시. 빈 명시 선택 허용. 요청별/누적 구분, 입력 변경 후 preview 갱신 필요 | F·V·L: ref/fragment/budget·preview_digest 대조 | 1.2/1.3/1.5 | 고정 used/budget 및 추정 표시는 있으나 선택·preview 조작/전체 비용·누락 목록 없음. 1.5 인계 미해결 요청: UI23-01, UI23-02. |
| AC-31 / UI-31 / SC-03, SC-05, SC-07, SC-08, SC-09 | 범위/명시 선택 초과, history 단독 초과, tokenizer/framing 미지원 | 읽기/preview/전송 → 차단·범위 축소 | 범위 축소/선택 해제/새 세션/지원 모델 안내. hard-cap 미지원 실행 불가. 자동 요약/전체 전송 없음 | F·V·L: final outbound 계수·provider 호출 0회·선택 재설정 | 1.3/1.5 | 예산 오류 문구 표시. 전송 gate/선택 정책 연결 없음. 4.8 완료 후 1.5·3.6·4.10에서 검증 미해결 요청: UI23-01, UI23-02. |
| AC-32 / UI-32 / SC-09 | provider 설정/미설정/미지원, 보호/서비스 오류 | 설정 보기 → 서버 설정 변경 → 다시 확인 | 모델/지원/상한/보호·실행 가능 여부, 비밀값 없음. 미설정 시 자료 준비만 허용. 추정을 exact로 표시 금지 | F·V·L: settings 응답·UI gate·network 목적지 | 1.2/1.3/1.5 | 미설정 모델과 gate 상태는 표시. 동적 재조회·전송 차단 연결은 1.4/1.5 인계 미해결 요청: UI23-06, UI23-07. |
| AC-33 / UI-33 / SC-01~SC-09 | 1280px/768px, 긴 한글/경로/오류·승인, 모달 | 키보드 탐색·입력·모달 열기 → Tab/Shift+Tab → Escape/닫기 → 복구 | 보이는 라벨·인접 오류·초점 유지/복귀·상태 낭독·대비 확인. 좁은 화면에서도 승인/취소 보존, 페이지 전체 수평 overflow 없음. 닫기/Escape로 승인·삭제 0회 | F·V·L: 키보드/접근성 트리·두 폭 screenshot·overflow/대비 실측 | 1.1/1.2/1.3/1.6 | SSR label/ARIA/anchor 및 1280/768 전체 overflow 없음은 확인. 768 패널 접기 누락, 승인창 제목/내용 초기 초점 및 닫기 복귀 미충족. 상태 낭독·대비 최종 인수는 미실행. 미해결 요청: UI23-04, UI23-06, UI23-08. |
| AC-34 / UI-34 / SC-03, SC-06 | 짧은 출력, 4,096바이트 경계 및 16 KiB 초과 sentinel, 저장 실패/quota/timeout | 무해한 명령 승인 → descriptor → 필요한 범위 재조회 → 실패 주입 | 작은 결과 또는 제한 descriptor·결과 링크. 큰 원문 fallback 금지. UI/DOM/저장소/SSE/provider/history 각각 확인. TTL·삭제·재시작 진실과 일치 | F·C·V·L: 원문 sentinel 검색·바이트 측정·실 SDK/4.10 결과 연결 | 1.3/1.4/1.5 | 제한 preview 표시는 확인. pointer 없이 저장/미지정 bytes를 0으로 단정하는 도구 표시, 280자 자체 잘림, 결과 목록·읽기 연결 미비가 남는다. 전 경계 sentinel 검증은 대기. 미해결 요청: UI23-02, UI23-05, UI23-08. |

## 6. 화면별 구현·최종 검증 연결

| 화면 | 구현 진입점 (`apps/ui/src/` 기준) | 인수 항목 | 최종 실서비스 확인 책임 |
| --- | --- | --- | --- |
2026-11-11 1.6에서 구현 진입점을 실제 서비스 화면(`Live*`)으로 갱신했다. 2.3 시점의 fixture 화면 파일은 1.5에서 삭제됐다.

| 화면 | 구현 진입점 (`apps/ui/src/` 기준) | 인수 항목 | 최종 실서비스 확인 책임 |
| --- | --- | --- | --- |
| SC-01 | `features/settings/components/LiveConnectionPanel.tsx`, `app/LiveApp.tsx` | AC-01, AC-02, AC-33 | 1.4 연결 후 1.6 / 3.8 |
| SC-02 | `features/project/components/LiveProjectPanel.tsx`, `features/project/hooks/useIndexWorkflow.ts` | AC-03~AC-06, AC-12, AC-17, AC-33 | 1.4·1.5와 3.6 색인 연결 후 1.6 / 3.8 |
| SC-03 | `features/chat/components/{ConversationPanel,AnswerView,ToolHistory}.tsx`, `model/runController.ts`, `model/toolLabels.ts` | AC-02, AC-07~AC-12, AC-14, AC-17, AC-31, AC-33, AC-34 | 1.4·1.5 및 실제 SDK 실행 후 1.6 / 3.8 |
| SC-04 | `features/approvals/components/ApprovalCard.tsx`, `components/Modal.tsx` | AC-13~AC-15, AC-33 | 1.4 승인·SDK 도구 효과 연결 후 1.6 / 3.8 |
| SC-05 | `features/context/components/LiveContextPanel.tsx` | AC-09, AC-12, AC-16, AC-17, AC-22, AC-31, AC-33 | 1.5 R0·context 연결 후 1.6 / 3.8 |
| SC-06 | `features/pointers/components/{LivePointerWorkspace,LivePointerPanel}.tsx` | AC-12, AC-18~AC-22, AC-24, AC-33, AC-34 | 1.5 및 4.3~4.6 후 1.6 / 3.8 |
| SC-07 | `features/pointers/components/LivePointerReadPanel.tsx`, `model/pointerSelector.ts` | AC-12, AC-22~AC-27, AC-29, AC-31, AC-33 | 1.5 및 4.6·4.9 후 1.6 / 3.8 |
| SC-08 | `features/pointers/components/LivePdfPanel.tsx` | AC-12, AC-20, AC-27~AC-29, AC-31, AC-33 | 1.5 및 4.9·4.10 후 1.6 / 3.8 |
| SC-09 | `features/context/components/LiveContextPanel.tsx`, `features/settings/components/LiveConnectionPanel.tsx` | AC-10, AC-12, AC-17, AC-22, AC-24, AC-30~AC-33 | 1.5 및 4.8 최종 gate 후 1.6 / 3.8 |
| 공통 | `app/PanelSwitcher.tsx`(1024px 미만 패널 전환), `features/shared/model/provenanceLabels.ts`(출처 표기) | AC-07, AC-16, AC-23, AC-27, AC-33 | 1.6 / 3.8 |

## 7. 1.6·3.8 실행 절차와 증거 필수 항목

1. 1.4/1.5 및 로드맵 선행 조건을 먼저 확인한다. 미완성 API가 501, 보호 gate가 `PROTECTION_UNAVAILABLE`이면 정상 실행 인수는 **BLOCKED**로 기록하고 해당 오류 표시만 별도로 검증한다. fixture 화면을 실제 서비스 화면으로 대체한 것처럼 기록하지 않는다.
2. 각 AC 행을 1280px와 768px에서 실행한다. 인증→프로젝트·5언어 색인→세션·질문→승인/거절/취소→출처→Source/Runtime 부분 조회→PDF 지정 페이지→예산 preview→단절·복구를 같은 workspace/session/run/ref로 이어서 확인한다. 상태를 select로 바꾸는 행위는 서버 전이를 검증한 것이 아니다.
3. 정상 흐름 뒤 실패 입력·권한·만료·변경·budget/저장 오류를 주입한다. 승인됨·등록됨·파싱 완료·취소됨 문구만 보지 말고 실제 파일/도구 효과와 요청 수를 확인한다. 거절·만료는 도구 실행 0회, 중복 제출·재연결은 중복 효과 0회여야 한다.
4. AC-13/14/15는 SDK 도구 실행 횟수, AC-23/24는 bounded I/O·revision/hash, AC-27/29는 실제 PDF 도구·Skill·cache version, AC-31은 최종 outbound 계수/차단, AC-34는 provider/history/SSE/DOM 각각의 sentinel 부재 증거를 연결한다. UI 테스트 하나로 백엔드 불변식을 대신하지 않는다.
5. 각 항목에 `AC ID / 실행 시각 / commit 또는 소스 기준 / 화면 폭 / fixture 또는 실서비스 / workspace·session·run 식별자 / 조작 / 기대 / 실제 / PASS·FAIL·BLOCKED / 결함 ID / 재검증 결과 / 증거 경로`를 남긴다. 비밀값·개인 원문·절대 개인 경로는 기록하지 않는다.
6. 모든 AC 행의 실서비스 결과가 PASS이고 인수 차단 결함이 없을 때만 1.6을 완료한다. 3.8은 이 표·1.6 기록·3.6/4.10의 실제 provider 증거를 함께 확인한다. 자동/수동 또는 fixture/live 구분을 지우지 않는다.

## 8. 검토 인계와 종료 기준

| 수정 요청 ID | 영향 인수 항목 | 구현 처리 작업 | 2.3 판정 |
| --- | --- | --- | --- |
| UI23-01 | AC-09, AC-17, AC-18, AC-22, AC-24, AC-30, AC-31 | 김민지 1.5 연결, 1.6 표현 정리 | 서로 배타적인 성공·무결과·빈값·만료의 동시 표시, 미해결 |
| UI23-02 | AC-16, AC-18, AC-19, AC-20, AC-21, AC-23, AC-25, AC-26, AC-30, AC-31, AC-34 | 김민지 1.5, 1.6 인수 | 검색·범위 입력·선택·preview·목록 조작 누락, 미해결 |
| UI23-03 | AC-27, AC-28, AC-29 | 김민지 1.5, 1.6 인수 | PDF 상태 문구·오류 복구·페이지 조작 누락, 미해결 |
| UI23-04 | AC-13, AC-14, AC-15, AC-20, AC-21, AC-33 | 김민지 1.6 | 승인 종류·대상·만료 및 공용 확인창 초기 초점·복귀, 미해결 |
| UI23-05 | AC-07, AC-09, AC-12, AC-16, AC-34 | 김민지 1.4 실행/이력, 1.5 출처, 1.6 인수 | 도구 phase·저장 사실·답변 출처 표현, 미해결 |
| UI23-06 | AC-32, AC-33 | 김민지 1.6 | 768px 패널 전환과 상태 접근성, 미해결 |
| UI23-07 | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-07, AC-08, AC-10, AC-12, AC-17, AC-32 | 김민지 1.4, 1.5 예산 연동, 1.6 인수 | 인증·색인·모델/보호 준비 조건과 실제 API 연결, 미구현 |
| UI23-08 | AC-07, AC-11, AC-33, AC-34 | 김민지 1.6 | 답변 자체 잘림과 과도한 실시간 알림, 미해결 |
| UI23-09 | AC-11, AC-14, AC-15 | 김민지 1.3 fixture 회귀 보완, 1.4 실 snapshot 동일성, 1.6 인수 | 취소 snapshot의 현재 질문·승인 이력 대체, 미해결 |

수정 요청은 [2.3 UI 검토 인계](../handoffs/2.3-ui-review-fixes.md)에 재현·실제·기대·영향·심각도·담당 작업으로 기록한다. 검토 가능한 fixture 표시와 동작은 현재 기준으로 리뷰했고, UI/상태/API 구현 누락은 1.4·1.5·1.6에서 처리한다. 2.3은 상태 관리 코드·hook·컴포넌트를 수정하지 않는다. 동작 검토 자체를 막는 결함이 생기면 1.3 재개방·수정·재검증 후 2.3을 닫는다.

완료 근거와 브라우저 실측 결과는 [작업 2.3 기록](../progress/tasks/2.3.md)에 있으며, 이 표의 미검증 최종 인수를 완료로 바꾸지 않는다. commit/push는 수행하지 않는다.

## 9. 초기 1.6 인수 기록 (2026-11-11, Mac 완성 작업 이전)

판정 기호:
- **E**: `npm run test:e2e`. 실제 context-service·host·SDK·Vite UI를 headless 브라우저로 조작하고, 모델은 fixture provider다.
- **L**: 실제 provider(로컬 Qwen2.5-7B, llama.cpp)로 브라우저 화면 또는 `npm run test:live`를 확인했다.
- **U**: UI 단위 시험.
- **H**: host 시험.

미해결 항목은 PASS로 적지 않았다. 상세 근거는 [1.6 기록](../progress/tasks/1.6.md)에 있다.

| 인수 ID | 결과 | 근거 / 남은 것 |
| --- | --- | --- |
| AC-01 | PASS | E: 잘못된 코드 거절, 올바른 코드로 연결. 연결 뒤 입력칸이 비고, URL·localStorage·sessionStorage·읽을 수 있는 cookie에 코드가 없다 |
| AC-02 | 부분 | E: 잘못된 코드 안내. 만료·재사용 코드, 서비스 중지 중 연결, 실행 중 인증 만료 뒤 기존 run 복구는 브라우저로 확인하지 않았다 |
| AC-03 | 부분 | E: 등록 성공. 없는 경로는 폼 옆에 사유("경로가 존재하지 않습니다")를 보이고 목록에 넣지 않는다. 새로고침 뒤 목록은 보이지만 **선택·세션은 복구하지 않는다**(미구현) |
| AC-04 | PASS | E: C·C++·Java·JavaScript·Python 프로젝트 색인. 진행 중 중복 시작은 버튼 잠금 |
| AC-05 | PASS | E: `partial`, 발견 7·색인 5·제외 1·실패 1, `broken.py:1 · syntax_error`, `types.ts · unsupported_language` |
| AC-06 | PASS | E·L: 원본 수정 뒤 `stale` 표시, 재색인으로 새 revision |
| AC-07 | PASS | E·L: 질문 → 도구 단계 → 완료. 답변과 서버가 확인한 근거(R0 `파일:줄`, PDF 쪽)를 같은 run에 표시. 빈 질문은 전송 비활성 |
| AC-08 | 부분 | E: 실행 중 전송 잠금. H: 같은 idempotency key로 run 1회. 응답 유실·새로고침 뒤 보존은 브라우저로 확인하지 않았다 |
| AC-09 | PASS | L(1.5): NO_MATCH와 한국어 전용 안내 |
| AC-10 | PASS | E: provider 500 → `실패`. provider 오류 본문을 답변으로 쓰지 않는다(1.6 결함 수정) |
| AC-11 | PASS | E·L: 실행 중 취소 → `취소됨`. 질문과 결정된 승인 이력을 유지한다(UI23-09). 모델 첫 응답 전 취소도 멈추지 않는다(1.6 결함 수정) |
| AC-12 | 부분 | E: SSE 2회 끊김 → "연결이 끊겼습니다" → 자동 재연결 → 같은 run 완료. 색인·PDF 상태 재조회와 화면 이동 중 늦은 응답은 확인하지 않았다 |
| AC-13 | PASS | E: 종류·도구·대상·만료 표시. 대화상자는 제목에 초점, Escape로 시작 버튼에 복귀, 닫기는 결정 없음 |
| AC-14 | PASS | E: 거절 → `거절됨`, 출력 저장 없음 |
| AC-15 | 부분 | E: 결정하지 않은 승인 → `승인 기한 만료`, 명령 미실행. 입력 digest 변경·다른 scope 결정은 host 시험만 있다 |
| AC-16 | PASS | L(1.5)·E: 후보 `파일:줄`·score·정확 계수, 원문 묶음, 연결 못 한 참조 |
| AC-17 | PASS | E·L: 원본 변경 → SOURCE_CHANGED, 머리말 `stale` |
| AC-18 | 부분 | L(1.5): Source·Runtime 목록, 빈 목록 안내, Runtime 다음 목록. 종류 탭·필터는 없다 |
| AC-19 | PASS | L·E: 지정한 경로만 등록, 없는 경로 404 안내 |
| AC-20 | PASS | L(1.5): 해제 뒤 원본 SHA-256 유지. E: 확인창 제목 초점·돌아가기 시 원래 버튼 복귀 |
| AC-21 | PASS | L(1.5): Runtime 저장분만 삭제, 목록·미리보기 비움 |
| AC-22 | PASS | L(1.5): EXPIRED·삭제 안내 |
| AC-23 | PASS | E·L: 4.5 MB/2 MB 원본에서 지정 줄만 읽음. 브라우저가 받은 API 본문 합계는 512 KiB 미만 |
| AC-24 | PASS | L(1.5): 원본 변경 → 미리보기 폐기와 등록 갱신 안내 |
| AC-25 | 부분 | E: 끝 줄 < 시작 줄을 요청 전에 원인별로 안내. JSON 경로 선택자와 8 MiB 초과 JSON은 확인하지 않았다 |
| AC-26 | PASS | E·L: 한국어·영문 검색, 일치 줄 표시 |
| AC-27 | PASS | E·L: 파싱 ready, 2쪽만 읽음, 원본 PDF 쪽·parser 출처, 답변 근거에 PDF 쪽 |
| AC-28 | PASS | E·L: 텍스트 없는 PDF `unsupported`, 손상 PDF `failed`. 암호화·용량 초과 PDF는 4.9 시험만 있다 |
| AC-29 | PASS | E: 파싱 뒤 원본 변경 → 이전 쪽 폐기·갱신 안내, 옛 본문 미표시 |
| AC-30 | PASS | L(1.5): 선택·누락 사유·정확 계수·출처 |
| AC-31 | PASS | E: 창보다 고정 비용이 크면 미리보기와 질문 모두 BUDGET_EXCEEDED, 모델 요청 0회 |
| AC-32 | 부분 | L: 호스트 설정 상태 표시. 설정 변경 뒤 다시 조회와 미설정 시 전송 차단은 확인하지 않았다 |
| AC-33 | 부분 | E: 키보드만으로 질문·승인창, 1280·768·640(200%) 가로 넘침 없음, 768 이하 패널 하나씩, 포인터 선택 접근성 이름. **스크린리더 낭독과 명도 대비 측정은 하지 않았다** |
| AC-34 | PASS | E: 대용량 로그·무관 파일·미선택 PDF 쪽이 provider 요청과 DOM에 없음. H: SSE·SDK 기록(3.6/4.10) |

2.3 수정 요청 처리:
- UI23-01: 1.5 실서비스 화면으로 해소. 현재 결과만 표시한다.
- UI23-02: 1.5에서 검색·범위·선택·목록 조작을 연결했다.
- UI23-03: 1.5 PDF 상태로 해소. 1.6 E2E로 재확인했다.
- UI23-04: 1.6에서 해소. 승인 메타와 대화상자 초점·복귀.
- UI23-05: 1.6에서 해소. 도구 단계, 크기 미확인, 서버 근거 목록.
- UI23-06: 1.6에서 해소. 768px 패널 전환.
- UI23-07: 1.4·1.5 실 API로 해소. 단 AC-02·AC-03의 복구는 남았다.
- UI23-08: 1.6에서 해소. 4,000자 단위 "더 보기", 상태만 live region.
- UI23-09: 1.6 E2E로 실서비스 이력 보존을 확인했다.


## 10. 최종 Mac UI 인수 결과 (2026-11-11 · COMPLETED)

이 절은 9절의 잔여 항목을 현재 구현과 시험으로 갱신한다. 과거의 `부분`·`미구현` 표시는 당시 기록이며 현재 판정에 사용하지 않는다. 전체 34개 인수의 최신 근거와 최종 제품 판정은 [Mac 최종 인수 보고서](../release/ACCEPTANCE_REPORT.md#ui-인수-34개-대응)에 모았다. 화면 구성 대응은 [Figma 화면 구현표](../progress/FIGMA_UI_IMPLEMENTATION_2026-11-11.md), 실제 앱 조작은 [native CUA 기록](../progress/CUA_MAC_ACCEPTANCE_2026-11-11.md)을 따른다.

- 자동 시험은 실제 UI·host·SDK·Python 서비스와 명시적인 시험용 모델 응답으로 수행했다. 실제 모델 시험과 native 앱 직접 조작은 별도 증거다.
- 현재 UI 단위 **50/50 PASS**. 선택 자료의 실제 전송 및 응답 유실 재시도에서 자료·idempotency key가 그대로 유지되는 회귀를 포함한다.
- 포인터 전환 및 PDF 선택 전송 E2E **2/2 PASS**. 이전 줄/검색어가 다음 파일에 남지 않으며, PDF 2쪽 선택 후 패널을 닫아도 실제 모델 입력에는 그 쪽만 포함되고 서버 확인 인용이 표시된다.
- 실제 CSS 명도 대비 **24표본 PASS, 최소 6.100:1**. 입력 placeholder의 초기 3.514:1 결함을 수정했다. [실측 JSON](../progress/evidence/localdesk-macos-contrast.json)에 색상·배경 합성·각 비율을 기록했다.
- 최신 native 앱에서 발견 결함의 재검증을 완료했다. 저장된 대화의 함수·helper·상수 출처, 최신 대화 위치 복원, PDF 2쪽 선택을 유지한 실제 답변 `바다`와 페이지 출처, 모델 양방향 전환, 파일 변경 거절/승인, 실행 취소, 3개 프로젝트 일괄 색인을 직접 확인했다.
- 대화 스크롤 E2E **2/2 PASS**. 복원·새 질문 전송은 최신 위치를 보이고, 사용자가 이전 답변을 읽는 동안에는 위치를 보존한다.
- **VoiceOver의 실제 음성 낭독은 시험하지 않았다.** 키보드·초점·native 접근성 트리의 이름/상태·CSS 명도 대비는 통과했다. 접근성 트리 확인을 음성 출력 확인으로 취급하지 않는다.

| 종전 잔여 인수 | 현재 결과 | 추가된 구현·검증 |
| --- | --- | --- |
| AC-02 인증 복구 | 자동 PASS | cookie 소실 → 새 코드 교환 → 같은 active run 복원, 새 모델 요청 없음. native 재인증 bridge 연결 |
| AC-03 선택·세션 복구 | PASS | 브라우저 reload 및 native 재시작 후 두 번째 프로젝트·새 대화·기존 기록 복원. UserDefaults에는 workspace/session ID만 보존 |
| AC-08 중복·유실 응답 | PASS | create 응답 유실 → reload → 원래 run 복구. 동일 질문·선택 자료 재확인 시 같은 key 재사용, 변경된 자료는 기존 key로 보내지 않음 |
| AC-12 단절·범위 이동 | 자동 PASS | SSE 재연결, active run reload, 완료 run 복구 뒤 추가 질문, 다른 프로젝트의 지연 색인 응답 격리 |
| AC-15 승인 복구 | PASS | 만료·결정 응답 유실 복구·중복 명령 없음. digest 변경·다른 scope 결정 거부는 host 회귀로 확인 |
| AC-18 목록 탭·필터 | PASS | Source/Runtime 종류 탭, 이름 필터, 빈 목록·무결과 구분, 현재 session의 Runtime만 표시. native CUA에서 Source+manual 필터로 PDF만 표시 확인 |
| AC-25 JSON 선택 | PASS | JSON Pointer 값만 반환. 8MiB 초과 JSON 구조 선택 제외와 줄·바이트 안내, 제한된 줄 읽기, 역범위 입력 거절 |
| AC-32 모델 상태 | PASS | 미설정 시 자료 준비 가능·질문 버튼/Enter 차단. 최신 native 앱의 Qwen2.5 ↔ Qwen3.8 cold loading·사용 중 전환·실제 질문·이전 대화 유지 확인. 실행 중 교체는 거부 |
| AC-33 접근성 | 키보드·AX·대비 PASS / 음성 낭독 미검증 | 모달 제목 초점·Escape 복귀·키보드 입력·1280/768/640 너비 검사, CSS 실측 최소 6.100:1, native 접근성 이름/상태 조작. VoiceOver 실제 음성은 시험하지 않음 |

CUA에서 발견한 자료 선택 누락, 포인터 범위 잔류, 과거 답변의 잘못된 모델명, 완료 run 전송 잠금, 프로젝트 간 색인 오류 잔류, 관련 코드 출처 누락, 대화 스크롤 위치를 수정하고 최신 앱에서 재검증했다. UI23-07의 AC-02·AC-03 복구 미구현도 해소됐다. 최종 직접 조작 증거와 검증 범위는 [native CUA 기록](../progress/CUA_MAC_ACCEPTANCE_2026-11-11.md), 제품 전체 판정은 [Mac 최종 인수 보고서](../release/ACCEPTANCE_REPORT.md)에 있다.
