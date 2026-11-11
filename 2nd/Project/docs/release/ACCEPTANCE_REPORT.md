# LocalDesk Mac 최종 인수 보고서

- 작성일: 2026-11-11, Asia/Seoul
- 상태: **COMPLETED — 2026-11-11 19:06 KST, 최신 native 앱 직접 조작과 빌드 검증 완료**
- 대상: 사용자의 현재 Apple Silicon Mac에서 개인용으로 실행하는 프로토타입. 배포·다중 사용자·다른 운영체제 호환은 이번 인수 범위가 아니다.
- 기준: [로드맵](../../INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md), [Figma 화면](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=5-757).
- 최신 사용자 지시는 작업 단위별 commit/push를 명시적으로 허용하며, 이전 문서의 팀원 전용 Git 제한보다 우선한다. 사용한도 리셋권은 사용하지 않았다.

## 실행 산출물

`npm run build:app`으로 `dist/LocalDesk.app`을 생성한다. Finder에서 열면 독립 창, 자동 인증, 로컬 Python 서비스와 Cline SDK 호스트가 함께 시작된다. Command-Q 또는 창 닫기로 자식 서비스를 종료한다. 상세 설치·복구·데이터 보존 안내는 [RUNBOOK](RUNBOOK.md) 4절에 있다.

앱은 현재 checkout과 설치된 Node/Python 환경을 사용한다. 빌드 시 실행 경로를 기록하므로 프로젝트나 Node 경로를 옮기면 다시 빌드한다. 이는 현재 Mac 전용 범위에 맞춘 실행 앱이며 다른 컴퓨터로 복사하는 독립 배포 패키지는 아니다.

앱 데이터는 `~/Library/Application Support/LocalDesk`에 둔다. 이전 `.securecode`의 세션·색인·포인터는 원본을 보존하며 한 번 복사했고, SDK 저장 경로를 새 위치로 옮겼다. 모델 가중치는 기존 프로젝트 경로에 유지한다.

인증 코드·키는 URL이나 브라우저 저장소에 두지 않는다. 앱 재인증은 내부 인증으로 새 일회용 코드를 발급받아 POST로 교환하며 기존 run을 유지한다. UserDefaults에는 선택한 workspace/session ID만 저장한다.

## 검증 환경과 방법

| 항목 | 실제 환경 |
| --- | --- |
| Mac | Apple Silicon arm64, macOS 27.2 |
| Node / npm | 22.14.0 / 10.9.2 |
| uv / Python | 0.9.17 / 3.14.4 |
| 앱 | Swift AppKit + WKWebView, 로컬 ad-hoc 서명 |
| UI | React 19.3.1, Vite 8.3.6 production build |
| SDK | 고정된 `@cline/sdk@0.2.0` |
| 자동 브라우저 | 설치된 Google Chrome, playwright-core, 매 시험 별도 임시 데이터와 빈 포트 |
| 실제 모델 | Qwen2.5-7B-Instruct Q4_K_M (llama.cpp), 기존 Qwen3.8-27B MLX 5bit (LM Studio) |

자동 E2E는 실제 UI·호스트·SDK·Python 서비스를 사용하지만 모델 응답은 명시적인 fixture다. 실제 모델 검증은 별도 live smoke, 실제 모델 전환 API 시험 및 native 앱 CUA로 구분했다. 시간 경과·오류·범위 침범 같은 결정적 조건은 단위/통합 시험으로, 사용자 동작은 브라우저와 CUA로 검증한다.

## 실행한 검사

