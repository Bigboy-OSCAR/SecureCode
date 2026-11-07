# 통합 시스템 구현 로드맵

> 문서명: `INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md`  
> 저장 위치: `2nd/Project` (저장소 루트 기준)  
> 작성일: 2026-10-27, 기준 시간대: Asia/Seoul  
> 역할 개정일: 2026-10-30 — 김찬우는 UI 설계·문서·검토, 화면 상태 처리는 김민지의 UI 구현에 포함  
> 목표: 네 사람이 아래 자신의 작업을 모두 완료하면, Cline SDK를 사용하는 로컬 코드 작업 도구의 구현·통합·검증·실행 문서가 함께 완성된다.  
> **Git commit과 git push는 팀원이 직접 한다. 모든 작업 프롬프트에서 LLM의 commit/push를 금지한다.**

바로 찾기: [김민지 — UI 6개 작업](#owner-1) · [김찬우 — UI 설계·검토 3개 작업](#owner-2) · [박준형 — R0/SDK/통합 8개 작업](#owner-3) · [임우형 — 포인터/예산/PDF 10개 작업](#owner-4) · [전체 실행 순서](#schedule) · [최종 완료 조건](#acceptance)

## 0. 공통 설계와 실행 규칙

### 0.1 요구 해석과 이번 프로젝트의 완료 범위

김찬우는 **UI 화면 설계·상세 명세·설계 검토**를 담당한다. 별도 UI STM(상태 전이 모델·상태 머신) 설계·구현 작업은 두지 않는다. 화면에 필요한 상태 관리, 사용자 동작 처리와 행동 검증은 **김민지의 UI 구현 작업**에 포함한다.

완성 제품은 사용자가 로컬 프로젝트를 등록하고 색인을 만든 뒤, 질문하거나 승인한 코드 수정·명령 실행을 Cline에 요청하는 로컬 웹 애플리케이션이다. 관련 코드 원문, 등록한 외부 문서/PDF, 실행 결과를 제한된 범위로 읽고 출처와 상태를 UI에서 확인한다. 네 사람에게 배정된 범위에는 설치·실행 스크립트, 오류 처리, 통합 시험, 사용 설명서도 포함한다. 별도의 미배정 “마지막 통합 작업”은 남기지 않는다.

| 포함 기능 | 이번 버전의 정확한 의미 | 최종 책임자 |
|---|---|---|
| Cline SDK | TypeScript 서버가 실제 `@cline/sdk`를 import하고 세션·모델 호출·도구 실행·승인·취소를 연결 | 박준형 |
| R0 symbol_index / Symbol Bundle | 언어별 심볼 원문·정적 참조 → 단일 원문/깊이 3 참조 묶음 → TF-IDF 코사인 검색 → 예산 안 원문 선택 | 박준형 |
| Runtime Pointer | 큰 로컬 도구 출력은 저장하고 짧은 주소·메타데이터로 교체, 필요한 부분만 다시 읽기 | 임우형 |
| Source Pointer | 등록한 디스크 파일의 주소·버전·범위를 관리하고 원문 일부만 읽기 | 임우형 |
| Context Selector | 위 세 자료의 중복·우선순위·토큰 예산을 조정하는 결정적 정책. 새 검색 기법이 아님 | 임우형 |
| PDF 도구·Skill | 텍스트 PDF를 페이지별로 파싱하고 Source Pointer로 제공하는 도구와 사용 지침 | 임우형 |
| UI / API 연동 | 화면·스타일·입력·상태 관리·사용자 동작·미리보기·스트림·API 오류와 UI 수정 | 김민지 |
| UI 설계 / 문서 / 검토 | 화면 구조·사용 흐름·상황별 표시·조작 명세, 설계 문서 작성, 구현 화면 검토와 인수표 | 김찬우 |

**범위에서 제외:** RAPTOR, RF/RH 요약 트리, H의 LLM 후보 선택 단계, 임베딩/벡터 DB, Self-Extend, 별도 에이전트 프레임워크, 클라우드 배포, 다중 사용자 협업, OCR, 암호화 PDF 해제. Cline 내부 기능을 추가 연구 기법으로 부르지 않으며, 암묵적인 컨텍스트 요약/전체 파일 주입은 검증되지 않은 채 켜 두지 않는다.

필수 코드 색인 언어는 **Python, C, C++, Java, JavaScript**다. 단일 언어 프로젝트와 다섯 언어가 섞인 프로젝트 모두 로컬 CLI를 한 번 실행해 색인을 생성할 수 있다. 작업 공간에서 색인을 요청하고 준비 상태를 조회하는 API는 3.3~3.6에서 연결한다. `Workspace.supported_languages`의 계약 값은 각각 `python`, `c`, `cpp`, `java`, `javascript`다. TypeScript는 Source Pointer로 등록해 부분 조회할 수 있다.

| 언어 | 색인 대상 확장자 | 3.3 색인과 3.4 검색에서 확인할 원문 예시 |
|---|---|---|
| Python | `.py` | 최상위 함수·async 함수·클래스·상수, decorator를 포함한 원문과 로컬 import 참조 |
| C | `.c`, `.h` | 함수 정의·원형, 이름 있는 구조체와 상수 및 직접 포함한 로컬 헤더의 참조 |
| C++ | `.C`, `.cc`, `.cpp`, `.cxx`, `.hh`, `.hpp`, `.hxx` | 함수·클래스·상수 및 직접 포함한 프로젝트 헤더의 참조 |
| Java | `.java` | 클래스·인터페이스·enum·record·annotation의 타입 원문(메서드·필드 포함), 패키지와 명시적 import 참조 |
| JavaScript | `.js`, `.mjs`, `.cjs`, `.jsx` | 함수·클래스·이름이 있는 화살표 함수·상수, 명시적인 상대 경로 ESM 및 CommonJS 참조 |

`.h`는 두 문법을 확인한다. C++ 분석이 성공하고 C 구문 오류나 클래스·네임스페이스 같은 C++ 전용 구문이 있으면 C++로, 공통 문법만 있으면 C로 분류한다. 같은 이름이 여러 언어에 있어도 파일과 스코프를 확인한 대상만 연결한다. 메서드는 클래스 원문 안에서 제공해도 된다. 동적 호출이나 대상이 불명확한 참조는 제품에서 `unresolved_reference`로 표시한다. 검색 점수가 모두 0이면 식별자·파일명 입력을 안내한다.

### 0.2 현재 상태와 재사용 원칙

**2026-11-05 기준 구현·검증 현황**

| 영역 | 확인한 동작 | 남은 인수 작업 |
|---|---|---|
| 실행 기반 (3.1·3.2·3.5) | `npm run dev`로 호스트와 Python 서비스를 기동하고 일회용 launch code를 표시한다. 브라우저 cookie 인증, 작업 공간·세션·run·승인·취소·SSE replay를 실제 SDK와 scripted provider로 검증했다. 서비스 종료 후 호스트는 `degraded`를 반환한다. [3.5 검증 기록](docs/progress/tasks/3.5.md) | 운영 세션은 4.4/4.8 hook 연결 전까지 `PROTECTION_UNAVAILABLE`이다. index·pointer route와 live provider smoke는 3.6이 연결한다. |
| R0 (3.3·3.4) | 다섯 언어의 원문·정적 참조를 로컬 JSON 또는 작업 공간별 revision으로 생성한다. 변경·이동·삭제 뒤 새 revision으로 원자적으로 전환하고, 이전 revision과 바뀐 파일의 원문 요청은 `SOURCE_CHANGED`로 거부한다. [3.3 검증 기록](docs/progress/tasks/3.3.md) | Python `R0SymbolService`의 TF-IDF 검색·예산 내 원문 묶음과 `ready` 전환은 완료했다. [3.4 검증 기록](docs/progress/tasks/3.4.md). 내부 route·host·index API 연결(3.5/3.6)이 남았다. |
| 포인터 (4.3~4.6) | 인증된 레거시 Runtime API의 세션 격리·부분 읽기, 실제 SDK 훅의 큰 출력 교체, 메모리 Source 등록부의 파일 변경 감지를 검증했다. | 정식 서비스 API, 운영 SDK·SSE 연결, Source 등록부 영속화와 범위 검색 |
| UI (1.1·2.2) | 9개 화면·34개 사례에 표시 항목과 사용자 조작을 정의했다. 범위 선택, 자료 등록·삭제, PDF, 예산 미리보기, 재연결 시 출처·승인 이력 복구를 공개 계약 예시와 대조했다. [2.2 검증 기록](docs/progress/tasks/2.2.md) | 1.1을 마치면 1.2에서 이 사례로 화면을 구현하고, 1.3에서 사용자 행동을 시험한다. |

기반 기능과 다섯 언어 색인을 검토했을 때 Python 테스트 206개, 호스트 단위 테스트 47개, TypeScript 계약 테스트 142개, 오프라인 SDK 검사 62개가 통과했다. Python 전체 수치에는 Python 계약 시험이 포함된다. 실제 외부 모델 호출과 이번 변경의 Windows 실행 검증은 후속이며 Windows용 Python 정적 타입 검사는 통과했다. [명령별 검증 상태](docs/architecture/ARCHITECTURE.md#7-개발-명령)

아래 실험 자료는 최초 설계의 출발점이다. 제품에 이식한 범위와 남은 조건은 해당 작업의 검증 기록에서 확인한다.

| 기존 자료 | 재사용할 내용 | 제품화 시 보완할 점 |
|---|---|---|
| `../../1st/symbol_test/symbol_bench/indexer.py` | Python AST와 원문 위치 추출의 출발점 | 전체 outline을 LLM에 주는 옛 경로 금지, 파일 갱신/오류 격리 |
| `../experiments/symbol_raptor/experiment.py` | `source_nodes`, `closure`, `fragment`, `raw_items`, `words`, `Retriever`, `pack`의 R0 관련 논리 | 함수별 이식, 버전·상한·경로 정책; `build_assets` 전체 실행 금지 |
| `../experiments/symbol_raptor/experiment_r0.py` | `CONFIG`와 `prepare`의 R0 전용 흐름 | 벤치마크 실행기·정답 파일에 제품이 의존하지 않게 분리 |
| `../../1st/runtime_pointer_test/runtime_pointer_bench/runtime_tools.py` | 저장 후 제한된 추출이라는 원리 | 4자리 ID/dict 저장을 교체, 삭제/TTL/세션 격리/디스크 저장 |
| `../../1st/source_pointer_test/source_pointer_bench/source_tools.py` | 등록된 원본을 해석하는 원리 | 전체 `read_text()` 대신 범위 읽기, 버전 확인, 한글 처리 |

`experiment.py`라는 경로에 RAPTOR가 있어도 가져올 것은 R0 함수뿐이다. R0의 사전 요약 호출과 LLM 후보 선택 호출은 **0회**다. LLM은 최종 코드 작업 및 도구 사용을 수행한다. R0 검색을 A/B의 “LLM이 출발 심볼 선택”이나 H의 “후보 목록을 LLM이 재선택”으로 바꾸지 않는다. 실험의 1,024토큰은 제품의 고정 한도가 아니며 4.8의 모델별 예산 설정으로 대체한다.

### 0.3 기술 구조와 소유권

**구현 기본안:** React + TypeScript + Vite UI, Node.js TypeScript Cline 호스트, Python FastAPI 컨텍스트 서비스. Python은 기존 연구 코드와 코딩컨벤션을 유지하고, TypeScript 호스트는 검증된 SDK 언어를 사용한다. Python 프로세스가 Cline SDK인 것처럼 설명하지 않는다.

```text
브라우저 UI·화면 상태·사용자 동작 (김민지) ← 화면 설계·표시 명세 (김찬우)
    │ HTTP JSON + SSE: /api/v1
    ▼
Node Cline 호스트 (박준형)
    ├─ ClineCore 세션 / 승인 / 취소 / 이벤트 / 실제 모델 호출
    ├─ 로컬 도구 registry / beforeModel 조기 검사 / fetch 최종 예산 검사
    ├─ afterTool 결과 교체 연결 ── Runtime 정책 (임우형)
    └─ 인증된 loopback HTTP ────── Python context-service
                                  ├─ symbols: R0 원문 검색 (박준형)
                                  ├─ runtime / source / pdf (임우형)
                                  └─ context: 선택·예산 정책 (임우형)
```

브라우저는 Python 서비스나 모델 provider를 직접 호출하지 않는다. API 키는 서버 환경에만 둔다. 두 서버는 `127.0.0.1`에 바인딩하고, 내부 서비스는 시작 시 생성한 비밀 토큰으로 보호한다. UI API는 같은 origin과 세션을 검증한다. 최초 브라우저 연결은 launcher가 로컬에 표시한 일회용 코드를 `POST /api/v1/auth/bootstrap`으로 교환하고 HttpOnly·SameSite=Strict cookie를 발급하는 방식으로 고정한다. SSE도 같은 origin cookie를 사용하며 개발 환경은 Vite proxy로 origin을 맞춘다. 코드/키/내부 서비스 토큰을 URL query·VITE 환경변수에 넣지 않는다. 모델에 전달할 문서·코드·로그는 비신뢰 데이터로 표시하며 그 안의 지시가 도구 승인 정책을 바꾸지 못하게 한다.

| 경계 | 단일 수정 책임 | 다른 사람의 사용 방식 |
|---|---|---|
| 루트 실행/검사 설정, lockfile, 호스트 조립, `/api/v1`, 공통 이벤트 | 박준형 | 필요한 의존성/계약 변경을 `docs/handoffs/`에 기록; 무단 병행 수정 금지 |
| `contracts/pointers`, `contracts/context`, Python 포인터·PDF, `apps/host/src/pointer-hooks`와 Runtime Pointer SDK 플러그인 | 임우형 | 박준형의 SDK adapter 포트에 붙이고 UI에는 DTO만 노출 |
| `docs/ui/{SCREEN_SPEC,UI_BEHAVIOR,ACCEPTANCE}.md`, UI 검토/인계 문서 | 김찬우 | 화면·표시·조작 요구를 문서로 제공; 상태 관리 코드와 실행 타입은 작성하지 않음 |
| `apps/ui/src/{features,hooks,components,api,styles}`, UI 행동 시험·E2E | 김민지 | 설계 명세와 생성된 API 타입을 사용해 화면 상태·사용자 동작·통신을 구현 |
| `context-service/src/securecode_context/symbols` | 박준형 | 임우형은 공통 Candidate 계약을 통해 사용 |

**경로 기준:** 저장소 루트는 현재 checkout에서 `1st/`와 `2nd/`가 있는 디렉토리다. 작업 루트는 저장소 루트 기준 `2nd/Project`이며, 이 문서가 있는 폴더다. 먼저 이 작업 루트로 이동한 뒤 작업한다. 이미 작업 루트에 있다면 다시 `2nd/Project`를 덧붙이지 않는다. 별도로 “저장소 루트 기준”이라고 표시한 경로 외에는 문서·프롬프트의 파일 경로와 명령을 작업 루트 기준으로 해석한다. 예를 들어 `docs/`는 저장소 루트 기준 `2nd/Project/docs/`, `../experiments/`는 저장소 루트 기준 `2nd/experiments/`를 가리킨다. Markdown 파일 링크도 이 문서 위치를 기준으로 해석한다. 특정 사용자 홈·컴퓨터의 경로를 코드·문서·프롬프트에 하드코딩하지 않는다.

사용자의 미커밋 변경, 기존 실험, 다른 사람의 작업을 덮어쓰지 않는다. 공유 파일 변경이 필요하면 해당 작업의 계약을 먼저 확인하고 최소한으로 수정한다. 별도 병렬 checkout을 사용한 경우 통합할 때에도 담당자가 수동 Git 작업을 수행한다.

### 0.4 Cline SDK 연결에서 반드시 지킬 점

3.1은 공식 소스 ref `775d0398039977ca5447ed39c1a7f178df69aa87`와 실제 설치한 `@cline/sdk@0.2.0`의 타입·실행 동작을 대조했다. 제품은 루트 `package-lock.json`으로 SDK를 고정한다. 저장된 증거를 보존하면서 재검증하려면 `npm run probe:sdk -- --no-evidence`를 실행한다. [검증된 SDK 확장점](docs/architecture/SDK_COMPATIBILITY.md)

- `ClineCore.create/start/send/subscribe/abort/stop/dispose`와 typed `hooks.afterTool`, `beforeModel`이 공식 표면에서 확인됐다. 실제 사용하는 인자·반환값은 설치 버전의 `.d.ts`로 확정한다. 검증되지 않은 `onToolResult` 등을 만들어 “SDK API”라고 쓰지 않는다.
- `afterTool`에서 **`result`를 교체**한다. `appendContext`만 추가하거나 UI에서 원문을 숨기는 것은 Runtime Pointer 적용이 아니다. SDK canonical history와 다음 provider 요청에도 원문이 남지 않는지 검사한다.
- MVP 도구 실행은 SDK의 **로컬 실행 경로**로 제한한다. provider 측 원격 실행 도구는 이 hook을 통과한다고 보장할 수 없으므로 비활성화한다. Cline CLI subprocess를 호출하는 것으로 SDK 사용을 대체하지 않는다.
- 큰 출력은 가능하면 프로젝트 소유 executor에서 스트리밍 저장하고 짧은 결과를 반환한다. `afterTool`은 나머지 로컬 결과를 처리한다. SDK가 먼저 잘라 버린 출력을 “원본 전체 저장”이라고 표시하지 않는다.
- pointer hook 오류는 `hookErrorMode: "throw"` 등 설치 버전에서 확인한 실패 차단 설정으로 처리한다. 기본 오류 무시/시간초과 후 원문 전달을 허용하지 않는다. 기본 hook timeout에 기대지 말고 최대 저장 크기·시간·취소 규칙을 정한다.
- 모든 허용 도구에 `toolPolicies`를 명시한다. 코드 수정·명령 실행은 승인 요청을 UI로 보내고, 거절/취소 시 실행하지 않는다. 자동 승인 기본값에 기대지 않는다.
- Core의 `capabilities.requestToolApproval`에서 앱이 승인 ID·입력 digest·만료시간을 생성한다. 취소/세션 종료/timeout 때 대기 Promise를 종료하고 늦은 승인을 거절한다. Core의 `CoreSessionEvent`와 하위 Agent 이벤트를 혼동하지 말고 설치 타입을 기준으로 AppEvent에 매핑한다.
- 필수 pointer/budget hook의 등록·준비가 확인되지 않으면 세션 시작을 차단한다. `hookErrorMode`만으로 미등록 hook이 보장되지는 않는다. 자동 사용자 MCP 설정 도구 유입·spawn agent/teams·미승인 plugin은 검증된 설정으로 비활성화하고 허용 도구 집합을 고정한다.
- `checkpoint: { enabled: false }`와 로컬 backend 설정을 검증해 SDK가 Git 상태를 자동 변경하지 않게 한다. 프로젝트 도구의 commit/push 실행도 금지한다.
- `beforeModel`은 요청을 관측하고 조기에 차단한다. 3.1에서 확인한 최종 차단 지점은 provider 요청 본문이 직렬화된 뒤의 `ClineCoreOptions.fetch`다. 4.8은 이 지점에서 전체 요청의 예산을 검증한다. `prepareTurn`의 요청 투영과 저장된 대화 이력 변경을 혼동하지 않는다. 같은 자료를 최초 프롬프트·hook·도구 결과에 중복 삽입하지 않는다.
- 기본 읽기/코드 검색 도구가 전체 저장소·거대한 파일을 우회 전송하지 않도록 허용 목록과 wrapper를 고정한다. 기존 내장 도구를 교체/비활성화하는 실제 방법 역시 3.1에서 확인한다.

지원 불일치가 발견되면 3.1/3.5에서 같은 Cline SDK의 공개 API로 대안을 검증한다. 불가능한 기능을 가짜로 구현하거나 다른 SDK로 바꾸지 않는다. 해결하지 못한 필수 기능은 `BLOCKED`로 기록하고 후속 작업을 완료 처리하지 않는다.

### 0.5 올바른 디렉토리 구조와 파일 분할

아래는 **최종 목표 구조**다. 현재 생성한 패키지와 모듈별 담당은 [아키텍처 문서](docs/architecture/ARCHITECTURE.md)에 기록한다. 파일을 먼저 전부 빈 껍데기로 만들지 말고, 해당 담당 작업에서 필요한 모듈을 만든다.

```text
Project/
├── INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md
├── CODING_CONVENTIONS.md                  # 기존 Python 규약 보존
├── README.md
├── package.json                          # 공통 명령; 박준형 소유
├── package-lock.json
├── .env.example                          # 키 값 없는 이름/설명만
├── .gitignore
├── docs/
│   ├── architecture/{SDK_COMPATIBILITY,ARCHITECTURE,POINTER_DESIGN,CONTEXT_SELECTOR}.md
│   ├── contracts/{API,EVENTS,POINTERS,CONTEXT}.md
│   ├── conventions/TYPESCRIPT_REACT.md
│   ├── ui/{SCREEN_SPEC,UI_BEHAVIOR,ACCEPTANCE}.md
│   ├── handoffs/                         # 계약 변경/담당자 인계
│   ├── progress/tasks/                   # 1.1.md 등 작업별 검증 기록
│   └── release/{RUNBOOK,ACCEPTANCE_REPORT}.md
├── contracts/
│   ├── common/                          # error, version, pagination
│   ├── api/                             # 프로젝트/세션/승인/실행
│   ├── events/                          # SDK와 독립된 앱 이벤트
│   ├── symbols/
│   ├── pointers/
│   ├── context/
│   └── fixtures/                        # 성공/오류/호환성 샘플
├── apps/
│   ├── ui/src/
│   │   ├── app/                         # 초기화/라우팅만
│   │   ├── hooks/                       # 김민지: 공통 상태·구독 처리
│   │   ├── features/                     # project/chat/context/pointers/approvals/settings
│   │   │   └── <기능>/{components,model,hooks}/  # 김민지: 화면·상태·사용자 동작
│   │   ├── components/                  # 공용 UI만
│   │   ├── api/{client,events,mappers}/
│   │   └── styles/
│   └── host/src/
│       ├── app/                         # 서버 조립/수명주기만
│       ├── routes/{projects,sessions,runs,pointers,context,approvals}/
│       ├── cline/{adapter,plugins,tools,events,permissions}/
│       ├── context-client/
│       ├── pointer-hooks/               # 임우형
│       └── config/
├── services/context-service/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/securecode_context/
│   │   ├── app/                         # DI/기동만
│   │   ├── api/                         # 입력 검증/라우팅만
│   │   ├── common/                      # 오류/경로/저장 공용
│   │   ├── symbols/{parser,index,graph,retrieval,bundle}/
│   │   ├── pointers/{models,registry,runtime,source}/
│   │   ├── context/{models,policy,budget}/
│   │   └── pdf/{parser,cache,tools}/
│   └── tests/{unit,contract,integration}/
├── skills/pdf-pointer/SKILL.md
├── scripts/                             # dev/check/stop/구조 검사
├── tests/{contracts,integration,e2e,fixtures}/
├── artifacts/verification/              # 검증 결과; 원문/키 제외
└── .securecode/                          # 실행 데이터; Git 제외
    ├── workspaces/<workspace_id>/        # registry/index/PDF 파생 캐시
    └── runtime/<workspace_id>/<session_id>/
```

**파일 규칙:** 직접 작성하는 production source 한 파일은 원칙적으로 300줄 이하, 테스트 파일은 500줄 이하로 제한하고 기능별로 분리한다. 함수 60줄·React 컴포넌트 150줄을 분리 검토 기준으로 삼는다. 생성 코드/lockfile/fixture/문서는 줄 수 제한에서 제외하되 생성물 디렉토리를 분리한다. 길이 검사를 피하기 위해 줄을 압축하거나 `utils` 한 파일로 모으지 않는다. 예외가 꼭 필요하면 해당 작업 증거에 이유와 분리 불가 사유를 기록하고 3.7에서 해소 여부를 판정한다.

한 파일에 UI·네트워크·화면 상태 처리·SDK·파서·DB 코드를 혼합하지 않는다. `main`, `App`, `__init__`, `index`는 조립과 공개 export만 담당한다. feature 간 순환 import를 금지한다. 실험 스크립트 전체 복사, `sys.path`로 실험 폴더를 끌어오는 방식, 제품 루트의 `temp.py`/`test2.ts` 같은 임시 파일을 금지한다.

**코딩컨벤션:** Python은 기존 `CODING_CONVENTIONS.md`를 반드시 지킨다. 클래스 PascalCase, 함수/변수 snake_case, 공백 4칸, 함수·클래스 설명 docstring에 규약의 필드와 실제 작성 날짜를 포함한다. TypeScript는 3.2에서 별도 보완 규약을 작성한다: strict 모드, 함수/변수 camelCase, 타입/컴포넌트 PascalCase, ESLint/Prettier, 의미 없는 `any` 금지, 비동기 오류 명시, 네트워크 타입 검증. JSON 전송 필드는 snake_case로 고정하고 UI 변환은 mapper 한 곳에서 한다. Python 문법을 TypeScript에 억지로 적용하지 않는다.

<a id="06-공유-데이터api-계약-초안"></a>

### 0.6 공유 데이터·API 계약과 연결 범위

3.2의 공통 계약과 4.2의 포인터·컨텍스트 계약은 `contracts/`의 JSON Schema를 기준으로 한다. 다음 표는 버전 1의 주요 필드를 요약한다. 소비자는 생성 타입 또는 같은 스키마로 검증한다. 뒤의 API 표에는 운영 연결을 기다리는 경로도 포함된다. [공개 API 명세](docs/contracts/API.md) · [포인터 명세](docs/contracts/POINTERS.md)

| DTO | 최소 필드/의미 |
|---|---|
| Workspace | `workspace_id`, `display_name`, `index_revision`, `index_status`, `supported_languages`; 실제 절대경로는 서버 내부 |
| SymbolCandidate / SymbolBundle | 후보는 `candidate_id`, `primary`, `symbol_ids`, `score`, `index_revision`, `estimated_tokens`를 담는다. 묶음은 `fragments`, `omissions`, `unresolved_references`, `token_count`로 원문·출처·누락을 전달한다. |
| PointerDescriptor | `pointer`, `kind`(source/runtime), `workspace_id`, `revision`, `media_type`, `byte_size`, `preview`, `available_operations`, `provenance`; runtime에 `session_id`, `expires_at` |
| PointerReadRequest | `pointer`와 선택 필드 `selector`, `max_bytes`, `max_tokens`, `cursor`. 범위는 구조화된 selector로 전달한다. |
| PointerReadResult | `content`, `provenance.revision`, `truncated`, `next_cursor`, `token_count`, `count_mode`. cursor는 scope·revision·연산에 묶는다. |
| ContextCandidate | `candidate_id`, `ref`, `score`, `explicit`, `estimated_tokens`. 심볼·Source·Runtime 참조의 종류는 `ref.kind`로 구분한다. |
| ContextPlan | `selected`, `fragments`, `omitted`, `index_revision`. 사용 토큰과 계수 방식은 `budget.used_tokens`와 `budget.count_mode`에 들어간다. |
| AppEvent | `schema_version`, `event_id`, 단조 증가 `sequence`, `workspace_id`, `session_id`, `run_id`, `type`, `timestamp`, `payload` |
| ApiError | `code`, 사용자용 `message`, `retryable`, `request_id`, 선택적 `details`; 내부 경로/키/대형 원문 노출 금지 |

정식 URI는 `securecode://source/<workspace_id>/<source_id>?v=<revision>`와 `securecode://runtime/<workspace_id>/<session_id>/<pointer_id>?v=1`이다. 서비스는 URI의 종류·범위·버전을 인증된 요청과 등록 기록에 대조한다. Source descriptor에는 `session_id`와 `expires_at`을 허용하지 않는다. 실제 파일 경로는 registry에서 관리한다. 심볼과 PDF 페이지는 Source provenance로 원본을 식별한다.

| UI가 호출할 API / 동작 | 구현 책임 |
|---|---|
| `POST /api/v1/auth/bootstrap`, `GET /api/v1/health`, `GET /api/v1/settings` (비밀값 제외) | 박준형 3.5 |
| `POST /api/v1/workspaces`, `POST /workspaces/:id/index`, `GET /workspaces/:id/index` | 박준형 3.5/3.6 |
| `POST /api/v1/sessions`, `POST /sessions/:id/runs`, `GET /runs/:id`, `GET /runs/:id/events`, `POST /runs/:id/cancel` | 박준형 3.5 |
| `POST /api/v1/runs/:id/approvals/:approval_id` | 박준형 3.5; 승인 요청 ID와 도구 입력 digest 검증 |
| `GET /api/v1/workspaces/:id/pointers`, `POST /workspaces/:id/sources`, `POST /pointers/read`, `POST /pointers/search`, `DELETE /pointers` | 임우형 서비스 4.3~4.6, 박준형 공개 route 연결 3.6 |
| `POST /api/v1/context/preview`, `POST /api/v1/pdf/parse`, `GET /api/v1/pdf/jobs/:id` | 임우형 4.8/4.9, 박준형 route 연결 3.6 |

표의 축약 경로는 모두 `/api/v1` 아래다. 현재 호스트에서 동작하는 공개 경로는 health이며, 계획된 업무 경로는 연결 전까지 501을 반환한다. 포인터 URI를 URL path에 직접 붙이지 않는다. `DELETE /pointers`의 JSON 본문은 pointer와 scope를 가지며 호스트/프록시도 해당 계약을 검증한다. Source 삭제는 **등록 해제와 파생 캐시 삭제**이며 사용자 원본 파일을 삭제하지 않는다. Runtime 삭제는 저장한 실행 결과만 지운다. PDF는 PdfParseRequest로 요청하고 job ID로 PdfJobStatus를 조회한다. 2.2는 대기·처리 중·완료·일부 제외·미지원·실패·원본 변경의 화면 동작을 인계한다. [계약과 예시](docs/handoffs/2.2-ui-behavior-contract-gaps.md)

내부 서비스 포트는 `symbols.build_index/search/read_bundle`, `runtime.put/stat/list/read/search/delete/clear_session`, `source.register/stat/list/read/search/unregister`, `context.select`, `pdf.parse/status/read_pages`, 내부 공용 `tokens.count`로 나눈다. Runtime put/세션 정리 같은 관리 기능을 모델에 모두 공개하지 않는다. 모델에는 필요한 검색/부분 조회 도구만 노출한다. 기본 본문 TokenCounter는 3.2가 실행 가능한 구현으로 제공하고, provider framing을 포함한 최종 요청 검사는 4.8이 확장한다. 따라서 포인터/R0 모듈이 후속 Selector를 기다릴 필요가 없다.

세션당 동시 실행은 1개다. 중복 run 생성은 `idempotency_key`로 같은 결과를 반환한다. SSE 연결 끊김은 실행 취소와 다르다. 재연결은 `Last-Event-ID`로 중복 이벤트를 걸러 복원하며, replay 보존 범위를 벗어나면 run snapshot을 다시 읽는다. 종료는 `completed/failed/cancelled` 중 하나만 확정하고 늦은 이벤트가 이를 되돌리지 못한다. 취소는 `cancelling`을 거쳐 SDK 확인 후 `cancelled`가 된다.

페이지 계약에서 `has_more=true`이면 다음 cursor가 필요하다. 포인터 검색 결과는 최대 100개이며, `truncated`와 `next_cursor`로 이어 읽기를 표시한다. 서비스는 목록·검색·R0 후보 응답에 정해진 크기 한도를 적용한다. 모델뿐 아니라 SDK 이벤트→AppEvent→SSE에서도 전체 도구 원문을 통과시키지 않는다. 로그/디버그 모드가 이 규칙을 우회하지 않게 한다.

공통 결과 코드에는 `INVALID_POINTER`, `NOT_FOUND`, `EXPIRED`, `FORBIDDEN`, `SOURCE_CHANGED`, `INVALID_SELECTOR`, `UNSUPPORTED_FORMAT`, `UNSUPPORTED_LANGUAGE`, `PARSE_FAILED`, `NO_MATCH`, `BUDGET_EXCEEDED`, `TOKENIZER_UNAVAILABLE`, `SDK_UNAVAILABLE`, `PROVIDER_ERROR`, `APPROVAL_REJECTED`, `CANCELLED`가 있다. 검색 결과가 없으면 HTTP 200으로 응답한다. 심볼 검색은 빈 `candidates`와 `no_match.reason_code="NO_MATCH"`를, 포인터 검색은 `matches: []`를 반환한다. 오류 상태와 기본 재시도 여부는 [공통 코드표](contracts/common/error-codes.json)를 따른다.

### 0.7 예산·저장·부분 읽기 기준

도구 출력을 포인터로 교체하는 기준과 포인터를 한 번에 읽을 수 있는 양은 따로 관리한다.

- **도구 출력 교체 (4.4)** — 현재 SDK 훅은 UTF-8 **4,096바이트 이상**을 저장하고 결과를 교체한다. 3.1에서 SDK가 8,000자를 넘는 출력을 자르는 경로를 확인했으므로, 초기 제안인 16 KiB를 적용하려면 먼저 원문 보존 경로를 검증해야 한다. 운영 임계값과 스트리밍 저장 정책은 4.4에서 인수한다.
- **포인터 부분 읽기·검색 (4.2)** — 요청 상한은 `max_bytes` 16,384바이트와 `max_tokens` 32,768토큰이다. 응답은 요청된 두 한도를 모두 지킨다. preview는 최대 512 UTF-8바이트다. R0 `SymbolBundleRequest.max_bytes`의 상한은 별도로 32 KiB다. [포인터 조회 계약](contracts/pointers/read.schema.json) · [심볼 묶음 계약](contracts/symbols/symbol.schema.json)
- **제품 저장·파싱 목표** — Runtime 객체 32 MiB, 세션 합계 128 MiB, 기본 TTL 24시간, Source 파일 256 MiB, JSON 구조 조회 8 MiB, PDF 50 MiB·500페이지다. 각 구현 작업에서 적용 여부와 초과 시 오류를 검증한다.

- Runtime은 SQLite 메타데이터 + 개별 blob 등 원자적 파일 저장을 사용한다. 임시 파일→완료 rename, 오류/취소 시 정리, 세션 격리, TTL sweep, 재시작 시 정합성을 지원한다. 프로세스 dict만으로 완료 처리하지 않는다.
- Source는 등록 시 root/경로 허용을 검증한다. 프로젝트 외부 자료는 UI에서 사용자가 지정한 파일/디렉토리만 허용 목록에 등록한다. symlink와 `..` 경로 이탈을 차단하고 stat/hash/revision으로 오래된 원문을 감지한다. 모든 요청에서 거대한 파일을 재해시하지 않도록 정책을 명시한다.
- Text/log/Markdown은 줄 오프셋 인덱스·seek·streaming을 사용한다. 최초 색인/검색은 순차 scan일 수 있으나 bounded memory를 지키고, 반복 범위 조회는 파일 전체를 다시 읽지 않는다. 실제 읽은 bytes/최대 chunk 크기로 이를 입증한다.
- JSON 구조 경로 조회는 위 크기 이하만 파싱하는 MVP다. 큰 JSON의 byte/line 읽기와 임의 JSON path 부분 I/O를 구분한다. 무제한 JSON path 지원이라고 쓰지 않는다.
- PDF는 최초 페이지 추출과 캐시 생성이 필요하다. 이후 요청한 페이지의 텍스트만 제공하고 원본 hash/parser version/page를 보존한다. 스캔/빈/손상/암호화 문서는 지원 상태 또는 오류를 명확히 반환한다.
- read 결과가 다시 포인터로 무한 포장되지 않도록 `bounded_read` 도구를 구분한다. 초과하면 cursor로 나누고 원문 preview를 무제한 반복하지 않는다.

각 모델 요청의 컨텍스트 예산은 다음 식으로 계산한다.

```text
available_context = model_context_limit
                  - tokens(system + tool_schema + user + retained_history + message_overhead)
                  - reserved_output_tokens - safety_margin
```

사용자 명시 선택 → 현재 요청과 연결된 도구 결과/자료 → R0 점수 순으로 선택하고 동점은 안정적인 ID 순으로 처리한다. 명시 선택도 예산을 넘길 수 없다. 먼저 권한/버전 검사, 이어서 같은 source hash+range 중복 제거, 마지막에 토큰 한도 안 선택을 한다. 점수가 다른 검색기끼리 임의 비교되지 않도록 source별 priority와 정규화 기준을 4.7에서 명시한다. 전체 history가 이미 한도를 넘으면 `BUDGET_EXCEEDED`로 중단하고 새 세션/범위 축소를 안내한다. 새로운 요약기를 자동 추가하지 않는다.

최종 직렬화된 모델 입력도 다시 계수한다. **beforeModel 이후 provider message 변환·tool framing이 추가될 수 있으므로 그 hook에 검사가 있다는 사실만으로 최종 입력 hard cap을 보장하지 않는다.** 3.1에서 최종 HTTP 본문의 관측·차단을 검증했다. 3.2의 본문 토큰 계수는 단일 메시지에 대한 provider 추정값이며, 전체 요청·framing의 계수와 예산 적용은 4.8의 인수 범위다. 검증 전에는 요청 추정 예산이며 exact라고 표시하지 않는다. tool-call과 tool-result 쌍을 깨뜨리지 않는다. 정확한 계수/최종 차단을 지원하지 못하는 모델은 hard-cap 보장 모드에서 `TOKENIZER_UNAVAILABLE` 또는 명시적 미지원으로 차단한다. 문자열 길이/4를 실제 토큰 수라고 보고하지 않는다. 원문 전송량 비교는 동일 fixture·동일 tokenizer·동일 응답 예산의 원문 baseline과 수행한다.

### 0.8 한 작업을 실행하고 체크하는 방법

1. 각 작업 첫 줄의 **선행 조건**을 확인한다. 다른 사람의 선행 작업도 `[x]`이고 증거 파일이 존재해야 한다. 같은 번호가 낮다고 먼저 실행하는 것이 아니다.
2. 해당 작업의 `text` 코드 블록 **하나를 통째로** LLM에 붙여넣는다. 공통 프롬프트를 따로 조립하거나 ID를 치환할 필요가 없다. 작업 목적·입력·수정 범위·시험·종료 처리가 포함되어 있다.
3. LLM은 구현/설계와 관련 검증을 끝낸 뒤 `docs/progress/tasks/<작업번호>.md`에 결과를 저장한다. 이후 해당 작업의 완료 조건과 대표 `완료` 체크박스를 `[x]`로 바꾼다.
4. 미완료 선행조건, SDK 불일치, 실패 시험, 필수 live 검증의 비밀값 부재, mock만 성공한 실연동 작업은 체크하지 않는다. 증거 파일에 `BLOCKED` 또는 `IN_PROGRESS`, 원인, 재개 방법을 쓴다. 다른 독립 작업은 진행할 수 있다. **3.1/3.5의 실제 SDK+scripted provider 검증은 정식 완료 기준이므로 live 키 없이 완료할 수 있다.** 실제 provider 필수 작업은 3.6 이후 해당 조건이 명시된 항목이다.
5. 같은 프롬프트를 다시 실행하면 기존 구현과 증거를 읽고 남은 범위만 처리한다. 현재 코드를 지우고 처음부터 만들지 않는다. 완료 항목의 회귀는 원래 담당자가 자기 체크를 다시 열고 이유·수정·재검증을 기록한다. 다른 담당자는 재현 자료를 인계하고 자신의 의존 작업을 BLOCKED로 유지하며 타인의 체크를 직접 바꾸지 않는다.

작업 증거는 `task_id / owner / status / started_at / completed_at / dependencies / changed_files / commands_and_results / acceptance_evidence / limitations / next_handoff`를 포함한다. 실행하지 않은 검증을 통과로 쓰지 않는다. 로그에는 API 키·사용자 원문·절대 개인 경로를 제거한다. 로드맵의 해당 항목 외에 다른 사람의 체크를 임의 변경하지 않는다.

**정의상 작업 완료 = 담당 산출물 존재 + 해당 완료 조건 검증 + 증거 기록 + 다음 담당자가 바로 사용할 공개 계약 존재.** 설계 작업은 구현 대신 화면 명세/스키마/사용 사례의 검증이 기준이다. 부분 검증이 있는 작업은 검증한 동작과 남은 인수 조건을 각각 기록한다.

3.2의 공통 명령은 `npm run dev`, `npm run stop`, `npm run check`, `npm run test:unit`, `npm run test:contracts`, `npm run test:integration`, `npm run test:e2e`, `npm run test:live`, `npm run build`다. 2026-11-05 재검증에서 계약 검사는 종료 코드 0이다. `check`·단위·통합·빌드는 구현분이 통과했고 UI·제품 통합·배포 등 각 명령의 남은 항목 때문에 코드 3을 반환했다. UI E2E는 대기 중이며 외부 모델 검사는 명시적으로 켠 경우에만 실행한다. [실행 방법](README.md)

<a id="owner-1"></a>

## 1. 김민지의 역할 — UI 코드 작성·수정·API 연동

UI 표현·화면 상태·사용자 동작·API 연결을 소유한다. 김찬우의 화면 설계와 박준형의 공개 API를 기준으로 구현하고, 서버의 실행 상태와 정책을 화면에서 별도로 재정의하지 않는다.

### 1.1 UI 실행 기반과 공용 컴포넌트 만들기

**선행 조건: 김찬우 2.1번 + 박준형 3.2번 작업이 모두 완료된 이후에 진행.**

- [ ] **1.1 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 화면별 구현이 제각각 시작되면 스타일·접근성·설정이 중복된다. 확정된 화면 설계를 바탕으로 React 실행 기반과 공용 표현 요소를 먼저 만들어 뒤의 화면 작업이 동일한 구조를 사용하게 한다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui/src/app, components, styles; UI 패키지 설정; UI 기초 시험  
**검증 기록:** `docs/progress/tasks/1.1.md`

**완료 조건**

- [ ] UI 개발 서버와 production build가 실행되고 초기 화면에 런타임 오류가 없다.
- [ ] 기본 레이아웃·공용 컴포넌트가 분리되고 키보드 이동과 두 화면 폭을 확인했다.
- [ ] 실제 키/경로가 UI 번들에 포함되지 않으며 상태/네트워크를 공용 UI에 섞지 않았다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.1 UI 실행 기반과 공용 컴포넌트 만들기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김찬우 2.1번 + 박준형 3.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.1절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui/src/app, components, styles; UI 패키지 설정; UI 기초 시험
수행할 일:
1. docs/ui/SCREEN_SPEC.md와 docs/conventions/TYPESCRIPT_REACT.md, 루트 workspace 설정을 읽고 React/TypeScript/Vite 앱을 기존 workspace 안에 구성하라. 의존성을 추가해야 하면 지정된 lockfile 소유 규칙을 지켜 변경 내역을 인계하라.
2. 프로젝트 선택, 대화, 컨텍스트, 포인터, 설정 영역으로 분리된 기본 레이아웃을 만들고 버튼·입력·상태 배지·알림·모달을 공용 components로 분리하라. 이 작업에서는 레이아웃과 공용 표현 요소에 집중하고 화면 상태/사용자 동작은 1.3, 실제 SDK API 연결은 1.4에서 구현하라.
3. 키보드 focus, label, 오류 메시지 연결, 색상 대비, 1280px/768px 폭을 지원하라. 색상·간격·글꼴 토큰은 styles에 모으고 각 화면에 하드코딩을 복제하지 마라.
4. 초기 실행/빌드와 최소 컴포넌트 렌더 시험을 실행하고 다음 화면 담당 코드가 import할 공용 export를 정리하라.

반드시 검증할 완료 조건:
- UI 개발 서버와 production build가 실행되고 초기 화면에 런타임 오류가 없다.
- 기본 레이아웃·공용 컴포넌트가 분리되고 키보드 이동과 두 화면 폭을 확인했다.
- 실제 키/경로가 UI 번들에 포함되지 않으며 상태/네트워크를 공용 UI에 섞지 않았다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.1.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.1절의 조건 및 '1.1 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 1.2 계약 fixture로 전체 업무 화면 구현하기

**선행 조건: 김민지 1.1번 + 김찬우 2.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [ ] **1.2 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 백엔드가 완성될 때까지 UI를 기다리게 하지 않으려면 실제 API와 같은 형태의 fixture로 화면을 구현해야 한다. 정상 화면뿐 아니라 빈 결과·실패·포인터 만료도 이 단계에서 확인한다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui/src/features; tests/fixtures/ui; 화면별 렌더 시험  
**검증 기록:** `docs/progress/tasks/1.2.md`

**완료 조건**

- [ ] 필수 화면과 정상/빈값/오류/만료/변경 상태가 계약 fixture로 표시된다.
- [ ] 승인·취소·삭제 의도가 구분되며 원본 전체를 DOM/브라우저 저장소에 숨겨 두지 않는다.
- [ ] 새 DTO를 임의로 만들지 않았고 화면 기능별 파일 분리가 유지된다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.2 계약 fixture로 전체 업무 화면 구현하기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.1번 + 김찬우 2.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.2절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui/src/features; tests/fixtures/ui; 화면별 렌더 시험
수행할 일:
1. contracts의 API/Event/Pointer fixture와 SCREEN_SPEC, UI_BEHAVIOR를 읽고 기능별 화면을 구현하라. 실제 API를 호출하는 코드는 아직 만들지 말고 계약을 검증하는 fixture adapter를 사용하라.
2. 로컬 최초 연결 코드 입력, 프로젝트 등록·색인 진행/완료/부분실패, 질문 입력·답변 스트림, 실행 도구 이력·승인/거절·취소, 심볼 출처/선택 이유/누락 이유, Source/Runtime 목록·부분 미리보기·삭제 확인, PDF parse 진행, 모델/예산 상태를 각각 분리하라.
3. Source 등록 해제와 Runtime 삭제의 표현을 구분하고 원본 파일 삭제 기능을 만들지 마라. SDK 및 서비스의 내부 구현 용어를 사용자가 불필요하게 보지 않게 하되 출처와 제한 이유는 표시하라.
4. empty/loading/error/expired/source_changed/no_match/budget_exceeded fixture를 화면별로 렌더하라. 긴 원문은 제한된 preview만 표시하고 전체 본문을 hidden DOM에 넣지 마라.
5. 주요 조작 요소에 안정적인 테스트 식별자를 주고 렌더·입력·접근성 검증을 실행하라.

반드시 검증할 완료 조건:
- 필수 화면과 정상/빈값/오류/만료/변경 상태가 계약 fixture로 표시된다.
- 승인·취소·삭제 의도가 구분되며 원본 전체를 DOM/브라우저 저장소에 숨겨 두지 않는다.
- 새 DTO를 임의로 만들지 않았고 화면 기능별 파일 분리가 유지된다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.2.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.2절의 조건 및 '1.2 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 1.3 화면 상태 관리와 사용자 동작 구현하기

**선행 조건: 김민지 1.2번 작업이 완료된 이후에 진행.**

- [ ] **1.3 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 화면을 그리는 것만으로는 중복 제출, 승인 대기, 취소, 재연결을 올바르게 처리할 수 없다. 김민지가 UI 구현의 일부로 화면 상태와 사용자 동작을 직접 구현해 표시와 실제 동작을 일치시킨다. 별도 STM 산출물이나 김찬우의 상태 관리 코드를 기다리지 않는다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui/src/features/<기능>/model 및 hooks; apps/ui/src/hooks; 사용자 동작 통합 시험  
**검증 기록:** `docs/progress/tasks/1.3.md`

**완료 조건**

- [ ] 정상 완료·실패·거절·취소·재연결의 화면 표시와 사용자 동작이 2.2 설계 명세와 일치한다.
- [ ] 중복 클릭·같은 sequence·늦은 run 이벤트가 실행/승인을 중복시키거나 완료 상태를 되돌리지 않는다.
- [ ] 화면 상태·렌더링·요청 처리가 기능별로 분리돼 있으며 1.4에서 실제 API로 교체할 연결 지점이 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.3 화면 상태 관리와 사용자 동작 구현하기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.2번 작업이 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.3절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui/src/features/<기능>/model 및 hooks; apps/ui/src/hooks; 사용자 동작 통합 시험
수행할 일:
1. 2.2의 docs/ui/UI_BEHAVIOR.md와 3.2의 API/Event 계약을 읽고, 1.2 화면에서 사용할 상태 처리 코드를 직접 구현하라. 김찬우에게 상태 전이 모델·상태 머신 코드·런타임 타입 구현을 요구하지 마라.
2. 프로젝트 선택/색인 진행, 실행/승인 대기/취소, 연결 상태, 포인터 조회/PDF 진행을 필요한 범위로 나눠 관리하라. 기능별 model/hook과 공통 hooks를 사용하고 파생 가능한 표시 값을 여러 boolean으로 중복 저장하지 마라. React의 기본 상태 관리나 이미 선택된 수단을 사용하며 별도 상태 머신 프레임워크·범용 전이 엔진은 필수 산출물로 만들지 마라.
3. 서버의 session_id/run_id/sequence/approval_id와 상태 snapshot 계약을 기준으로 중복·오래된 응답을 무시하라. 승인 대기 중 버튼 정책, cancelling 표시, 새 세션 초기화, terminal 상태 보존, 재연결 후 snapshot 복구를 구현하라. 실제 SDK의 수명주기는 호스트를 기준으로 하고 UI에서 별도 실행 상태를 추측하지 마라.
4. 사용자 입력 handler와 요청·SSE 구독 등 부수효과를 렌더 컴포넌트에서 분리하고 이 단계에서는 fixture adapter에 연결하라. 구독 해제·타이머 정리·화면 종료 후 응답 무시를 처리해 1.4에서 같은 인터페이스로 실제 API를 연결할 수 있게 하라.
5. 중복 제출, 승인 거절·timeout, 취소, 연결 단절/복구, 역순 이벤트, 이전 run의 늦은 응답을 UI 동작 시험으로 검증하라. 코드 결함은 본인이 수정하고 화면 표시 명세의 모호함만 김찬우에게 문서 변경 요청으로 인계하라. 공개 hook/handler 사용법과 검증 증거를 1.4·2.3에 넘겨라.

반드시 검증할 완료 조건:
- 정상 완료·실패·거절·취소·재연결의 화면 표시와 사용자 동작이 2.2 설계 명세와 일치한다.
- 중복 클릭·같은 sequence·늦은 run 이벤트가 실행/승인을 중복시키거나 완료 상태를 되돌리지 않는다.
- 화면 상태·렌더링·요청 처리가 기능별로 분리돼 있으며 1.4에서 실제 API로 교체할 연결 지점이 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.3.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.3절의 조건 및 '1.3 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 1.4 실제 프로젝트·Cline 실행 API와 SSE 연결하기

**선행 조건: 김민지 1.3번 + 박준형 3.5번 작업이 모두 완료된 이후에 진행.**

- [ ] **1.4 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 화면이 mock에서만 동작해서는 프로젝트가 완성되지 않는다. 준비된 호스트의 세션·실행·승인 API와 스트림을 연결하고 통신 결과·오류를 1.3의 화면 상태 처리에 반영한다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui/src/api; run/project/approval effect handlers; 실제 호스트 UI 통합 시험  
**검증 기록:** `docs/progress/tasks/1.4.md`

**완료 조건**

- [ ] UI→실제 호스트→실제 Cline SDK lifecycle의 실행·스트림·승인·취소가 통과한다.
- [ ] 재접속/중복 요청이 새 run이나 중복 도구 실행을 만들지 않는다.
- [ ] 잘못된 API 응답을 검출하고 비밀값이 브라우저/로그에 유출되지 않는다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.4 실제 프로젝트·Cline 실행 API와 SSE 연결하기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.3번 + 박준형 3.5번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.4절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui/src/api; run/project/approval effect handlers; 실제 호스트 UI 통합 시험
수행할 일:
1. docs/contracts/API.md, EVENTS.md 및 3.5에서 실행 가능한 호스트를 읽고 typed HTTP client와 SSE client를 각각 작성하라. JSON 스키마 검증·snake_case 변환은 경계 mapper에 모아라.
2. 프로젝트 등록, 세션 생성, run 생성, 답변/tool 이벤트, 승인 응답, 취소, run snapshot 조회를 실제 API에 연결하라. 아직 연결되지 않은 index/pointer 기능을 성공으로 가장하지 말고 준비 상태를 표시하라.
3. 요청 중복에는 idempotency_key를 사용하고 이벤트 sequence를 기준으로 중복을 제거하라. Last-Event-ID 재연결과 replay 만료 시 snapshot 복구를 구현하라. SSE disconnect만으로 cancel API를 호출하지 마라.
4. 최초 일회용 연결 코드를 bootstrap API로 교환하고 same-origin HttpOnly cookie를 HTTP/SSE에 사용하라. 코드를 URL에 넣지 말고 사용 후 입력값을 지워라. provider API 키/내부 서비스 토큰을 브라우저에 요구하거나 저장하지 마라. 네트워크 종료·401/403·5xx·timeout을 구분해 1.3의 화면 상태 처리와 오류 표시에 반영하라.
5. 실제 SDK 호스트의 scripted provider fixture로 완료·승인 거절·취소·연결 복구를 검증하라. fixture provider와 실제 provider 실행 결과를 명확히 구분하라.

반드시 검증할 완료 조건:
- UI→실제 호스트→실제 Cline SDK lifecycle의 실행·스트림·승인·취소가 통과한다.
- 재접속/중복 요청이 새 run이나 중복 도구 실행을 만들지 않는다.
- 잘못된 API 응답을 검출하고 비밀값이 브라우저/로그에 유출되지 않는다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.4.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.4절의 조건 및 '1.4 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 1.5 R0·포인터·PDF·컨텍스트 예산 화면을 실서비스에 연결하기

**선행 조건: 김민지 1.4번 + 박준형 3.6번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.**

- [ ] **1.5 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 코드 근거와 문서, 실행 결과가 실제로 어디에서 왔는지 보여야 사용자가 제한된 컨텍스트를 이해할 수 있다. 모든 부가 기능을 실서비스와 연결해 UI의 마지막 mock 경로를 제거한다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui/src/features/{project,context,pointers}; API mappers; pointer/PDF UI 시험  
**검증 기록:** `docs/progress/tasks/1.5.md`

**완료 조건**

- [ ] R0·Source·Runtime·PDF·예산 화면이 모두 실서비스로 동작한다.
- [ ] 페이지/줄/실행 출처와 제한·누락·만료·변경 이유가 정확히 표시된다.
- [ ] Source 등록 해제로 원본이 지워지지 않고 대형 본문 전체를 자동 다운로드하지 않는다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.5 R0·포인터·PDF·컨텍스트 예산 화면을 실서비스에 연결하기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.4번 + 박준형 3.6번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.5절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui/src/features/{project,context,pointers}; API mappers; pointer/PDF UI 시험
수행할 일:
1. 3.6 통합 호스트를 실행하고 색인 생성/상태, R0 원문 출처, context preview, 포인터 목록/읽기/검색/삭제, PDF parse job을 실제 API에 연결하라.
2. symbol은 파일·줄·revision, PDF는 원본 문서·페이지, Runtime은 실행/도구/시간·만료를 표시하라. 선택/누락 이유와 실제 계수/추정 여부를 구분하고 절감률은 비교 가능한 실측값이 있을 때만 보여라.
3. Source 등록 시 사용자가 지정한 외부 파일만 보내고 브라우저가 임의 디스크 파일을 읽는다고 가정하지 마라. 대형 응답은 cursor로 조회하고 source_changed 시 재등록/갱신을 안내하라.
4. PDF parsing/ready/unsupported/failed, Runtime expired/deleted, stale index, NO_MATCH, 한국어 검색어 부족, BUDGET_EXCEEDED를 표시하라. 새 요약기/LLM selector를 UI에 추가하지 마라.
5. 사용자 원본 파일이 Source 등록 해제 후 존재하는지, 삭제 후 오래된 preview가 남지 않는지, 다른 run 이벤트가 현 화면에 섞이지 않는지 실제 서비스로 검증하라.

반드시 검증할 완료 조건:
- R0·Source·Runtime·PDF·예산 화면이 모두 실서비스로 동작한다.
- 페이지/줄/실행 출처와 제한·누락·만료·변경 이유가 정확히 표시된다.
- Source 등록 해제로 원본이 지워지지 않고 대형 본문 전체를 자동 다운로드하지 않는다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.5.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.5절의 조건 및 '1.5 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 1.6 UI 오류 수정과 전체 사용자 흐름 인수 시험 완료하기

**선행 조건: 김민지 1.5번 + 김찬우 2.3번 + 박준형 3.7번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.**

- [ ] **1.6 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 개별 화면 성공과 사용자가 처음부터 끝까지 작업하는 성공은 다르다. 설계 인수표와 준비된 통합 환경을 사용해 실제 사용 흐름의 UI 결함을 마무리하고 최종 출시 검증에 넘긴다.

**담당:** 김민지  
**주요 산출물·수정 범위:** apps/ui; tests/e2e; docs/ui의 구현 대응표; 1.6 검증 증거  
**검증 기록:** `docs/progress/tasks/1.6.md`

**완료 조건**

- [ ] 2.3의 필수 UI 인수 항목과 전체 E2E가 통과하고 UI 차단 결함이 없다.
- [ ] 실제 provider smoke와 자동 fixture 시험을 구분한 증거가 있다.
- [ ] 빌드·접근성/반응형·오류 표시를 확인했고 최종 3.8이 바로 재현할 수 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 1.6 UI 오류 수정과 전체 사용자 흐름 인수 시험 완료하기
담당 역할: 김민지
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.5번 + 김찬우 2.3번 + 박준형 3.7번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 1.6절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/ui; tests/e2e; docs/ui의 구현 대응표; 1.6 검증 증거
수행할 일:
1. 2.3 UI ACCEPTANCE 표와 3.7 실행 절차, 4.10 검증 fixture로 전체 앱을 실행하라. UI 소유 코드의 결함을 수정하고 소유권이 다른 결함은 재현 자료를 인계하되 미해결 상태를 성공으로 처리하지 마라.
2. 신규 프로젝트→색인 READY→질문→R0 근거 확인→승인된 명령 실행→큰 로그 Runtime Pointer→부분 읽기→PDF Source Pointer→답변 출처 확인을 E2E로 검증하라.
3. 실패/거절/취소, 실행 중 SSE 단절·재연결, 원본 수정 후 stale, PDF 미지원, 예산 초과, 키보드 조작과 768px/1280px 레이아웃을 검증하라.
4. fixture provider 기반 자동 시험과 실제 설정 provider 기반 smoke를 구분해 기록하라. 실 provider 인증이 없으면 해당 필수 live 항목과 본 작업 완료 체크를 남겨 두고 .env.example의 설정 방법을 안내하라.
5. 변경한 UI에 한해 회귀 시험·typecheck/lint/build를 통과시키고 화면별 인수 증거·남은 제한을 3.8 담당자에게 인계하라. 원격 배포는 하지 마라.

반드시 검증할 완료 조건:
- 2.3의 필수 UI 인수 항목과 전체 E2E가 통과하고 UI 차단 결함이 없다.
- 실제 provider smoke와 자동 fixture 시험을 구분한 증거가 있다.
- 빌드·접근성/반응형·오류 표시를 확인했고 최종 3.8이 바로 재현할 수 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/1.6.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 1.6절의 조건 및 '1.6 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

<a id="owner-2"></a>

## 2. 김찬우의 역할 — UI 설계·설계 문서·구현 화면 검토

화면 구조·사용 흐름·상황별 표시 명세와 설계 검토를 담당한다. 산출물은 UI 설계 문서·사용 사례·인수표이며 UI 런타임 코드 작성은 포함하지 않는다. 화면 상태·사용자 동작 구현과 시험은 김민지 1.3, 실제 API 연결은 1.4, 최종 UI 수정은 1.6에서 수행한다.

### 2.1 제품 화면·사용 흐름·인수 범위 설계하기

**선행 조건: 없음. 지금 시작 가능.**

- [x] **2.1 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 네 사람이 같은 제품을 만들려면 화면이 무엇을 제공하고 어떤 성공을 의미하는지 먼저 정의해야 한다. 백엔드 기술 계약을 기다리지 않아도 사용자 흐름과 화면별 책임을 독립적으로 설계할 수 있다.

**담당:** 김찬우  
**주요 산출물·수정 범위:** docs/ui/SCREEN_SPEC.md; 화면 와이어프레임과 사용자 시나리오  
**검증 기록:** `docs/progress/tasks/2.1.md`

**완료 조건**

- [x] 모든 포함 기능에 화면·사용자 행동·성공/실패 상태가 대응한다.
- [x] 화면별 인수 시나리오 ID와 API/이벤트 요구가 있어 1.1/3.2가 바로 시작 가능하다.
- [x] 추가 기법·클라우드·다중 사용자 같은 범위 밖 기능이 섞이지 않았다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 2.1 제품 화면·사용 흐름·인수 범위 설계하기
담당 역할: 김찬우
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 없음. 지금 시작 가능.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 2.1절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/ui/SCREEN_SPEC.md; 화면 와이어프레임과 사용자 시나리오
수행할 일:
1. 이 로드맵 0절과 기존 CODING_CONVENTIONS.md를 읽고 UI 목적·사용자 흐름·화면 구조를 docs/ui/SCREEN_SPEC.md에 작성하라. 이 작업은 설계이며 앱 코드나 Figma 파일을 새로 만들 필요는 없다.
2. 프로젝트 등록/색인, 대화·코드 작업, 승인·취소, 관련 심볼·출처, Source/Runtime 목록·읽기·삭제, PDF 등록/파싱, 컨텍스트 예산·provider 설정 상태를 화면별 와이어프레임과 입력/출력 표로 정의하라.
3. 정상, 빈 결과, 로딩, 부분 성공, 오류, 만료, 원본 변경, 연결 끊김, 예산 초과를 각 화면에 배정하라. Source 등록 해제의 의미, 다섯 언어의 심볼 지원 범위, TypeScript 자료 등록 안내를 UI 문구에 반영하라.
4. 승인 없는 명령 실행을 허용하지 않고 사용자 원본 삭제/전체 파일 자동 전송 버튼을 만들지 마라. SDK 용어를 숨기되 상태·출처·제한은 이해할 수 있게 표현하라.
5. 화면별 수용 시나리오 ID와 김민지 구현 대상, 3.2에 요청할 API/이벤트 요구를 작성하라. 요구사항 누락을 표로 점검하고 모순을 해결하라.

반드시 검증할 완료 조건:
- 모든 포함 기능에 화면·사용자 행동·성공/실패 상태가 대응한다.
- 화면별 인수 시나리오 ID와 API/이벤트 요구가 있어 1.1/3.2가 바로 시작 가능하다.
- 추가 기법·클라우드·다중 사용자 같은 범위 밖 기능이 섞이지 않았다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/2.1.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 2.1절의 조건 및 '2.1 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 2.2 화면별 표시·사용자 동작 상세 명세 작성하기

**선행 조건: 김찬우 2.1번 + 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [x] **2.2 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 화면마다 어떤 내용을 보여 주고 어떤 조작을 허용할지 명확해야 김민지가 별도 해석 없이 구현할 수 있다. 확정된 API와 오류 정보를 사용자의 관점에서 정리한 상세 설계 문서를 만든다. 내부 상태 구조와 실행 코드는 김민지가 결정한다.

**담당:** 김찬우  
**주요 산출물·수정 범위:** docs/ui/UI_BEHAVIOR.md; docs/ui/SCREEN_SPEC.md 보완; 화면별 사례와 요구 대응표  
**검증 기록:** `docs/progress/tasks/2.2.md`

**2026-11-05 완료 · 3/3.** 9개 화면과 34개 사례에서 표시 필드·입력·버튼·오류·복구 행동을 대조했다. 한글 원문의 선택 범위가 미리보기와 실행 요청까지 일치하며, PDF 7개 상태와 재연결 후 출처·승인 이력도 공개 계약 예시로 확인했다. 1.2의 화면 구현과 1.3의 행동 시험에 사용할 수 있다. [항목별 검증 기록](docs/progress/tasks/2.2.md#4-acceptance_evidence) · [화면별 사례표](docs/ui/UI_BEHAVIOR_CASES.md) · [계약 보완 인계](docs/handoffs/2.2-ui-behavior-contract-gaps.md)

**완료 조건**

- [x] 모든 화면에 표시 항목·입력 규칙·버튼 활성 조건·오류 문구·복구 행동이 정의돼 있다.
- [x] 3.2/4.2 API·이벤트·오류 필드와 화면 표시의 대응이 맞고 빠진 상황이 없다.
- [x] 1.2/1.3이 바로 사용할 문서·사례가 있으며 별도 상태 전이 모델이나 상태 관리 코드를 산출물로 요구하지 않는다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 2.2 화면별 표시·사용자 동작 상세 명세 작성하기
담당 역할: 김찬우
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김찬우 2.1번 + 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 2.2절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/ui/UI_BEHAVIOR.md; docs/ui/SCREEN_SPEC.md 보완; 화면별 사례와 요구 대응표
수행할 일:
1. 2.1 화면 설계, 3.2 API/Event 계약, 4.2 포인터·오류 명세를 읽고 docs/ui/UI_BEHAVIOR.md를 작성하라. 필요한 내용은 SCREEN_SPEC.md에 연결하고 같은 설명을 중복 관리하지 마라.
2. 각 화면마다 목적, 표시 필드와 API 출처, 입력/검증 규칙, 버튼·메뉴 동작, 로딩/빈 결과/오류 문구, 접근성 안내를 표로 정의하라. 와이어프레임의 각 요소가 무엇을 표시하는지 식별 가능하게 하라.
3. 색인 진행/부분실패, 승인 대기/거절/만료, 취소 요청/완료, 연결 끊김/복구, 포인터 만료·삭제·원본 변경, PDF 미지원, 예산 초과 때 사용자가 볼 내용과 다음에 할 수 있는 행동을 설명하라. 정상 종료 뒤 늦은 응답이 와도 화면이 실행 중으로 돌아가면 안 된다는 관찰 가능한 요구를 적어라.
4. 각 사례를 사전 상황→사용자 조작 또는 서버 응답→예상 화면·버튼·메시지 형태로 작성하라. 기존 계약 fixture ID를 참조하되 새로운 API 타입/이벤트 스키마를 임의로 만들지 마라. 현재 상태+이벤트+가드+다음 상태의 전이표, machine/reducer, command 프로토콜을 별도 설계하거나 코드로 구현하지 마라.
5. 화면 설계와 API 필드/오류 코드가 일치하는지 점검하고 누락·모순을 문서에서 해결하라. 계약 자체의 결함은 소유자에게 인계하라. 실제 구현에 필요한 설계가 확정되면 김민지 1.2/1.3에 전달하고, 자동 행동 시험과 상태 처리 코드는 김민지가 담당함을 명시하라.

반드시 검증할 완료 조건:
- 모든 화면에 표시 항목·입력 규칙·버튼 활성 조건·오류 문구·복구 행동이 정의돼 있다.
- 3.2/4.2 API·이벤트·오류 필드와 화면 표시의 대응이 맞고 빠진 상황이 없다.
- 1.2/1.3이 바로 사용할 문서·사례가 있으며 별도 상태 전이 모델이나 상태 관리 코드를 산출물로 요구하지 않는다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/2.2.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 2.2절의 조건 및 '2.2 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 2.3 구현 화면의 설계 검토와 최종 인수표 작성하기

**선행 조건: 김민지 1.3번 + 김찬우 2.2번 작업이 모두 완료된 이후에 진행.**

- [ ] **2.3 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 상세 설계와 실제 화면의 차이를 API 통합 전에 발견해야 뒤늦은 수정이 줄어든다. 김찬우는 화면·사용 흐름을 설계 기준으로 검토하고, 김민지가 최종 검증에 사용할 인수표와 수정 요청을 문서화한다.

**담당:** 김찬우  
**주요 산출물·수정 범위:** docs/ui/ACCEPTANCE.md; SCREEN_SPEC/UI_BEHAVIOR 보완; docs/handoffs의 UI 수정 요청  
**검증 기록:** `docs/progress/tasks/2.3.md`

**완료 조건**

- [ ] 화면/동작 설계의 모순이 해소되고 fixture UI를 기준으로 필수 사용 흐름을 검토했다.
- [ ] 1.6이 바로 사용할 인수표와 UI 수정 요청이 있으며 구현 결함마다 김민지의 처리 작업이 지정돼 있다.
- [ ] 필수 UI 요구가 설계·구현 작업·최종 검증 항목에 연결되고 상태 관리 코드 수정은 김찬우의 완료 조건에 포함되지 않는다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 2.3 구현 화면의 설계 검토와 최종 인수표 작성하기
담당 역할: 김찬우
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.3번 + 김찬우 2.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 2.3절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/ui/ACCEPTANCE.md; SCREEN_SPEC/UI_BEHAVIOR 보완; docs/handoffs의 UI 수정 요청
수행할 일:
1. 1.3의 실행 가능한 fixture UI를 SCREEN_SPEC.md와 UI_BEHAVIOR.md에 대조하라. 완료·오류·거절·취소·재연결·부분 조회·만료·원본 변경 사례를 사용자 관점에서 검토하라. 실서비스로 재확인할 항목과 fixture에서 검토한 항목을 구분하라.
2. 화면 설계의 누락·모순은 본인 문서에서 수정하라. 표시/상태 처리/API 연결의 구현 결함은 재현 순서, 실제 결과, 기대 결과, 영향 화면, 심각도와 담당 작업을 docs/handoffs에 남겨 김민지에게 인계하라. apps/ui의 상태 코드·hook·컴포넌트를 이 작업에서 구현하거나 수정하지 마라.
3. docs/ui/ACCEPTANCE.md에 항목 ID, 선행 데이터, 사용자 조작, 예상 표시·버튼 동작, 검증 방법, 구현 담당 작업을 작성하라. 1.6과 3.8에서 실서비스로 확인할 조건을 명시하라.
4. 동작 검토를 진행할 수 없는 차단 결함은 김민지가 1.3을 다시 열어 해결한 뒤 확인하라. 최종 화면 표현 수정은 1.6의 입력으로 인계하며, 미해결 결함을 검증 통과로 표시하지 마라. 본 작업은 설계 검토·인계 완료를 기준으로 닫고 제품의 최종 UI 통과는 1.6에서 판정한다.
5. 설계 문서, API 대응, 인수표의 시나리오 ID를 맞추고 본인의 산출물 목록을 전달하라. 상태 관리 구현이나 상태 전이 시험 코드 작성은 수행하지 마라.

반드시 검증할 완료 조건:
- 화면/동작 설계의 모순이 해소되고 fixture UI를 기준으로 필수 사용 흐름을 검토했다.
- 1.6이 바로 사용할 인수표와 UI 수정 요청이 있으며 구현 결함마다 김민지의 처리 작업이 지정돼 있다.
- 필수 UI 요구가 설계·구현 작업·최종 검증 항목에 연결되고 상태 관리 코드 수정은 김찬우의 완료 조건에 포함되지 않는다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/2.3.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 2.3절의 조건 및 '2.3 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

<a id="owner-3"></a>

## 3. 박준형의 역할 — R0 Symbol Bundle·Cline SDK·통합 연결

R0와 LLM 연결 외에 공통 기반/API/최종 조립의 소유자다. 이 통합 책임을 작업으로 배정했으므로 별도 백엔드 담당자 없이 네 사람의 작업으로 프로젝트가 닫힌다.

### 3.1 실제 Cline SDK 버전과 필수 확장점 검증하기

**선행 조건: 없음. 지금 시작 가능.**

- [x] **3.1 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 설계가 존재하지 않는 hook이나 CLI에 기대면 다른 사람의 기능이 완성돼도 제품은 연결되지 않는다. 가장 먼저 실제 SDK 설치·타입·실행 순서를 증명하고 이후 작업에서 사용할 정확한 API를 고정한다.

**담당:** 박준형  
**주요 산출물·수정 범위:** docs/architecture/SDK_COMPATIBILITY.md; tools/sdk-probe의 분리된 작은 검증 파일/고정 lockfile  
**검증 기록:** `docs/progress/tasks/3.1.md`

**완료 조건**

- [x] 설치 가능한 SDK 버전·Node 조건·정확한 호출 타입을 고정하고 실제 import/실행에 성공했다.
- [x] 실제 SDK의 2회 provider 요청과 canonical history에서 큰 원문 제거/포인터 전달을 확인했다.
- [x] 승인·취소·실패 차단·예산 게이트·도구 제한·checkpoint 비활성화의 실행 증거가 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.1 실제 Cline SDK 버전과 필수 확장점 검증하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 없음. 지금 시작 가능.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.1절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/architecture/SDK_COMPATIBILITY.md; tools/sdk-probe의 분리된 작은 검증 파일/고정 lockfile
수행할 일:
1. 공식 Cline 문서와 설치 가능한 @cline/sdk 버전, Node 요구 조건을 확인하고 정확한 버전/다운로드 근거/타입 선언/확인 날짜를 기록하라. 이 작업에서는 tools/sdk-probe에만 최소 패키지와 fixture를 두고 최종 workspace 조립은 3.2로 넘겨라.
2. ClineCore를 실제 import하고 local backend에서 create/start/send/subscribe/abort/stop/dispose 흐름을 검증하라. 실제 타입을 읽어 scripted provider fixture를 연결하고 lifecycle만 흉내 낸 자체 SDK를 만들지 마라. 이 작업은 실제 SDK+fixture provider로 완료할 수 있으며 live API 키는 필요 없다. 아직 TS 규약 파일이 없으므로 0.5를 적용하라.
3. 프로젝트 소유 local tool을 등록하고 2회 모델 요청을 캡처하라. 첫 요청의 도구 호출→큰 sentinel 결과→afterTool의 result 교체→두 번째 요청에 pointer만 있고 sentinel 원문은 없는지 입증하라. 이 작업의 메모리 pointer fixture는 정식 Runtime Store가 아님을 표시하라.
4. beforeModel 또는 동등한 공개 확장점에서 provider messages/tools/options를 관측·차단할 수 있는지, tool-call/result 순서를 보존할 수 있는지 검증하라. 마지막 provider 변환 후 outbound payload/framing 계수·차단 위치와 지원 모델의 tokenizer를 확정하라. beforeModel만 확인하고 최종 요청 cap을 입증했다고 쓰지 마라.
5. 승인 요청/거절, 중단, hook 저장 실패/timeout에서 원문 전송 차단, provider tool 비활성화, 기본 read/search/command 도구의 교체·허용 목록 설정을 확인하라. checkpoint를 끄고 Git 상태가 바뀌지 않게 하라.
6. 실제 provider 접속에 필요한 서버 환경변수·model/context limit을 .env.example에 값 없이 정리할 사양을 만들고, 공개 문서와 설치 API 차이를 호환성 표에 기록하라. SDK 필수 기능이 검증되지 않으면 대체 API를 같은 SDK에서 조사하고 완료 체크를 남겨라.

반드시 검증할 완료 조건:
- 설치 가능한 SDK 버전·Node 조건·정확한 호출 타입을 고정하고 실제 import/실행에 성공했다.
- 실제 SDK의 2회 provider 요청과 canonical history에서 큰 원문 제거/포인터 전달을 확인했다.
- 승인·취소·실패 차단·예산 게이트·도구 제한·checkpoint 비활성화의 실행 증거가 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.1.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.1절의 조건 및 '3.1 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.2 모듈 기반 프로젝트 골격·공통 계약·개발 명령 확정하기

**선행 조건: 박준형 3.1번 + 김찬우 2.1번 + 임우형 4.1번 작업이 모두 완료된 이후에 진행.**

- [x] **3.2 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 각자 파일과 API를 임의로 만들면 통합 시 타입과 폴더가 충돌한다. SDK 검증 결과, 화면 요구, 포인터 설계를 한 번 맞춰 공통 골격과 공개 계약을 만들고 병렬 작업의 출발점을 제공한다.

**담당:** 박준형  
**주요 산출물·수정 범위:** 루트 package/lock/실행 설정; apps/host; services/context-service 골격; contracts/common, api, events, symbols; 공통 문서  
**검증 기록:** `docs/progress/tasks/3.2.md`

후속 검토에서 호스트의 내부 HTTP 요청을 loopback으로 제한하고 리디렉션 시 중단하도록 했다. Python 서비스는 잘못된 입력이나 예외를 기록할 때 원문·비밀값을 노출하지 않도록 하고, 오류 응답의 요청 ID를 헤더와 일치시킨다. 빌드한 Python wheel의 모듈 45개를 현재 소스와 바이트 단위로 대조했다. [호스트 통신 시험](apps/host/tests/unit/contextClient.test.ts) · [서비스 로그 시험](services/context-service/tests/unit/test_redaction.py)

**완료 조건**

- [x] 공통 골격·의존성 lock·Python/TS 규약·health 실행과 계약 fixture 검증이 존재한다.
- [x] UI/SDK/심볼/포인터 담당 경계와 생성 타입·공통 오류·이벤트가 문서화됐다.
- [x] 필수 검사 미구현은 성공으로 위장하지 않고 후속 담당과 완료 작업이 연결돼 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.2 모듈 기반 프로젝트 골격·공통 계약·개발 명령 확정하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.1번 + 김찬우 2.1번 + 임우형 4.1번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.2절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: 루트 package/lock/실행 설정; apps/host; services/context-service 골격; contracts/common, api, events, symbols; 공통 문서
수행할 일:
1. 3.1 SDK 호환성, 2.1 UI 요구, 4.1 포인터 설계를 읽고 0.5 목표 구조에 맞게 Node workspace와 Python src layout을 구성하라. 검증한 SDK 버전과 Python/FastAPI/검사 도구 의존성을 lock하고 SDK probe의 중복 의존성은 최종 구조에 정리하라.
2. 기존 CODING_CONVENTIONS.md를 보존하고 docs/conventions/TYPESCRIPT_REACT.md를 작성하라. strict TypeScript, ESLint/Prettier, Python Ruff/mypy/pytest, 파일 길이·금지 의존성 검사의 기준을 설정하라.
3. contracts/common/api/events/symbols의 JSON Schema와 성공/오류 fixture를 만들고 생성 타입/검증 경로를 정하라. Pointer/Context 세부는 4.2가 소유하므로 경계 참조만 확정하라. 프로젝트·index·session·run·approval·pagination·idempotency·SSE replay 계약을 문서화하라.
4. 앱 이벤트와 SDK 이벤트를 분리하고 김민지의 UI가 참조할 서버 상태 snapshot을 정의하라. 공개 포트 ContextServiceClient, SymbolService, PointerService, TokenCounter, ModelRequestGate, ToolResultTransformer를 앱 내부 인터페이스로 명시하라. 3.1에서 선택한 모델의 본문 tokenizer를 common의 실행 가능한 TokenCounter와 내부 tokens.count로 제공해 Python/TS가 재사용하게 하라. exact/estimated 표기·Unicode fixture·오류 계약을 검증하되 최종 provider framing과 총 요청 gate는 4.8에 맡겨라.
5. npm run dev/check/test:contracts/test:integration/test:e2e/test:live/build 인터페이스와 서비스 기동/종료 골격을 제공하라. 아직 미구현인 필수 검사/서비스는 명시적으로 미완료를 보고하게 하고 성공하는 no-op으로 두지 마라.
6. .env.example, .gitignore, 데이터 디렉토리, loopback 인증, same-origin 정책, 로그 redaction, 라이브 smoke 설정을 정하라. 계약 fixture 검증과 최소 host/service health 실행을 확인하고 담당별 소유 파일을 ARCHITECTURE.md에 고정하라.

반드시 검증할 완료 조건:
- 공통 골격·의존성 lock·Python/TS 규약·health 실행과 계약 fixture 검증이 존재한다.
- UI/SDK/심볼/포인터 담당 경계와 생성 타입·공통 오류·이벤트가 문서화됐다.
- 필수 검사 미구현은 성공으로 위장하지 않고 후속 담당과 완료 작업이 연결돼 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.2.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.2절의 조건 및 '3.2 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.3 5개 언어의 심볼·정적 참조·원문 색인과 갱신 구현하기

**선행 조건: 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [x] **3.3 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** R0는 질문 전에 원문과 참조 관계를 준비해야 한다. 기존 실험 파서를 제품 모듈로 옮기고 변경된 코드와 오래된 줄 번호가 섞이지 않도록 revision 단위 색인을 만든다.

**담당:** 박준형  
**주요 산출물·수정 범위:** services/context-service/src/securecode_context/symbols/{parser,index,graph}; 심볼 fixture/시험  
**검증 기록:** [3.3 로컬 색인과 혼합 프로젝트 시험](docs/progress/tasks/3.3.md)

**2026-11-05 반영 범위** — 로컬 색인 생성은 `services/context-service`에서 `uv run python -m securecode_context.symbols <프로젝트_경로> --out <색인.json>`으로 실행한다. 심볼 원문과 최대 깊이 3의 정적 참조 묶음은 R0 검색 후보가 된다. `--store <데이터_경로> --workspace-id <ws_ID>`는 작업 공간별 revision을 만들고 `current.json`으로 원자적으로 전환한다. 검색 벡터 준비 전이므로 revision 상태는 `parsed`다. 서비스 검색 API·`ready` 전환은 3.4, 웹 화면과 SDK 연결은 3.5/3.6의 인수 대상이다. 기존 Python 벤치마크의 고정 입력·결과는 재현용으로 보존한다.

로컬 참조 검증에는 Python의 표준 `src/` 배치와 JavaScript의 `require("./lib.cjs").size` 직접 호출·별칭을 포함한다. 같은 저장소에서도 서로 다른 Python 프로젝트의 동명 심볼은 구분한다. 기존 Python 프로젝트 7개를 다시 색인한 결과, R0 후보 314개의 필드와 순서가 고정 결과와 일치했다.

**완료 조건**

- [x] 다섯 언어 각각에서 심볼 원문·정적 참조와 출처/hash가 정확하고 파싱 실패가 파일별로 격리된다.
- [x] 변경/삭제/이동 시 새 revision으로 원자적으로 전환하고 stale 자료를 정상 반환하지 않는다.
- [x] 실험 코드 runtime 의존·요약 생성·전체 index 전송이 없고 3.4 입력 계약이 준비됐다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.3 5개 언어의 심볼·정적 참조·원문 색인과 갱신 구현하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.3절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: services/context-service/src/securecode_context/symbols/{parser,index,graph}; 심볼 fixture/시험
수행할 일:
1. 기존 experiment.py의 source_nodes/closure/fragment와 experiment_r0.py의 R0 전용 prepare를 읽고 순수 파싱·참조 분석만 새 모듈로 이식하라. 실험 실행기·Client·build_assets·정답 데이터를 import하지 마라.
2. 0.1의 다섯 언어를 파일별로 판별해 심볼과 참조를 추출하고 파일/줄/qualname/hash를 보존하라. Python은 decorator 시작 줄과 로컬 from import·상대 import·alias를 유지하라. 각 언어의 스코프와 로컬 모듈 규칙으로 대상이 확정될 때만 연결하고 동적·모호한 참조는 unresolved로 남겨라.
3. .git/.securecode/node_modules/venv/build/generated 제외와 symlink/root 허용 정책을 적용하라. 한 파일 SyntaxError·인코딩 오류가 전체 색인을 중단하지 않게 diagnostics를 남겨라. 미지원 언어는 명시하라.
4. 파일 manifest/hash와 index_revision을 저장하라. MVP 갱신은 새 revision 전체를 준비한 뒤 원자적으로 교체해도 된다. 파일 수정/삭제/이동과 의존 bundle·IDF 재계산 필요성을 표시하고 이전 revision과 새 자료를 섞지 마라.
5. 검색기가 아직 준비되지 않았으면 ready 대신 parsed/pending 상태로 두고 3.4에 넘겨라. Source registry는 계약 포트로 주입해 4.5/4.6 미완료 때문에 순환 의존성이 생기지 않게 하되 fixture임을 명시하라.
6. 언어별 단독 프로젝트와 혼합 프로젝트를 검증하라. 다섯 언어의 원문·위치, Python 함수→다른 파일 helper→상수 및 decorator, 다른 언어의 로컬 참조, 순환과 언어 간 동명 심볼, 깨진 파일, TypeScript 제외, 변경/삭제/경로 이탈을 확인하라.

반드시 검증할 완료 조건:
- 다섯 언어 각각에서 심볼 원문·정적 참조와 출처/hash가 정확하고 파싱 실패가 파일별로 격리된다.
- 변경/삭제/이동 시 새 revision으로 원자적으로 전환하고 stale 자료를 정상 반환하지 않는다.
- 실험 코드 runtime 의존·요약 생성·전체 index 전송이 없고 3.4 입력 계약이 준비됐다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.3.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.3절의 조건 및 '3.3 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.4 R0 TF-IDF 검색과 제한된 Symbol Bundle 구현하기

**선행 조건: 박준형 3.3번 작업이 모두 완료된 이후에 진행.**

- [x] **3.4 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 전체 주소록을 LLM에게 주지 않으려면 서버가 질문과 관련된 원문을 먼저 선택해야 한다. R0의 원문·참조 묶음 검색을 그대로 살리되 무결과와 중복·크기 제한을 제품 계약으로 드러낸다.

**담당:** 박준형  
**주요 산출물·수정 범위:** symbols/{retrieval,bundle}; SymbolService 구현; R0 회귀 fixture/시험  
**검증 기록:** [3.4 TF-IDF 검색과 Symbol Bundle 시험](docs/progress/tasks/3.4.md)

**2026-11-05 반영 범위** — Python `R0SymbolService`가 `search`와 `read_bundle`을 제공한다. 기존 실험 Retriever와 상위 10개 순위·점수가 질문 104개에서 일치했다. 색인 빌드가 TF-IDF 벡터까지 준비한 revision만 `ready`로 게시한다. 0점 후보는 반환하지 않고 HTTP 200 NO_MATCH 본문으로 안내한다(실험의 0점 채움과 다름). 내부 HTTP route와 host 연결은 3.6, 작업 공간 루트 등록부는 3.5에서 연결한다. [선행 시험](docs/progress/tasks/3.3.md)

**완료 조건**

- [x] 다섯 언어에서 원문 atomic/깊이 3 bundle의 TF-IDF 검색과 안정적 순위가 기존 R0 논리를 재현한다.
- [x] 관련 원문·출처만 제한된 크기로 반환하고 무결과/큰 후보/중복/stale을 처리한다.
- [x] READY는 벡터 준비까지 포함하며 요약·LLM selector·전체 index 전송이 없다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.4 R0 TF-IDF 검색과 제한된 Symbol Bundle 구현하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.3번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.4절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: symbols/{retrieval,bundle}; SymbolService 구현; R0 회귀 fixture/시험
수행할 일:
1. experiment.py의 raw_items/words/Retriever/pack를 근거로 atomic 원문과 최대 참조 edge 깊이 3 bundle 후보를 생성하라. 메타데이터와 TF-IDF 벡터는 서버 안에만 보관하라.
2. IDF=ln((N+1)/(df+1))+1, TF=1+ln(count), L2 정규화와 cosine 순위를 구현하라. camelCase/underscore 분리를 보존하고 동점은 stable candidate_id 순으로 정렬하라. 별도 LLM selector·번역·요약/임베딩을 추가하지 마라.
3. SymbolService search/read_bundle에 index_revision, source provenance, score, token_count/count_mode, omissions를 반환하라. 전체 symbol index/candidate text 배열을 모델에 보내지 마라. 토큰 계산은 주입된 TokenCounter를 사용하라.
4. 유효한 검색어에서 추출할 토큰이 없거나 모든 점수가 0이면 HTTP 200, 빈 candidates와 no_match.reason_code=NO_MATCH를 반환하고 영어 식별자·파일명·사용자 선택 범위 안내를 제공하라. 기존 0점 임의 채움과의 차이를 문서화하라.
5. source hash+range 단위 중복 제거, bundle가 너무 클 때 atomic 후보나 명시적 누락, 재조회 직전 stale 감지를 구현하라. 검색 후보 상한·응답 bytes/token cap을 적용하고 최종 전체 요청 예산은 4.8에 맡겨라.
6. 원문/vector 준비가 모두 완료된 revision만 READY로 전환하라. 다섯 언어 각각의 식별자 검색과 원문 묶음, Python 함수→helper→상수 fixture, TF-IDF 순위, 순환 참조, 큰 후보, 부분 중복, 한국어만 있는 질문을 검증하고 사전 요약/선택 LLM 호출이 0회임을 검사하라.

반드시 검증할 완료 조건:
- 다섯 언어에서 원문 atomic/깊이 3 bundle의 TF-IDF 검색과 안정적 순위가 기존 R0 논리를 재현한다.
- 관련 원문·출처만 제한된 크기로 반환하고 무결과/큰 후보/중복/stale을 처리한다.
- READY는 벡터 준비까지 포함하며 요약·LLM selector·전체 index 전송이 없다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.4.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.4절의 조건 및 '3.4 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.5 Cline SDK 호스트와 UI용 실행·승인·이벤트 API 구현하기

**선행 조건: 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [x] **3.5 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 박준형의 LLM 연결 역할에는 SDK를 감싸는 것뿐 아니라 UI가 사용할 실행 수명주기를 제공하는 일도 포함된다. 심볼·포인터 완성을 기다리지 않고 계약 포트를 통해 먼저 실행 가능한 호스트를 만든다.

**담당:** 박준형  
**주요 산출물·수정 범위:** apps/host/src/{app,routes,cline,context-client,config}; host 계약/통합 시험  
**검증 기록:** [3.5 SDK host·실행 API 시험](docs/progress/tasks/3.5.md) · [인계](docs/handoffs/3.5-host-api-and-fixtures.md)

**2026-11-05 반영 범위** — host가 설치 `@cline/sdk` ClineCore로 세션·run·승인·취소·SSE를 제공한다. 실제 SDK + scripted provider 시험이 통과했다. 운영 host는 4.4/4.8 hook이 등록될 때까지 세션을 `PROTECTION_UNAVAILABLE`로 거절한다. 시험은 fixture hook만 주입한다. index·pointer·context·PDF route와 live provider smoke는 3.6이 연결한다.

**완료 조건**

- [x] 실제 SDK host의 실행/스트림/승인/취소와 UI API 계약이 통과한다.
- [x] 세션·이벤트·중복 요청·재시작 처리가 정의되고 앱에서 SDK로 직접 결합되지 않는다.
- [x] 포인터 hook/예산 포트와 로컬 도구 제한이 작동하며 자동 commit/push/checkpoint가 없다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.5 Cline SDK 호스트와 UI용 실행·승인·이벤트 API 구현하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.2번 + 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.5절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/host/src/{app,routes,cline,context-client,config}; host 계약/통합 시험
수행할 일:
1. 3.1에서 검증한 ClineCore API로 세션 생성·run·subscribe·approval·abort·dispose를 구현하라. 실제 SDK import를 사용하고 CLI subprocess나 mock agent loop로 대체하지 마라.
2. 0.6 API의 bootstrap/health/settings/workspace/session/run/approval/cancel/snapshot/SSE를 구현하라. launcher 일회용 코드→HttpOnly SameSite cookie 교환과 Vite same-origin proxy/SSE 인증을 구현하라. 미연결 index/pointer는 명시적 준비 안 됨 오류를 반환하고 추후 3.6에 조립하도록 route/service를 분리하라.
3. 세션별 단일 run, idempotency, event_id/sequence, 보존 기간이 있는 replay, snapshot 복구, terminal 전이·재시작 후 중단 상태를 구현하라. 설치 버전의 CoreSessionEvent와 agent_event 내부 payload를 구분해 AppEvent로 변환하라. 대형 원문은 SDK 이벤트에서 제거한 뒤 SSE로 내보내라.
4. 로컬 도구 registry와 명시적 toolPolicies, 코드 수정/명령 실행 승인, 허용 workspace, provider tool 비활성화, checkpoint 비활성화를 구현하라. capabilities.requestToolApproval을 앱 approval_id/digest/만료시간과 연결하고 취소/종료/timeout에 대기 Promise를 해소해 늦은 승인을 거절하라. Git commit/push 도구 실행은 거부하라.
5. 임우형이 연결할 ToolResultTransformer와 ModelRequestGate 포트, context-service HTTP client를 구현하라. 테스트에서만 fixture transformer/gate를 주입해 4.4/4.8을 기다리지 않고 완료하라. production은 실제 필수 hook 미등록 시 차단한다. hook 순서/timeout/error mode와 body size cap·인증을 검증하고 사용자 MCP/plugin/추가 에이전트 자동 유입을 끄라. Pointer/Selector 정책 자체는 중복 구현하지 마라.
6. 실제 SDK+scripted provider로 run 완료·승인 거절·취소·hook 실패·SSE 중복/단절·세션 격리를 검증하고 1.4/4.4에 사용 가능한 host 실행 명령과 fixture를 인계하라.

반드시 검증할 완료 조건:
- 실제 SDK host의 실행/스트림/승인/취소와 UI API 계약이 통과한다.
- 세션·이벤트·중복 요청·재시작 처리가 정의되고 앱에서 SDK로 직접 결합되지 않는다.
- 포인터 hook/예산 포트와 로컬 도구 제한이 작동하며 자동 commit/push/checkpoint가 없다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.5.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.5절의 조건 및 '3.5 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.6 R0·포인터·Context Selector·PDF를 SDK 경로에 통합하기

**선행 조건: 박준형 3.4번 + 박준형 3.5번 + 임우형 4.4번 + 임우형 4.6번 + 임우형 4.8번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.**

- [ ] **3.6 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 각 서비스가 별도로 성공해도 모델에 실제로 전달되는 자료가 잘못되면 세 기술의 효과가 없다. SDK host 조립의 책임자가 모든 포트를 실제 구현으로 연결하고 요청 payload 기준으로 작동을 증명한다.

**담당:** 박준형  
**주요 산출물·수정 범위:** apps/host/src/app 조립; context-client; routes; cline/tools/plugins; 서비스 API 조립; 통합 fixture  
**검증 기록:** [3.6 BLOCKED 기록](docs/progress/tasks/3.6.md)

**2026-11-05 상태: BLOCKED** — 선행 4.4·4.6·4.8·4.9가 미완료다(체크 `[ ]`, 증거 파일 없음, Python `context/`·`pdf/` 패키지 없음). provider 키도 없어 live smoke를 할 수 없다. 코드는 바꾸지 않았다. 재개 조건은 검증 기록에 있다.

**완료 조건**

- [ ] 세 기능·PDF·Selector가 실제 SDK production 경로에 연결되고 mock 경로가 남지 않는다.
- [ ] provider payload/history에서 전체 index·큰 원문·미선택 페이지 유출이 없다.
- [ ] 실제 provider smoke·승인·취소·실패 차단 증거와 UI 연동 예제가 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.6 R0·포인터·Context Selector·PDF를 SDK 경로에 통합하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.4번 + 박준형 3.5번 + 임우형 4.4번 + 임우형 4.6번 + 임우형 4.8번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.6절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/host/src/app 조립; context-client; routes; cline/tools/plugins; 서비스 API 조립; 통합 fixture
수행할 일:
1. 3.4 R0, 4.4 Runtime hook, 4.6 Source, 4.8 Selector/ModelRequestGate, 4.9 PDF를 실제 host와 Python 서비스에 연결하라. fixture adapter는 테스트에서만 허용하고 production 실행에서는 남기지 마라.
2. 프로젝트 등록→index 준비→질문 R0 검색→context.select→최종 provider 입력 검사→SDK run→큰 도구 결과 저장/교체→필요 부분 재조회 흐름을 조립하라. initial context와 tool result가 중복 주입되지 않게 하라.
3. 나머지 pointer/source/context/pdf 공개 API를 service에 연결하라. 원본 외부 파일 허용 목록과 scope 검증은 서버에서 수행하고 모든 read/search 응답에 bytes/token cap을 적용하라.
4. SDK built-in read/search나 command 결과가 우리 경계를 우회하지 않는지 허용 도구 전체를 점검하라. source 본문 읽기는 Source adapter, 코드 검색은 R0, 실행 결과는 Runtime adapter로 수렴하게 하라.
5. provider 요청을 캡처하는 fixture로 무관한 sentinel 1,000개/대형 로그/PDF 미선택 페이지가 실제 모델 입력에 없음을 검사하라. canonical transcript에도 큰 원문이 남지 않는지 확인하라.
6. 실제 설정 provider smoke에서 R0 원문 근거, pointer 도구 호출·부분 읽기, 답변 출처를 확인하라. provider 키가 없으면 fixture 성공과 live 미실행을 분리하고 이 실연동 작업을 완료 처리하지 마라.
7. UI가 사용할 실행·실패 예제를 인계하고 통합 결함은 자신의 조립 코드에서 수정하라. 다른 담당자 정책 결함은 재현 자료를 인계해 원래 담당자가 자기 작업을 다시 열고 수정·검증하게 하라. 그동안 본 작업은 BLOCKED로 두고 해결 후 체크하라.

반드시 검증할 완료 조건:
- 세 기능·PDF·Selector가 실제 SDK production 경로에 연결되고 mock 경로가 남지 않는다.
- provider payload/history에서 전체 index·큰 원문·미선택 페이지 유출이 없다.
- 실제 provider smoke·승인·취소·실패 차단 증거와 UI 연동 예제가 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.6.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.6절의 조건 및 '3.6 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.7 백엔드 회귀 검사·구조 검사·로컬 실행 패키징 완료하기

**선행 조건: 박준형 3.6번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.**

- [ ] **3.7 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 개발자 컴퓨터에서 한 번 실행된 상태만으로는 다른 팀원이 제품을 재현할 수 없다. 백엔드 검증과 설치·기동·종료·데이터 정리 절차를 완성해 UI 최종 시험의 안정된 기반을 제공한다.

**담당:** 박준형  
**주요 산출물·수정 범위:** scripts; 루트 검사/빌드 설정; tests/integration; README.md; docs/release/RUNBOOK.md  
**검증 기록:** `docs/progress/tasks/3.7.md`

**완료 조건**

- [ ] 설치/기동/종료/빌드/검사 명령과 RUNBOOK이 다른 팀원에게 재현 가능하다.
- [ ] 백엔드·SDK·계약·구조 검사가 통과하며 무의미한 no-op 검사가 없다.
- [ ] 지원 범위·실 provider 설정·데이터 정리·오류 대응이 문서화돼 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.7 백엔드 회귀 검사·구조 검사·로컬 실행 패키징 완료하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.6번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.7절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: scripts; 루트 검사/빌드 설정; tests/integration; README.md; docs/release/RUNBOOK.md
수행할 일:
1. 3.2 명령 인터페이스의 미구현 부분을 모두 실제 명령으로 완성하라. npm run dev가 Python/host/UI를 readiness 순서로 기동하고 실패 시 이미 띄운 child를 정리하게 하라. stop/종료 신호·포트 충돌을 처리하라.
2. Node/Python 버전, npm ci/uv sync --locked, 환경변수 설정, SDK/model 구성, dev/build 실행, 테스트, 데이터 경로/TTL/정리/재시작 방법을 README와 RUNBOOK에 작성하라. 모델 키나 개인 데이터를 포함하지 마라.
3. 파일 길이/순환 의존/실험 코드 import/production mock/비밀값/금지 기법/미구현 placeholder 검사를 실제 구현하라. 과도한 파일은 역할별로 분리하고 필요한 예외는 근거를 남겨라.
4. 계약 fixture·Python unit/contract/integration·host integration·타입/lint/build를 실행하라. SDK+실 provider smoke 재현 명령을 별도로 제공하고 오프라인 시험과 섞지 마라.
5. 새 임시 실행 데이터 디렉토리에서 설치·기동·중단·재시작 smoke를 재현하라. 기존 사용자의 .securecode나 프로젝트 원본을 삭제하지 마라.
6. 알려진 지원 범위/제한, 검증된 버전, 담당자별 실패 시 수정 파일을 기록하고 1.6과 3.8에 인계하라. 원격 배포/commit/push는 수행하지 마라.

반드시 검증할 완료 조건:
- 설치/기동/종료/빌드/검사 명령과 RUNBOOK이 다른 팀원에게 재현 가능하다.
- 백엔드·SDK·계약·구조 검사가 통과하며 무의미한 no-op 검사가 없다.
- 지원 범위·실 provider 설정·데이터 정리·오류 대응이 문서화돼 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.7.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.7절의 조건 및 '3.7 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 3.8 전체 프로젝트 최종 인수와 실행 증거 확정하기

**선행 조건: 김민지 1.6번 + 김찬우 2.3번 + 박준형 3.7번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.**

- [ ] **3.8 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 네 사람의 작업 완료가 곧 프로젝트 완료가 되려면 마지막 판정 책임도 명확해야 한다. 박준형이 이미 완료된 UI·포인터·호스트를 함께 실행하고 UI 설계 인수표와 대조해 프로젝트 완료 조건을 증거로 확정한다.

**담당:** 박준형  
**주요 산출물·수정 범위:** docs/release/ACCEPTANCE_REPORT.md; artifacts/verification; 이 로드맵의 최종 완료 체크  
**검증 기록:** `docs/progress/tasks/3.8.md`

**완료 조건**

- [ ] 모든 담당 작업과 6절 인수 조건이 구현·검증 증거로 닫혔다.
- [ ] 실제 provider와 전체 UI/SDK/세 기술 통합이 통과하고 모델 입력의 제한을 확인했다.
- [ ] 최종 인수 보고서·실행 안내·지원 범위가 완성됐으며 commit/push는 하지 않았다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 3.8 전체 프로젝트 최종 인수와 실행 증거 확정하기
담당 역할: 박준형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 김민지 1.6번 + 김찬우 2.3번 + 박준형 3.7번 + 임우형 4.10번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 3.8절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/release/ACCEPTANCE_REPORT.md; artifacts/verification; 이 로드맵의 최종 완료 체크
수행할 일:
1. 모든 1.1~1.6, 2.1~2.3, 3.1~3.7, 4.1~4.10 체크와 작업 증거를 읽고 누락·실패·BLOCKED가 있으면 먼저 식별하라. 근거 없는 체크는 성공으로 신뢰하지 마라.
2. 새 임시 workspace와 fixture에서 6절의 필수 최종 인수 시나리오를 실행하라. 같은 코드/로그/PDF/토큰 설정을 이용한 원문 baseline 대비 입력량을 측정하되 제품 전체 정확도 향상을 근거 없이 주장하지 마라.
3. npm run check/test:contracts/test:integration/test:e2e/test:live/build의 필수 경로가 통과하는지 확인하라. live provider 미설정/실패는 최종 인수 미완료이며 mock 결과로 대체하지 마라.
4. UI→실제 Cline SDK→R0/Source/Runtime/PDF→승인/취소→출처 있는 응답과 startup/shutdown을 입증하라. 모델 요청과 history의 대형 원문 미포함, 전체 예산 준수도 확인하라.
5. 실패가 있으면 본인 담당 영역을 최소 수정하거나 소유자에게 재현 증거를 인계하라. 원래 소유자가 자기 작업의 체크를 다시 열어 수정·재검증하며 그동안 본 작업은 BLOCKED로 둬라. 타인의 체크를 직접 수정하지 말고 새 기술·추가 범위를 만들지 마라.
6. ACCEPTANCE_REPORT에 버전/환경/실행 명령/실측/통과 여부/제한/증거 위치를 기록하라. 모든 필수 항목이 통과할 때에만 3.8과 6절 최종 완료 체크를 갱신하라. 최종 보고는 실행 방법·검증 결과·남은 제한·팀원이 직접 할 commit/push 안내만 포함하라.

반드시 검증할 완료 조건:
- 모든 담당 작업과 6절 인수 조건이 구현·검증 증거로 닫혔다.
- 실제 provider와 전체 UI/SDK/세 기술 통합이 통과하고 모델 입력의 제한을 확인했다.
- 최종 인수 보고서·실행 안내·지원 범위가 완성됐으며 commit/push는 하지 않았다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/3.8.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 3.8절의 조건 및 '3.8 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

<a id="owner-4"></a>

## 4. 임우형의 역할 — Runtime·Source Pointer·Context Selector·PDF

포인터 설계부터 데이터 계약, 저장/조회/삭제, SDK 결과 교체, 부분 읽기, 예산 정책, PDF 도구/Skill와 통합 검증까지 담당한다.

### 4.1 Runtime·Source Pointer 통합 설계 문서 작성하기

**선행 조건: 박준형 3.1번 작업이 모두 완료된 이후에 진행.**

- [x] **4.1 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 포인터의 주소·수명·원본 의미를 먼저 정하지 않으면 저장소와 UI, SDK가 서로 다른 삭제·조회 동작을 가정한다. 실제 SDK 경계를 근거로 임우형이 맡을 전체 기능의 설계와 상한을 확정한다.

**담당:** 임우형  
**주요 산출물·수정 범위:** docs/architecture/POINTER_DESIGN.md; 3.2에 넘길 서비스 경계/정책 표  
**검증 기록:** `docs/progress/tasks/4.1.md`

**완료 조건**

- [x] 세 수명주기·scope·URI·버전·저장·삭제·상한 정책이 모순 없이 문서화됐다.
- [x] 실제 SDK hook 경계와 실패/누락 시 차단 요구가 확정됐다.
- [x] 3.2 골격/공통 계약을 시작할 서비스 포트와 검증 요구가 준비됐다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.1 Runtime·Source Pointer 통합 설계 문서 작성하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.1번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.1절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/architecture/POINTER_DESIGN.md; 3.2에 넘길 서비스 경계/정책 표
수행할 일:
1. 3.1 SDK 호환성 문서와 기존 Runtime/Source 실험을 읽어 현재 기능과 미구현을 구분하라. 기존 4자리 Runtime ID, process dict, 전체 read_text, 한글 제목 정규화 문제를 제품 요구로 옮겨라.
2. Runtime put→ready→read→expired/deleted, Source register→ready→changed/unregistered, PDF parsing→ready/unsupported/failed 수명주기를 정의하라. Source 원본 파일은 서비스가 삭제하지 않는다고 명시하라.
3. opaque URI, workspace/session scope, revision/fingerprint, metadata/blob 저장, 원자적 쓰기, 시작 시 복구, TTL/용량·동시성/정리 정책을 0.7 기본값과 맞춰 설계하라. 보호할 데이터와 사용자 원본/파생 캐시를 분리하라.
4. 박준형 SDK 호스트의 ToolResultTransformer/ModelRequestGate와 임우형 서비스의 책임을 정의하라. 원본 결과가 저장 전에 SDK에서 잘리는 경우와 hook timeout/실패/미등록 시 차단 방식을 명시하라.
5. Source 허용 root·외부 파일 명시 등록, bounded I/O, JSON 크기 제한, PDF 텍스트 추출 범위, Context Selector가 새 검색 기법이 아니라는 점을 설계에 포함하라.
6. 실패/재시작/세션 간 접근/삭제 시나리오와 검증 계획을 작성하고 3.2가 사용할 최소 인터페이스·의존성 요구를 인계하라. 아직 저장소 코드를 구현하거나 SDK API를 추측하지 마라.

반드시 검증할 완료 조건:
- 세 수명주기·scope·URI·버전·저장·삭제·상한 정책이 모순 없이 문서화됐다.
- 실제 SDK hook 경계와 실패/누락 시 차단 요구가 확정됐다.
- 3.2 골격/공통 계약을 시작할 서비스 포트와 검증 요구가 준비됐다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.1.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.1절의 조건 및 '4.1 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.2 포인터·조회·예산 데이터 구조와 API 명세 확정하기

**선행 조건: 임우형 4.1번 + 박준형 3.2번 작업이 모두 완료된 이후에 진행.**

- [x] **4.2 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 문자열 포인터만 정하면 조회 범위·오류·토큰 수를 소비자가 제각각 해석한다. Python 서비스와 TypeScript host/UI가 같은 payload를 검증할 수 있는 스키마와 예제를 만든다.

**담당:** 임우형  
**주요 산출물·수정 범위:** contracts/pointers, context 및 fixtures; docs/contracts/{POINTERS,CONTEXT}.md; 생성 타입  
**검증 기록:** `docs/progress/tasks/4.2.md`

후속 계약 검증에서 URI와 descriptor·참조의 종류 일치, Source의 만료 필드 거부, 페이지의 다음 cursor, 검색 결과 상한을 고정했다. 공개 UI에 필요한 범위 선택·등록·삭제·출처 필드는 [2.2 계약 보완 인계](docs/handoffs/2.2-ui-behavior-contract-gaps.md)에서 추적한다.

**완료 조건**

- [x] 포인터/selector/응답/예산/오류 JSON 계약과 단위·범위 규칙이 명확하다.
- [x] 성공/오류 fixture가 Python/TypeScript 양쪽에서 일치한다.
- [x] 목록·검색·cursor까지 크기와 scope 제한이 있고 다른 담당자가 생성 타입을 사용할 수 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.2 포인터·조회·예산 데이터 구조와 API 명세 확정하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.1번 + 박준형 3.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.2절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: contracts/pointers, context 및 fixtures; docs/contracts/{POINTERS,CONTEXT}.md; 생성 타입
수행할 일:
1. 3.2 공통 schema/error/event 계약에 맞춰 PointerDescriptor, SourceRegistration, RuntimePut, ReadRequest/Result, selector union, ContextCandidate/Plan을 정의하라. schema_version, revision, provenance, count_mode를 포함하라.
2. URI parser와 내부 registry 경계를 정의하고 pointer 문자열에 임의 파일 경로/실행 명령을 허용하지 마라. runtime 세션, source workspace, cursor의 scope/revision/query를 검증하도록 명세하라. source.search와 runtime.search 모두의 문자열 패턴/scan 상한/결과 줄 출처 계약을 포함하라.
3. line/byte/section/json_path/pdf_page selector별 인덱스 시작(줄/페이지 1부터, byte 0부터), 끝 범위 포함 여부(줄/페이지 양끝 포함, byte [start,end)), UTF-8 경계, max_bytes/max_tokens, truncated/next_cursor 규칙을 명시하라.
4. 목록·검색에 limit/cursor와 응답 bytes/token cap을 적용하라. 저장소/부분조회 오류군의 HTTP 상태·retryable·UI 의미를 정의하고 source.unregister가 원본을 지우지 않음을 계약화하라.
5. 성공·잘못된 URI·다른 세션·만료·원본 변경·예산 초과·미지원 형식 fixture를 만들고 Python/TS 양쪽 validator에서 같은 판정을 얻어라. generated 타입은 전용 위치에 두고 수기 중복 모델을 만들지 마라.
6. SDK 자체 타입과 우리의 DTO를 분리하라. 2.2/3.3/3.5/4.3/4.5/4.7에서 바로 사용할 공개 포트를 인계하라.

반드시 검증할 완료 조건:
- 포인터/selector/응답/예산/오류 JSON 계약과 단위·범위 규칙이 명확하다.
- 성공/오류 fixture가 Python/TypeScript 양쪽에서 일치한다.
- 목록·검색·cursor까지 크기와 scope 제한이 있고 다른 담당자가 생성 타입을 사용할 수 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.2.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.2절의 조건 및 '4.2 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.3 Runtime Pointer 저장·조회·삭제 MVP 구현하기

**선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [x] **4.3 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 실행 출력의 원문을 모델 밖에 안전하게 보관해야 짧은 주소로 반복 접근할 수 있다. 세션별 저장소와 수명주기부터 완성해 SDK hook이 신뢰할 수 있는 기반을 제공한다.

**담당:** 임우형  
**주요 산출물·수정 범위:** pointers/runtime, registry, models; runtime API; 저장소 단위/통합 시험  
**검증 기록:** `docs/progress/tasks/4.3.md`

**재사용할 구현** — 별도로 기동하는 레거시 FastAPI와 SQLite 저장소에서 Bearer 인증, 작업 공간·세션 격리, TTL, UTF-8 바이트 단위 이어 읽기를 검증했다. 새 Runtime URI는 `?v=1`로 발급한다. 정식 서비스 API, 세션 합산 용량, 검색·정리와 대량 발급 검증은 이 작업에 남아 있다. [레거시 API 실행 안내](services/context-service/README.md#레거시-runtime-pointer-api)

**완료 조건**

- [x] Runtime 저장·목록·부분 조회·삭제·세션 정리·TTL·재시작이 실디스크에서 작동한다.
- [x] 10,001회 발급·동시 저장·scope 격리·오류/용량 한도 시험을 통과한다.
- [x] 모든 응답/preview가 제한되며 원자성·정리·멱등 삭제가 확인됐다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.3 Runtime Pointer 저장·조회·삭제 MVP 구현하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.3절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: pointers/runtime, registry, models; runtime API; 저장소 단위/통합 시험
수행할 일:
1. 4.2 계약으로 RuntimeStore put/stat/list/read/search/delete/clear_session을 구현하라. UUID 계열 opaque ID와 SQLite metadata+개별 blob 등 디스크 저장을 사용하고 4자리 카운터/process dict를 제품 저장소로 쓰지 마라.
2. workspace/session scope를 매번 검증하고 원자적 임시 저장/rename, checksum, TTL, 객체/세션 용량 상한, 동시 저장, 취소·중단 시 cleanup, 재시작 복구를 구현하라. quota 정책은 오래된 자료를 조용히 덮어쓰지 말고 명확한 오류로 반환하라.
3. 제한된 preview와 text/log line/byte read, 한글 section 추출, JSON 크기 이하 구조 조회, runtime.search의 문자열 패턴 검색을 구현하라. 검색은 streaming scan·최대 scan bytes/timeout·match limit/cursor를 지원하고 결과에 줄 출처를 포함하라. 목록과 검색에 body 상한을 적용하고 bounded read가 다시 새 pointer로 무한 감싸지지 않게 식별하라. 본문 token cap은 3.2의 TokenCounter를 사용하라.
4. delete는 runtime blob/metadata만 제거하며 재호출은 멱등적으로 처리하라. 만료·삭제된 포인터는 정상 원문 대신 명확한 상태를 반환하고 세션 종료 정책과 sweep을 분리하라.
5. 10,001개 작은 객체 발급/조회, 동시 put, scope 위반, 삭제/TTL, quota/디스크 오류, 재시작, 긴 한 줄·한글을 검증하라. 비밀값·원문을 테스트 로그에 불필요하게 저장하지 마라.
6. 4.4 hook이 사용할 스트리밍 저장/descriptor 반환 포트와 실제 오류 예제를 인계하라.

반드시 검증할 완료 조건:
- Runtime 저장·목록·부분 조회·삭제·세션 정리·TTL·재시작이 실디스크에서 작동한다.
- 10,001회 발급·동시 저장·scope 격리·오류/용량 한도 시험을 통과한다.
- 모든 응답/preview가 제한되며 원자성·정리·멱등 삭제가 확인됐다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.3.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.3절의 조건 및 '4.3 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.4 Cline 도구 출력의 Runtime Pointer 교체 hook 연결하기

**선행 조건: 임우형 4.3번 + 박준형 3.5번 작업이 모두 완료된 이후에 진행.**

- [x] **4.4 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 저장소만 있으면 Cline이 여전히 원문 전체를 읽을 수 있다. SDK의 모델 입력과 대화 이력에 들어가기 전에 결과를 실제로 교체하고 실패 시 원문 유출을 막는다.

**담당:** 임우형  
**주요 산출물·수정 범위:** apps/host/src/pointer-hooks; 프로젝트 소유 command executor 연결; Runtime SDK 통합 시험  
**검증 기록:** `docs/progress/tasks/4.4.md`

**재사용할 구현** — 설치된 SDK의 `afterTool`에서 64 KiB 출력을 한 번 저장하고, 그 원문 대신 포인터가 다음 모델 요청 본문과 SDK 대화 기록에 들어가는 것을 오프라인으로 확인했다. 3.5 운영 세션과 4.3 정식 저장소에 연결한 뒤 승인된 명령, 취소·저장 실패, SSE까지 검증한다. [SDK 통합 시험](apps/host/tests/integration/runtimePointerPlugin.test.ts)

**완료 조건**

- [x] 실제 SDK 결과가 모델 입력/history 전에 포인터로 교체되고 부분 재조회가 된다.
- [x] 저장 실패·timeout·미등록 hook·취소에서 원문 fallback이 없고 SSE에도 유출되지 않는다.
- [x] streaming 결과/이미 잘린 결과/제한된 read 결과의 서로 다른 정책을 검증했다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.4 Cline 도구 출력의 Runtime Pointer 교체 hook 연결하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.3번 + 박준형 3.5번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.4절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: apps/host/src/pointer-hooks; 프로젝트 소유 command executor 연결; Runtime SDK 통합 시험
수행할 일:
1. 기존 apps/host/src/cline/plugins/runtimePointerPlugin.ts의 hooks.afterTool을 3.5 ToolResultTransformer 및 4.3 저장소에 연결하라. 임계값 미만은 제한 검증 후 유지하고, 임계값 이상은 저장한 뒤 짧은 descriptor로 result를 교체하라. appendContext만 더하지 마라.
2. command stdout/stderr처럼 매우 큰 출력은 프로젝트 소유 executor에서 streaming 저장해 전체 문자열을 먼저 메모리에 만들지 않게 하라. SDK에서 이미 잘린 결과는 captured/truncated와 원본 보존 범위를 정확히 표시하라.
3. runtime.read/search를 등록하고 source.read/pdf.read 같은 bounded_read 도구는 재귀 포인터화를 금지하며 자체 cap/cursor를 검사하라. 아직 미완료인 Source/PDF는 4.2 계약 fixture로 정책만 검사하고 실제 도구 검증은 3.6에서 하라. 구조화 JSON의 상태·exit code·도구 오류를 포인터 교체 때 잃지 마라.
4. pointer hook 등록/준비 완료를 확인한 뒤 SDK 세션을 시작하고 미등록·비활성·저장 실패·timeout·취소 시 fail-closed로 중단하라. await 누락이나 기본 ignore 설정으로 원문이 fallback 전달되지 않게 하라.
5. 실제 SDK 두 번 이상 turn을 돌려 provider payload, canonical history, SDK→AppEvent→SSE의 모든 경계에서 큰 sentinel이 없고 pointer/제한된 preview만 있는지 검증하라. 이벤트 raw payload를 UI에 pass-through하지 마라.
6. 승인된 명령 결과→pointer→필요 line 재조회 성공, 승인 거절 시 미실행, 실패/만료/세션 종료를 시험하라. 후속 3.6 조립에 필요한 registration과 정책 설정을 인계하라.

반드시 검증할 완료 조건:
- 실제 SDK 결과가 모델 입력/history 전에 포인터로 교체되고 부분 재조회가 된다.
- 저장 실패·timeout·미등록 hook·취소에서 원문 fallback이 없고 SSE에도 유출되지 않는다.
- streaming 결과/이미 잘린 결과/제한된 read 결과의 서로 다른 정책을 검증했다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.4.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.4절의 조건 및 '4.4 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.5 Source Pointer 등록·버전·등록 해제 구현하기

**선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.5 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 디스크 파일은 Runtime 결과와 달리 사용자가 수정하거나 지울 수 있다. 주소에 실제 경로를 드러내지 않고 원본 변경·접근 범위·등록 해제를 일관되게 관리한다.

**담당:** 임우형  
**주요 산출물·수정 범위:** pointers/source의 registry/lifecycle; Source API; 파일 정책 시험  
**검증 기록:** `docs/progress/tasks/4.5.md`

**재사용할 구현** — 현재 Source 등록부는 메모리에서 작업 공간별 파일 등록·중복 처리·등록 해제를 수행하고, 등록한 파일이 교체되면 기존 ID의 읽기를 거절한다. 디스크 등록부, 재시작 복구, 공개 등록·해제 계약은 후속 범위다. [등록부 회귀 시험](services/context-service/tests/unit/test_source_store.py)

**완료 조건**

- [ ] Source 등록/목록/stat/등록 해제가 디스크 registry로 동작하고 scope가 격리된다.
- [ ] 경로 이탈·원본 변경/삭제·중복 등록·재시작에 대한 상태가 정확하다.
- [ ] 등록 해제 뒤 원본 파일이 존재하며 provenance/resolve 계약이 준비됐다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.5 Source Pointer 등록·버전·등록 해제 구현하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.5절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: pointers/source의 registry/lifecycle; Source API; 파일 정책 시험
수행할 일:
1. SourceStore register/stat/list/unregister를 4.2 계약으로 구현하라. opaque source ID와 workspace scope, 내부 실제 경로, 원본 fingerprint/revision, media type, available_operations를 저장하라.
2. 프로젝트 내부 허용 root와 사용자가 명시적으로 등록한 외부 파일/디렉토리 허용 목록을 분리하라. realpath/symlink/../상대경로/정규화·확장자 위장을 검사하고 API에서 보낸 임의 경로를 자동 신뢰하지 마라.
3. 파일 크기/유형 상한을 검사하고 stat 변경 시 hash 재확인과 revision 갱신 정책을 구현하라. register 중 파일이 바뀌거나 사라지는 경우 실패로 처리하고 다른 본문과 기존 fingerprint를 섞지 마라.
4. unregister는 registry와 우리 파생 캐시만 지우고 사용자 원본은 보존하라. 캐시가 여러 source에서 공유될 때 참조 수 또는 안전한 소유권 정책을 적용하라.
5. 정상 파일·중복 등록·다른 workspace·symlink escape·허용되지 않은 외부 파일·수정/삭제·등록 해제·재시작을 검증하라. 재시작 후 경로 권한을 다시 확인하라.
6. 3.3 심볼 provenance와 4.6/PDF가 사용할 stat/resolve 포트를 제공하라. 본 작업의 완료가 실제 bounded read 완료를 의미하지 않도록 구분하라.

반드시 검증할 완료 조건:
- Source 등록/목록/stat/등록 해제가 디스크 registry로 동작하고 scope가 격리된다.
- 경로 이탈·원본 변경/삭제·중복 등록·재시작에 대한 상태가 정확하다.
- 등록 해제 뒤 원본 파일이 존재하며 provenance/resolve 계약이 준비됐다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.5.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.5절의 조건 및 '4.5 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.6 Source Pointer 파일 부분 읽기·검색·변경 감지 구현하기

**선행 조건: 임우형 4.5번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.6 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 전체 파일을 읽은 뒤 응답만 자르는 것은 큰 외부 파일의 메모리 문제를 해결하지 못한다. 범위 읽기와 검색을 제한된 I/O로 구현하고 읽는 도중 바뀐 자료를 정상 결과로 내보내지 않는다.

**담당:** 임우형  
**주요 산출물·수정 범위:** pointers/source/{readers,index,search} 등 기능별 모듈; bounded I/O 시험  
**검증 기록:** `docs/progress/tasks/4.6.md`

현재 Source 텍스트 읽기는 파일을 작은 단위로 순차 스캔하고 UTF-8 바이트 한도를 지킨다. 뒤쪽 줄을 반복 조회할 때의 seek 인덱스, 검색·JSON 선택자, 토큰 한도와 revision에 묶인 cursor는 이 작업에서 구현·계측한다.

**완료 조건**

- [ ] 텍스트 반복 범위 읽기가 실제 bounded I/O이며 계측 근거가 있다.
- [ ] UTF-8/한글/긴 줄/검색/JSON 제한과 bytes/token cap·cursor가 작동한다.
- [ ] 읽기 도중 변경·stale cursor·경로 이탈을 거부하고 정확한 출처를 반환한다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.6 Source Pointer 파일 부분 읽기·검색·변경 감지 구현하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.5번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.6절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: pointers/source/{readers,index,search} 등 기능별 모듈; bounded I/O 시험
수행할 일:
1. text/log/Markdown의 byte/line/section 조회를 line offset index, seek, streaming으로 구현하라. 최초 인덱스/검색은 순차 scan일 수 있음을 문서화하고 반복 범위 조회에 전체 read_text를 사용하지 마라.
2. UTF-8 multibyte/CRLF/긴 한 줄/한글 제목·검색을 처리하고 정규화에서 한글을 지우지 마라. 줄/byte 범위 규칙과 잘못된 범위 오류를 지켜라. 검색은 bounded result와 이어읽기 cursor를 사용하라.
3. JSON path는 0.7 최대 크기 이하로 제한하고 실제 전체 파싱이라는 사실을 표시하라. 큰 JSON은 허용된 byte/line 읽기 또는 크기 오류를 제공하고 무제한 구조 조회를 구현했다고 쓰지 마라.
4. 요청 전과 읽기 완료 시 fingerprint/stat를 확인하고 읽는 도중 원본이 바뀌면 SOURCE_CHANGED로 반환하라. cursor도 revision에 묶고 오래된 cursor로 새 원문을 읽지 마라. 원문+출처/hash의 일치가 우선이다.
5. 64 MiB 이상 텍스트 fixture의 작은 범위 조회로 bytes read/최대 buffer를 계측하라. 반복 조회가 전체 파일 크기만큼 읽지 않는지, 응답 bytes/token cap과 cursor 연속 범위를 검증하라.
6. 경로 재검증·세션 접근·손상 인코딩·중간 변경·원본 삭제를 시험하고 Source adapter를 3.6/4.8/4.9에 인계하라.

반드시 검증할 완료 조건:
- 텍스트 반복 범위 읽기가 실제 bounded I/O이며 계측 근거가 있다.
- UTF-8/한글/긴 줄/검색/JSON 제한과 bytes/token cap·cursor가 작동한다.
- 읽기 도중 변경·stale cursor·경로 이탈을 거부하고 정확한 출처를 반환한다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.6.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.6절의 조건 및 '4.6 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.7 Context Selector의 우선순위·예산·실패 정책 설계하기

**선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.7 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 세 기능이 각각 제한을 지켜도 합친 컨텍스트는 모델 창을 넘을 수 있다. 선택과 실제 원문 조회, 최종 예산 검사까지 누가 책임지는지 먼저 확정해 중복 삽입과 예산 누락을 막는다.

**담당:** 임우형  
**주요 산출물·수정 범위:** docs/architecture/CONTEXT_SELECTOR.md; contracts/context 세부 정책/fixture  
**검증 기록:** `docs/progress/tasks/4.7.md`

**완료 조건**

- [ ] 우선순위·중복·score·materialize·총 요청 예산·실패 정책이 완결돼 있다.
- [ ] 명시 선택/0 예산/무결과/권한/대형 후보의 기대 결과 fixture가 있다.
- [ ] host와 Selector의 책임이 겹치지 않고 새 검색·요약 기법을 추가하지 않는다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.7 Context Selector의 우선순위·예산·실패 정책 설계하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.2번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.7절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: docs/architecture/CONTEXT_SELECTOR.md; contracts/context 세부 정책/fixture
수행할 일:
1. 0.7 예산식을 바탕으로 system/tool schema/user/history/message overhead/output reserve/safety margin과 검색 자료 예산을 구분하라. 실제 provider/tokenizer가 검증되지 않은 수치를 exact로 표시하지 마라.
2. 허용 scope·revision 검증→후보 메타데이터 평가→명시 선택 우선→현재 요청 연관 자료→R0 점수→stable ID 동점 순서를 정의하라. 후보가 많을 때 상한과 source별 score 정규화 규칙을 명시하라.
3. Selector가 선택한 후보를 각 resolver로 bounded materialize하고 실제 fragment 계수/중복 제거/재포장까지 수행하도록 계약하라. ContextPlan은 selected metadata와 제한된 fragments를 구분하고 host는 fragments를 한 번만 삽입한다.
4. 이미 history에 있는 pointer/원문 범위 중복, tool-call/result 쌍 보존, 0/음수 예산, 명시 선택도 초과하는 경우, no_match/stale/unauthorized/large_fragment 누락 이유를 정의하라.
5. 토큰 부족 시 새 요약기·전체 파일 fallback을 사용하지 말고 범위 축소/새 세션을 안내하라. 지원 provider의 최종 outbound payload 검사·차단 책임과 exact/estimated/unsupported 모드를 구분하라.
6. 손으로 계산 가능한 작은 후보 fixture에 대해 예산별 선택/누락/순서와 materialized 결과를 작성하고 계약 검증을 수행하라. 이 작업은 정책 설계이며 구현은 4.8에서 한다.

반드시 검증할 완료 조건:
- 우선순위·중복·score·materialize·총 요청 예산·실패 정책이 완결돼 있다.
- 명시 선택/0 예산/무결과/권한/대형 후보의 기대 결과 fixture가 있다.
- host와 Selector의 책임이 겹치지 않고 새 검색·요약 기법을 추가하지 않는다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.7.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.7절의 조건 및 '4.7 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.8 Context Selector와 최종 모델 요청 예산 게이트 구현하기

**선행 조건: 임우형 4.7번 + 박준형 3.4번 + 임우형 4.4번 + 임우형 4.6번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.8 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 설계된 예산 규칙을 실제 코드로 적용해야 큰 로그를 포인터로 바꾼 뒤에도 요청이 한도를 넘지 않는다. 결정적 선택과 원문 조회를 구현하고 SDK의 실제 요청 경계에서 다시 검증한다.

**담당:** 임우형  
**주요 산출물·수정 범위:** context/{models,policy,budget}; host pointer-hooks의 model gate; 예산 통합 시험  
**검증 기록:** `docs/progress/tasks/4.8.md`

**완료 조건**

- [ ] 선택→부분 원문 조회→계수·중복 제거→제한된 ContextPlan 반환이 동작한다.
- [ ] SDK 실제 outbound 경계에서 검증된 예산을 지키고 미지원 정확 계수는 차단한다.
- [ ] 0/음수 예산·여러 turn·권한/stale·중복에서 재현 가능한 결과와 누락 사유가 있다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.8 Context Selector와 최종 모델 요청 예산 게이트 구현하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.7번 + 박준형 3.4번 + 임우형 4.4번 + 임우형 4.6번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.8절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: context/{models,policy,budget}; host pointer-hooks의 model gate; 예산 통합 시험
수행할 일:
1. 4.7 정책을 순수 선택 함수와 resolver orchestration, 최종 요청 budget adapter로 분리하라. 3.2의 본문 TokenCounter를 재사용하고 provider framing/전체 요청 gate를 확장하라. R0/Source/Runtime 후보는 scope/revision 검증 후 제한된 개수로 받고 metadata 선택→bounded materialize→원문 중복 제거→실계수 재포장을 수행하라.
2. 같은 source hash+range, 같은 runtime object+range가 중복 삽입되지 않게 하라. user 명시 선택도 cap을 넘기지 않으며 제외 이유·남은 budget·count_mode를 ContextPlan에 반환하라.
3. 3.5 ModelRequestGate에 연결해 매 모델 호출에서 system/tools/user/history와 직렬화 overhead/output reserve를 포함해 검증하라. beforeModel 이후 provider 변환이 추가된다면 3.1에서 검증한 마지막 outbound 경계의 계수/차단 방법을 사용하라.
4. 정확한 tokenizer 및 provider framing이 검증된 모델만 strict 모드를 지원하라. 그 외는 추정치라고 표시하고 필수 hard-cap 모드에서는 TOKENIZER_UNAVAILABLE 또는 명시적 미지원으로 차단하라. tool-call/result 쌍을 잘라 요청을 손상시키지 마라.
5. raw result 임계값/부분 읽기 cap과 전체 요청 예산을 연결하되 이전 history를 무제한 다시 삽입하지 마라. 예산이 음수면 provider 호출 없이 BUDGET_EXCEEDED를 반환하라.
6. 동일 입력 결정성·0/경계/초과 예산·Unicode·한글·도구 schema가 큰 경우·여러 turn·중복·stale·권한 위반을 시험하라. 실제 SDK outbound payload가 검증된 cap을 지키는 증거를 남기고 3.6에 인계하라.

반드시 검증할 완료 조건:
- 선택→부분 원문 조회→계수·중복 제거→제한된 ContextPlan 반환이 동작한다.
- SDK 실제 outbound 경계에서 검증된 예산을 지키고 미지원 정확 계수는 차단한다.
- 0/음수 예산·여러 turn·권한/stale·중복에서 재현 가능한 결과와 누락 사유가 있다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.8.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.8절의 조건 및 '4.8 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.9 PDF 파싱·Source Pointer 연동·Skill 도구 구현하기

**선행 조건: 임우형 4.6번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.9 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** PDF를 통째로 모델에 보내는 대신 페이지별 텍스트를 주소로 읽게 해야 Source Pointer가 외부 문서에서도 작동한다. 파서와 도구, 사용 지침을 함께 제공해 Cline이 올바른 순서로 사용할 수 있게 한다.

**담당:** 임우형  
**주요 산출물·수정 범위:** pdf/{parser,cache,tools}; PDF API/job; skills/pdf-pointer/SKILL.md; PDF fixture/시험  
**검증 기록:** `docs/progress/tasks/4.9.md`

**완료 조건**

- [ ] 텍스트 PDF가 페이지 캐시와 Source Pointer로 연결되고 전체 본문을 반환하지 않는다.
- [ ] 실제 PDF 도구 계약과 SKILL.md 사용 지침·등록 export가 일치한다.
- [ ] 한글/페이지 범위/출처/캐시 갱신/미지원/손상·취소 시험이 통과한다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.9 PDF 파싱·Source Pointer 연동·Skill 도구 구현하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 임우형 4.6번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.9절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: pdf/{parser,cache,tools}; PDF API/job; skills/pdf-pointer/SKILL.md; PDF fixture/시험
수행할 일:
1. Python PDF 라이브러리를 검증해 텍스트 PDF parser를 기능별 파일로 구현하라. 파일 크기/페이지/시간 상한, job 상태·취소·실패 정리를 지원하고 OCR·암호 해제를 추가하지 마라.
2. register/parse는 Source descriptor+page_count+job 상태만 반환하라. 전체 추출 텍스트를 tool response/history에 넣지 마라. 원본 hash+parser version을 cache key로 하고 페이지별 UTF-8 텍스트와 원본 페이지 provenance를 저장하라.
3. pdf.status/read_pages를 Source의 bounded selector로 연결하고 요청 페이지의 지정 범위만 반환하라. 원본 변경 시 stale·재파싱, 중복 parse job의 재사용/멱등 정책, unregister 시 파생 캐시 정리를 구현하라.
4. skills/pdf-pointer/SKILL.md에 등록→파싱 확인→페이지/절 검색→필요 범위 읽기→출처 인용 순서, 실제 도구명/입출력 예, 제한/오류/예산 규칙을 작성하라. 네 번째 검색 기술이나 다른 서비스의 skill로 만들지 마라.
5. 해당 SKILL.md의 지침이 앱 소유 PDF tool registry/SDK prompt loader에 명시적으로 연결되게 export하라. 파일이 있다는 이유만으로 SDK가 자동 로드한다고 가정하지 말고 3.6에서 등록 검증할 fixture를 제공하라.
6. 한글/여러 페이지/빈 페이지/스캔/손상/암호화/페이지 초과 fixture를 시험하라. 페이지 2 요청에 페이지 1/3 sentinel이 없고 출처 번호가 정확한지, 원문 변경/timeout에서 정상 처리로 오인하지 않는지 검증하라.

반드시 검증할 완료 조건:
- 텍스트 PDF가 페이지 캐시와 Source Pointer로 연결되고 전체 본문을 반환하지 않는다.
- 실제 PDF 도구 계약과 SKILL.md 사용 지침·등록 export가 일치한다.
- 한글/페이지 범위/출처/캐시 갱신/미지원/손상·취소 시험이 통과한다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.9.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.9절의 조건 및 '4.9 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

### 4.10 포인터·예산·PDF의 실제 SDK 통합 회귀 검증 완료하기

**선행 조건: 박준형 3.6번 + 임우형 4.8번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.**

- [ ] **4.10 완료** — 구현/설계·검증·증거 기록 후에만 체크

**왜 필요한가 / 무엇을 하는가:** 포인터 기능은 오류가 나도 원문을 그대로 보내면 겉으로는 답변이 성공할 수 있다. 임우형이 실제 통합 경로에서 저장·조회·교체·예산 불변식을 끝까지 확인해 자신의 기능 범위를 닫는다.

**담당:** 임우형  
**주요 산출물·수정 범위:** services/context-service tests; tests/integration의 pointer/context/PDF 시나리오; 운용 인계 문서  
**검증 기록:** `docs/progress/tasks/4.10.md`

**완료 조건**

- [ ] SDK 통합 경로에서 Runtime·Source·예산·PDF 수명주기와 오류 경로가 통과한다.
- [ ] 모델/history/SSE에 큰 원문이 없고 예산·scope·revision·부분 읽기 불변식이 유지된다.
- [ ] 실 provider 증거와 복구/지원 범위 안내가 있어 후속 인수 작업이 재현 가능하다.

**LLM에 그대로 붙여넣을 실행 프롬프트**

```text
작업: 4.10 포인터·예산·PDF의 실제 SDK 통합 회귀 검증 완료하기
담당 역할: 임우형
작업 루트: 2nd/Project (현재 checkout의 저장소 루트 기준)
로드맵: INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md (작업 루트 기준)
경로 처리: 저장소 루트(1st/와 2nd/가 있는 디렉토리)를 확인하고 작업 루트로 이동하라. 이미 작업 루트에 있으면 그대로 유지하라. 이후 파일 경로와 명령은 작업 루트 기준으로 해석하고, 특정 사용자 홈·컴퓨터의 경로를 하드코딩하지 마라.
선행 조건: 박준형 3.6번 + 임우형 4.8번 + 임우형 4.9번 작업이 모두 완료된 이후에 진행.

먼저 적용되는 AGENTS.md, 위 로드맵의 0절과 4.10절, 선행 작업의 docs/progress/tasks/<번호>.md를 읽어라. 선행 체크와 실제 산출물을 확인하고 미완료/실패이면 이 작업을 BLOCKED로 기록하며 완료 체크하지 마라. 기존 사용자 변경과 다른 담당 파일을 보존하고 이미 끝난 범위는 재생성하지 마라.
CODING_CONVENTIONS.md를 반드시 읽고 코딩컨벤션을 준수하라. Python은 원본 규약, TypeScript/React는 docs/conventions/TYPESCRIPT_REACT.md 및 로드맵 0.5를 따른다. 보완 규약 파일이 아직 없으면 0.5를 적용하고 생성을 기다리지 마라. 정식 보완 규약 작성은 3.2 담당이다. 설계만 하는 작업도 코드 예시와 계약 이름에 같은 규약을 적용하라.
올바른 디렉토리 구조와 파일 분할을 반드시 지켜라. production 파일 300줄/테스트 500줄 기준, 단일 책임, UI·상태·API·SDK·저장·파서 분리를 적용하고 거대한 한 파일/임시 파일 난립/실험 실행기 의존을 만들지 마라.
적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 이 기능의 조정/추출 계층이다. RAPTOR·요약 트리·H의 LLM selector·임베딩·Self-Extend를 추가하지 마라.
git commit과 git push는 팀원이 직접 한다. 두 명령을 직접/SDK/스크립트로 실행하지 말고 자동 checkpoint도 켜지 마라. 사용자 변경을 reset/삭제하지 마라.

주요 산출물·수정 범위: services/context-service tests; tests/integration의 pointer/context/PDF 시나리오; 운용 인계 문서
수행할 일:
1. 3.6 실제 SDK host/service에 연결된 Runtime/Source/Selector/PDF를 검증하라. 4.3~4.9 단위 시험만 다시 보고 통합 완료라고 하지 마라.
2. 작은 도구 결과 원문 유지, 큰 결과 pointer 교체, pointer 부분 재조회, 동일 세션 여러 turn, 다른 세션 접근 차단, TTL/삭제/재시작, 용량/디스크 오류·timeout·취소를 실행하라.
3. 큰 Source text 반복 조회와 조회 도중 변경, JSON 상한, PDF 페이지/원본 hash/parser version/캐시 갱신, Skill 지침의 실제 SDK 등록을 확인하라.
4. 원문 sentinel이 provider 요청·canonical history·SSE·UI 상태에 남지 않는지, 요청당 전체 예산과 목록/검색/부분 read 상한이 지켜지는지 검사하라. 잘못된 hook 등록/비활성 fixture에서도 요청이 차단돼야 한다.
5. 실제 provider의 pointer 도구 조회·출처 있는 응답을 최소 한 번 확인하고 mock/실행 결과를 구분하라. 문제는 본인 소유 정책·서비스·hook에서 수정하고 host 조립 결함은 재현 증거를 3.6에 반영해 닫아라.
6. 저장 위치/TTL/용량/캐시 재생성/원본 보존/지원 형식/문제 복구를 문서화하고 3.7·1.6 담당자에게 인계하라. 필수 live 검증이 없거나 실패한 상태에서는 체크하지 마라.

반드시 검증할 완료 조건:
- SDK 통합 경로에서 Runtime·Source·예산·PDF 수명주기와 오류 경로가 통과한다.
- 모델/history/SSE에 큰 원문이 없고 예산·scope·revision·부분 읽기 불변식이 유지된다.
- 실 provider 증거와 복구/지원 범위 안내가 있어 후속 인수 작업이 재현 가능하다.

구현 후 해당 작업에 필요한 타입/lint/계약/행동 검증을 실제로 실행하라. 설계 작업은 화면 명세·스키마·요구 대응의 모순/누락을 검증하라. 실행하지 않은 검증, mock만 통과한 실연동, 실패한 live 검증을 성공으로 기록하지 마라.
docs/progress/tasks/4.10.md에 task_id/owner/status/시각/선행 증거/변경 파일/실제 명령과 결과/인수 근거/제한/다음 인계를 기록하라. 모든 조건이 충족될 때만 로드맵 4.10절의 조건 및 '4.10 완료'를 [x]로 바꿔라. 미충족이면 [ ]를 유지하고 원인·재개 방법을 기록하라. 다른 담당자의 체크는 수정하지 마라.
마지막 응답에는 완료 범위, 검증 결과, 남은 문제, 다음 시작 가능한 작업을 짧게 보고하라. commit/push는 하지 않았다고 명시하라.
```

<a id="schedule"></a>

## 5. 전체 진행 순서와 인계 지도

번호는 담당자별 분류다. 실제 실행 순서는 선행 작업으로 결정한다. 아래 라운드는 **모든 사람의 최대 병렬 진행 예시**이며 날짜/기간을 약속하는 일정이 아니다. 같은 담당자의 두 작업이 한 라운드에 있으면 그 안에서 순차 처리해도 된다. 각 작업의 선행 조건이 충족되면 다른 라운드 전체를 기다릴 필요가 없다.

| 의존 라운드 | 시작 가능한 작업 | 이번 단계의 목적 |
|---|---|---|
| 1 | 김찬우 2.1번<br>박준형 3.1번 | 제품 화면·사용 흐름·인수 범위 설계하기 / 실제 Cline SDK 버전과 필수 확장점 검증하기 |
| 2 | 임우형 4.1번 | Runtime·Source Pointer 통합 설계 문서 작성하기 |
| 3 | 박준형 3.2번 | 모듈 기반 프로젝트 골격·공통 계약·개발 명령 확정하기 |
| 4 | 김민지 1.1번<br>임우형 4.2번 | UI 실행 기반과 공용 컴포넌트 만들기 / 포인터·조회·예산 데이터 구조와 API 명세 확정하기 |
| 5 | 김찬우 2.2번<br>박준형 3.3번<br>박준형 3.5번<br>임우형 4.3번<br>임우형 4.5번<br>임우형 4.7번 | 화면별 표시·사용자 동작 상세 명세 작성하기 / 5개 언어의 심볼·정적 참조·원문 색인과 갱신 구현하기 / Cline SDK 호스트와 UI용 실행·승인·이벤트 API 구현하기 / Runtime Pointer 저장·조회·삭제 MVP 구현하기 / Source Pointer 등록·버전·등록 해제 구현하기 / Context Selector의 우선순위·예산·실패 정책 설계하기 |
| 6 | 김민지 1.2번<br>박준형 3.4번<br>임우형 4.4번<br>임우형 4.6번 | 계약 fixture로 전체 업무 화면 구현하기 / R0 TF-IDF 검색과 제한된 Symbol Bundle 구현하기 / Cline 도구 출력의 Runtime Pointer 교체 hook 연결하기 / Source Pointer 파일 부분 읽기·검색·변경 감지 구현하기 |
| 7 | 김민지 1.3번<br>임우형 4.8번<br>임우형 4.9번 | 화면 상태 관리와 사용자 동작 구현하기 / Context Selector와 최종 모델 요청 예산 게이트 구현하기 / PDF 파싱·Source Pointer 연동·Skill 도구 구현하기 |
| 8 | 김민지 1.4번<br>김찬우 2.3번<br>박준형 3.6번 | 실제 프로젝트·Cline 실행 API와 SSE 연결하기 / 구현 화면의 설계 검토와 최종 인수표 작성하기 / R0·포인터·Context Selector·PDF를 SDK 경로에 통합하기 |
| 9 | 김민지 1.5번<br>임우형 4.10번 | R0·포인터·PDF·컨텍스트 예산 화면을 실서비스에 연결하기 / 포인터·예산·PDF의 실제 SDK 통합 회귀 검증 완료하기 |
| 10 | 박준형 3.7번 | 백엔드 회귀 검사·구조 검사·로컬 실행 패키징 완료하기 |
| 11 | 김민지 1.6번 | UI 오류 수정과 전체 사용자 흐름 인수 시험 완료하기 |
| 12 | 박준형 3.8번 | 전체 프로젝트 최종 인수와 실행 증거 확정하기 |

### 5.1 담당별 작업 종료와 인계

| 담당자 | 작업 수 | 본인 역할의 종료 | 인계받는 최종 작업 |
|---|---:|---|---|
| 김민지 | 6 | 1.1~1.6: UI·화면 상태·사용자 동작 구현·수정·실 API 연결·UI 인수 완료 | 박준형 3.8 |
| 김찬우 | 3 | 2.1~2.3: 화면 설계·상세 명세·설계 검토·인수표 완료 | 김민지 1.6, 박준형 3.8 |
| 박준형 | 8 | 3.1~3.8: SDK·기반·R0·API·조립·실행 패키징·최종 인수 완료 | 프로젝트 완료 |
| 임우형 | 10 | 4.1~4.10: 설계·계약·Runtime·Source·예산·PDF·통합 검증 완료 | 박준형 3.7/3.8, 김민지 1.6 |

초기 착수는 **김찬우 2.1과 박준형 3.1을 병렬 실행**한다. 3.1 뒤 임우형 4.1, 이어 박준형 3.2가 공통 기반을 열면 UI 설계 상세화·화면 구현·R0·두 포인터를 나누어 진행할 수 있다. 최종 종료 지점은 **박준형 3.8 하나**다.

계약 수정이 필요한 경우 변경 원인·새 schema version·영향 파일·담당 작업을 `docs/handoffs/<작업번호>-<주제>.md`에 기록하고 해당 소유자 작업에서 반영한다. 통합 담당자가 다른 영역의 비공개 내부 코드에 직접 의존해 우회하지 않는다. 수정으로 기존 검증이 무효가 되면 관련 작업을 다시 열어 검증한다.

### 5.2 진행 확인 규칙

진행률의 기준은 각 작업의 **굵은 작업번호 완료 체크** 27개다. 하위 완료 조건 체크와 F1~F11은 작업 개수에 더하지 않는다. 작업별 증거 파일의 status와 이 체크가 다르면 증거를 확인해 정정한다. 단순히 체크박스 수만 세어 완료율을 과대 계산하지 않는다.

예시: `3.4 완료`가 `[x]`여도 `4.8 완료`가 `[ ]`이면 R0 검색은 완성됐지만 총 요청 예산 적용은 아직 진행 중이다. `1.2 완료`는 fixture UI 완성이며 실 API 연결 완료는 `1.4`/`1.5`에서 판단한다.


<a id="acceptance"></a>

## 6. 프로젝트 최종 완료 조건

아래 체크는 **박준형 3.8에서만**, 증거를 확인한 뒤 갱신한다. 담당별 대표 체크박스와 중복된 진행률 집계가 아니라 최종 제품 인수 조건이다.

- [ ] **F1 — 재현 가능한 실행:** README대로 설치·설정하면 UI, SDK host, Python 서비스가 함께 시작되고 종료된다. 환경/의존성은 고정돼 있고 원본 연구 폴더 없이 제품 모듈이 실행된다.
- [ ] **F2 — 실제 SDK/모델:** `@cline/sdk`를 실제 import하며 설정된 provider로 실행했다. CLI subprocess나 UI mock으로 대체하지 않았다. 승인 거절/취소/실패가 실제 실행 결과와 일치한다.
- [ ] **F3 — R0:** 준비 단계 요약 호출과 후보 선택 LLM 호출이 0회다. 다섯 언어의 식별자 검색으로 해당 언어의 원문과 출처를 읽을 수 있다. Python 함수→helper→상수의 정적 참조도 제공되며 무관한 1,000개 sentinel과 전체 index는 모델 입력에 없다. 변경/삭제 뒤 잘못된 revision을 반환하지 않는다.
- [ ] **F4 — Runtime:** 임계값 이상 결과를 저장하고 실제 provider 입력·history·SSE에는 제한된 descriptor만 들어간다. 부분 재조회·삭제·TTL·세션 격리·재시작을 확인했다. 저장/hook 실패 때 원문 fallback이 없다.
- [ ] **F5 — Source:** 허용된 파일만 등록하고 실제 bounded I/O로 범위를 읽는다. 조회 도중 변경·오래된 cursor·경로 이탈을 감지한다. 등록 해제가 사용자 원본을 삭제하지 않는다.
- [ ] **F6 — PDF:** 실제 도구/Skill 등록을 확인했다. 텍스트 PDF가 Source Pointer로 연결되고 요청한 페이지의 원문과 정확한 페이지 출처만 반환한다. 스캔/손상/암호화 한계를 성공으로 숨기지 않는다.
- [ ] **F7 — 총 컨텍스트 예산:** 지원 모델의 최종 outbound payload 기준 tokenizer/framing 검증과 예산 차단을 통과했다. tool schema/history/output 예약을 포함하며 초과·계수 미지원은 명시적으로 차단한다.
- [ ] **F8 — UI 동작/설계 일치:** 모든 필수 화면의 정상/빈값/오류/만료/변경/거절/취소/재연결 시나리오가 통과한다. 이벤트 중복/역순 때문에 상태가 되돌아가거나 효과가 재실행되지 않는다.
- [ ] **F9 — 검증·측정:** 실제 자동 시험과 실 provider smoke가 통과했다. 동일 fixture/tokenizer의 원문 baseline 대비 총 입력 토큰·원문 bytes·요청 횟수를 기록했다. 요청별 최대 입력과 세션 누적 입력을 구분하고 실험 수치를 제품 성능으로 복사하지 않았다.
- [ ] **F10 — 유지보수:** 파일 분할·디렉토리·Python/TS 코딩컨벤션·타입·lint·build 검사와 실행/복구 안내가 완료됐다. 구현을 대신하는 TODO·production mock·차단 결함이 없다.
- [ ] **F11 — 역할 종료:** 27개 작업의 대표 완료 체크와 증거가 모두 존재하고 최종 `docs/release/ACCEPTANCE_REPORT.md`가 작성됐다. Git commit/push는 LLM이 수행하지 않았다.

필수 통합 데모는 다음과 같이 하나의 시나리오로 재현한다.

1. Python, C, C++, Java, JavaScript의 단일 언어 프로젝트와 다섯 언어가 섞인 프로젝트를 등록하고 R0 색인을 READY로 만든다. 각 언어의 식별자로 검색해 원문·출처를 확인한다. 혼합 프로젝트에는 Python 함수·다른 파일 helper·상수와 동명 및 무관 심볼을 포함한다.
2. 실제 식별자가 포함된 질문을 보내 관련 원문만 전달되고 파일/줄 출처가 보이는지 확인한다.
3. 안전한 fixture 명령의 실행을 UI에서 승인해 큰 로그를 만들고, Runtime Pointer의 필요한 줄만 다시 읽는다. 거절한 명령은 실행되지 않아야 한다.
4. 큰 외부 텍스트와 한글 다중 페이지 PDF를 명시적으로 등록한다. Source 부분 조회와 PDF 지정 페이지의 출처를 답변에서 확인한다.
5. 실행 도중 UI 연결을 끊었다가 복구하고 중복 run/도구 실행이 없는지 확인한다. 별도 실행에서는 취소를 확인한다.
6. 파일 변경, 포인터 만료/삭제, 저장 실패, 예산 초과를 주입해 오류를 명확히 표시하고 큰 원문 전송으로 후퇴하지 않는지 확인한다.
7. 기존 원본이 보존됐는지 확인하고 앱을 정상 종료한다. 검증 기록만 저장하며 Git commit/push는 팀원이 직접 한다.

실제 provider 검증에 필요한 계정·API 키는 팀원이 로컬 환경으로 제공해야 한다. 이것은 미배정 구현 업무가 아니라 실행 환경 입력이다. 키가 없는 경우 나머지 독립 작업은 진행할 수 있지만 실연동·최종 인수 체크는 미완료로 남긴다. 비밀값을 문서/프롬프트/Git에 붙여넣도록 요구하지 않는다.

## 7. 근거 자료와 설계 결정의 구분

로컬 자료와 공식 SDK 소스에서 확인한 사실을 바탕으로 작성했다. UI 프레임워크, FastAPI sidecar, 신규 API/URI, 디렉토리, 기본 용량 제한, 작업 분담은 **이번 구현을 위한 설계 결정**이며 기존 제품에 이미 구현돼 있다고 주장하지 않는다. 외부 API는 실제 작업 시점의 설치 버전으로 다시 검증한다.

### 7.1 저장소 내부 근거

- [기존 Python 코딩컨벤션](CODING_CONVENTIONS.md): 모든 Python 신규/수정 코드의 기준.
- [R0 전용 실험 코드](../experiments/symbol_raptor/experiment_r0.py): `CONFIG`의 R0 정의와 `prepare`의 요약 없는 원문 준비.
- [R0 원문·참조·TF-IDF 구현](../experiments/symbol_raptor/experiment.py): `source_nodes`, `closure`, `raw_items`, `words`, `Retriever`, `pack`. 같은 파일의 요약 생성 경로는 적용 대상이 아니다.
- [현재 색인·R0 비교 보고서](../Documents/test_results/03_현재색인_A와_파일간확장_B_재실험_비교보고서.md): 1.5절 R0 원리, 한국어/0점 검색 한계, 검색 준비/갱신과 제품 UI 미구현 구분.
- [Runtime 실험 도구](../../1st/runtime_pointer_test/runtime_pointer_bench/runtime_tools.py), [Runtime 동작 문서](../../1st/runtime_pointer_test/runtime_pointer_test.md): 저장/추출 원리와 message history 이전 교체 설계.
- [Source 실험 도구](../../1st/source_pointer_test/source_pointer_bench/source_tools.py), [Source 동작 문서](../../1st/source_pointer_test/source_pointer_test.md): 등록된 원본/범위 조회 원리와 기존 전체 읽기의 한계.

### 7.2 공식 Cline SDK 근거 — 2026-10-27 확인

- [SDK 개요](https://docs.cline.bot/sdk/overview), [ClineCore](https://docs.cline.bot/sdk/clinecore), [ClineCore API](https://docs.cline.bot/sdk/reference/cline-core): SDK의 언어/실행/세션 API. 패키지 요구와 source 버전은 [고정 ref package.json](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/sdk/package.json)을 확인했다.
- [Plugin hooks](https://docs.cline.bot/sdk/plugins), [Agent 타입](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/shared/src/agent.ts): `afterTool`/`beforeModel`, 반환 result 교체, 오류 정책. [로컬 도구 결과 처리 순서](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/agents/src/agent-runtime.ts#L2621)와 [provider 도구 경로](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/agents/src/agent-runtime.ts#L1955)를 구분했다.
- [모델 요청 준비 순서](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/agents/src/agent-runtime.ts#L1660): `beforeModel` 검사만으로 provider 최종 framing까지 검증됐다고 단정하지 않는다.
- [승인 처리](https://docs.cline.bot/sdk/guides/permission-handling), [실제 Core 예제](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/apps/examples/cline-core-cli-agent/src/index.ts), [Core 이벤트 타입](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/core/src/types/events.ts): 승인 capability, 명시적 tool policy, Core 이벤트 변환 근거.
- [Core 설정 타입](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/packages/core/src/types/config.ts#L184): checkpoint 비활성화 설정. [파일 hook 예제](https://github.com/cline/cline/blob/775d0398039977ca5447ed39c1a7f178df69aa87/sdk/examples/hooks/README.md)는 typed result 교체 hook과 구별한다.