| 검사 | 최신 결과와 범위 |
| --- | --- |
| `npm run check` | PASS: lint·format·모든 TypeScript 타입·구조·생성 타입·Ruff·mypy·docstring·host/UI/Python 단위 |
| `npm run test:contracts` | PASS: TypeScript 계약 246개 및 Python 계약/응답 249개 |
| `npm run test:integration` | PASS: 실제 서비스 프로세스, 실제 SDK scripted provider, 승인·취소·SSE·포인터·예산, 기동·충돌·정리 |
| `npm run test:install` | PASS 9/9: 새 임시 폴더 설치→시작→등록→종료→재시작→데이터 유지→종료. 사용자 데이터 유지 확인 |
| `npm run test:e2e` | PASS 30/30: 대화 자동 스크롤·수동 위치 유지 및 기존 흐름, 복구·설정·키보드·대비 및 선택한 PDF 범위의 실제 모델 요청 전달 |
| `npm run build:app` | PASS: 생성 계약·host 타입·UI·Python wheel·hash manifest·Swift 앱·서명 |
| 실제 Qwen2.5 smoke | PASS 12/12: 정확 계수 2개 + SDK/도구/근거/승인/취소 10개 |
| 실제 모델 전환 | MLX→GGUF→MLX 모두 HTTP 200/ready. 선택된 모델의 설정과 공유 계수기 변경 확인 |
| 실제 CSS 명도 대비 | PASS 24표본, 최소 6.100:1. placeholder·오류·모달·코드 복사 포함 |

최신 체크의 host 단위는 100/100, 실행 스크립트/이전/정적 UI 서버는 7/7, Python 단위는 256 pass, 1 opt-in live skip, 1 integration deselect였다. UI 단위는 50/50였다. live skip을 실 모델 성공으로 계산하지 않았으며 실제 모델 시험은 별도로 실행했다.

## F1–F11 대응

| 조건 | 판정 | 증거 |
| --- | --- | --- |
| F1 재현 실행 | PASS | `test:install` 9/9, RUNBOOK, native 앱 시작·Command-Q 후 기존 PID/포트 종료 CUA |
| F2 실제 SDK/모델 | PASS | 실제 SDK import·전체 live smoke·MLX/GGUF 교체. 승인/거절/취소는 E2E와 live로 분리 확인 |
| F3 R0 | PASS | 5언어 색인·검색, atomic/bundle 중복 선택 회귀, 변경 revision 차단. CUA 1,009파일 색인; 함수→helper→상수 실제 입력 및3파일 출처·100→110 답변 CUA 확인 |
| F4 Runtime | PASS | SDK history/outbound/SSE descriptor 치환, 저장 실패 차단, 부분 읽기·검색·삭제·TTL·범위 격리 시험. native 1.1MB 로그의 줄 13,579 검색·읽기 |
| F5 Source | PASS | bounded I/O·변경/cursor/경로 거부·등록해제 원본보존. native 2.14MB 텍스트의 줄 25,000 검색·읽기 |
| F6 PDF | PASS | 실제 도구/Skill, 한글 3쪽 PDF parse, 지정 2쪽만 반환·출처. native 2쪽 17 exact tokens. 스캔/손상/암호화 제한 회귀 |
| F7 전체 요청 예산 | PASS | Qwen2.5 34=34/203=203, MLX 59=59/308=308/351=351. 변환된 최종 요청을 계수, 지원 불가/초과 차단 |
| F8 UI·Figma 동작 | PASS | Figma17화면 대응, E2E30, 최신 native CUA. 프로젝트/검색/모델/색인/자료/승인/취소/재시작과 발견 결함 재검증 완료 |
| F9 측정 | PASS | 실 요청 7회와 동일 도구/이력의 계수 전용 대조군. 요청별 최대와 누적 분리. 아래 측정표 |
| F10 유지보수 | PASS | `check`, build, 설치/복구 안내. CUA 발견 차단 결함 수정 및 재검증 완료 |
| F11 역할 종료 | PASS | 대표 체크27개 및1.6/3.8·F1–F11 완료. 사용자 지시에 따라 작업 단위별 commit/push |

## UI 인수 34개 대응

`E`는 현재 Mac의 fixture E2E, `H/P`는 host/Python 회귀, `L`은 실제 모델, `C`는 native CUA다. 과거 Windows 기록은 보존하되 현재 Mac 증거를 우선한다.

| 인수 | 현재 근거 / 최종 확인 |
| --- | --- |
| AC-01 | E: 정상 연결·오류 코드·비밀값 미저장. C: 자동 POST 인증 |
| AC-02 | E: cookie 소실→전용 새 코드→같은 active run 복원, 새 모델 요청 없음. H: 만료/재사용/내부 재발급 인증 |
| AC-03 | E: 등록·없는 경로 거절·reload 선택/세션 복원. C: native 폴더 선택. UserDefaults 재시작 선택 및 실제 모델 복원 CUA 확인 |
| AC-04 | E: 5언어 및 여러 프로젝트 색인, queued 상태/중복 요청 회귀. C: 1,009파일 |
| AC-05 | E: 7개 발견/5개 색인/1개 제외/1개 오류, partial과 path:line 진단 |
| AC-06 | E/H/P: 원본 수정·stale·새 revision·삭제/이동 회귀 |
| AC-07 | E/L/C: 질문·답변·도구 단계·파일/줄/PDF 출처. 안전 Markdown·복사 |
| AC-08 | E: 실행 중 잠금, create 응답 유실 후 reload로 원래 run 복구, 중복 POST 없음 |
| AC-09 | 기존 live와 H/P: 0점 검색·식별자 안내, 전체 원문 fallback 없음 |
| AC-10 | E: 실제 fixture endpoint 500을 실패로 표시, 오류 비밀 본문 미노출 |
| AC-11 | E/L: 취소 후 질문·승인 이력 보존, 실제 실행 중단 |
| AC-12 | E: SSE 두 번 단절/재연결, active reload, 이전 프로젝트의 지연 index 응답 격리. P: queued 상태 정확성 |
| AC-13 | E: 승인 metadata·제목 초점·Escape 복귀·닫기로 결정하지 않음 |
| AC-14 | E/L: 거절 명령 미실행·저장 출력 없음 |
| AC-15 | E: 승인 만료·결정 응답 유실 복구·중복 명령 없음. H: digest 변경/다른 scope/중복 결정 거부 |
| AC-16 | E/L/H/P: R0 후보·범위·점수·계수·연결 불가 참조. 최신 bundle 함수/helper/상수 원문과 출처 CUA 확인 |
| AC-17 | E: SOURCE_CHANGED와 stale 표시, 옛 자료 폐기 |
| AC-18 | Source/Runtime 종류 탭·이름 필터 구현. 자동 목록/선택 및 native 사용 확인; Source탭+manual이름필터 CUA 확인 |
| AC-19 | E/C: 지정한 파일만 등록. 없는 경로/정책 거부 안내 |
| AC-20 | H/P·기존 live: 원본 보존 등록 해제. E: 확인창 초점·돌아가기 |
| AC-21 | H/P·기존 live: Runtime 저장분 삭제와 후속 NOT_FOUND |
| AC-22 | H/P·기존 live: EXPIRED·삭제·세션 정리 구분 |
| AC-23 | E/C: 큰 로그/텍스트에서 요청 줄만, 브라우저 API 총 수신 512KiB 미만 회귀 |
| AC-24 | E/H/P: 변경 원본 미리보기 폐기·갱신 안내 |
| AC-25 | E: JSON Pointer의 선택 값만 반환, 8MiB 초과 구조 선택 제외·안내·제한된 줄 읽기, 역범위 입력 거절 |
| AC-26 | E/C: 한국어/영문 검색, 줄 13,579 및 25,000 확인 |
| AC-27 | E/L/C: PDF ready·지정 2쪽·원본 페이지 출처·정확 토큰 |
| AC-28 | E/P: 텍스트 없는 PDF 미지원, 손상·암호화·용량 상한 명시적 오류 |
| AC-29 | E: parse 뒤 변경 PDF의 옛 쪽 폐기. 포인터 선택 전환의 입력 초기화 회귀 추가 |
| AC-30 | H/P·L: 선택·누락 사유·전체 예산·출처 |
| AC-31 | E: preview/run BUDGET_EXCEEDED, provider 요청 0회 |
| AC-32 | E: 모델 미설정에서도 자료 준비 허용, 버튼/Enter 모두 실행 차단. L: 실제 모델 교체·계수기 교체. 최종 모델 메뉴 양방향 cold load 및 실행 중 교체 차단 CUA 확인 |
| AC-33 | E: 키보드·초점 복귀·1280/768/640 가로 넘침 없음. CSS 24표본 최소 6.100:1. E: AX `status: 완료`, 중복/역순 이벤트 억제 및 답변 토큰별 live-region 미사용. C: 접근성 트리 조작. VoiceOver 실제 음성 낭독을 시험했다는 주장은 하지 않으며 별도 CUA 수행 시 기록 |
| AC-34 | E/H/P/L: 대형 로그·무관 원문·미선택 PDF 페이지가 요청/history/DOM에 없음 |

## 실제 입력량 측정

| 항목 | 보호된 실제 요청 | 원문 대조군(계수만 수행) |
| --- | ---: | ---: |
| 요청 수 | 7 | 7로 고정 |
| 요청별 최대 입력 | 5,399 tokens | 535,104 tokens |
| 세션 누적 입력 | 32,054 tokens | 2,683,291 tokens |
| fixture 원문 | 코드 3,707 bytes, 로그 908,868 bytes, PDF 텍스트 141 bytes | 같은 원문 |

같은 모델 tokenizer와 요청의 도구 정의·이력을 유지하고, 선택 코드 대신 전체 fixture 코드, descriptor 대신 원래 로그, PDF 2쪽 대신 전체 쪽을 넣어 대조군을 계수했다. 대조군은 실제 추론으로 전송하지 않았다. 정확도·속도 향상 또는 모델이 전체 원문을 처리할 수 있다는 주장을 하지 않는다. 요청별 수치와 실패/수정 기록은 [context-measurement.json](../../artifacts/verification/localdesk-mac/context-measurement.json)에 있다.

## 최종 증거

- [native CUA 조작과 결함 수정 기록](../progress/CUA_MAC_ACCEPTANCE_2026-11-11.md)
- [백엔드 실제 모델/계수/전환 증거](../progress/BACKEND_MAC_VERIFICATION_2026-11-11.md)
- [전체 완성 작업 및 초기 감사](../progress/LOCALDESK_MAC_COMPLETION.md)
- [Figma 17개 작업 화면 대응](../progress/FIGMA_UI_IMPLEMENTATION_2026-11-11.md)
- [최종 자동 검사 기록](../progress/evidence/localdesk-macos-validation.json), [검사 요약 로그](../progress/evidence/localdesk-macos-validation.txt)
- [명도 대비 실측](../progress/evidence/localdesk-macos-contrast.json)
- [1.6 UI 검증 기록](../progress/tasks/1.6.md), [3.8 최종 인수 기록](../progress/tasks/3.8.md)

최신 native 앱에서 발견 결함을 수정 후 재확인했다. 양방향 모델 전환과 실제 답변42/42, PDF2쪽 선택→바다 답변/정확한 출처, 파일 쓰기 거절/승인, 실행 중 모델교체 차단과 취소, 실제 개발 폴더 등록 및3프로젝트 일괄 색인, 앱/모델 서버 종료를 확인했다. 마지막 앱은 실제 개발 프로젝트와 Qwen2.5 준비 상태로 열어 두었다. 로드맵27개 및F1–F11을 이 증거에 따라 완료했다.

OCR·암호 해제·원격 배포·다른 Mac/OS 배포·다중 사용자는 범위 밖이다. 원문/PDF의 지시는 비신뢰 자료이며 코드 수정과 명령 실행은 앱의 승인 정책을 통과해야 한다. 실제 로컬 모델의 답변 내용은 비결정적일 수 있다.
