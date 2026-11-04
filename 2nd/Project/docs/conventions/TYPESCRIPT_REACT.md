# TypeScript·React 보완 코딩컨벤션

> 작성: 박준형 (작업 3.2) · 작성일: 2026-11-04 (Asia/Seoul) · 적용: `apps/**`, `contracts/**`, `scripts/**`, `tools/**`의 TypeScript/React
>
> Python은 [CODING_CONVENTIONS.md](../../CODING_CONVENTIONS.md)가 원본 규약이다. 이 문서는 그 규약을 TypeScript에 억지로 옮기지 않고, 로드맵 0.5의 요구를 TypeScript/React에 맞게 구체화한다. 규칙은 가능한 한 도구로 강제하며, 강제 수단을 각 절에 적는다.

## 1. 우선순위

1. 로드맵 0절(특히 0.3 보안·0.5 구조)과 [SDK_COMPATIBILITY.md](../architecture/SDK_COMPATIBILITY.md)의 실측 제약
2. 이 문서
3. 도구 기본값(ESLint `recommendedTypeChecked`, Prettier)

규칙과 다른 코드가 꼭 필요하면 해당 작업 증거(`docs/progress/tasks/<번호>.md`)에 이유를 쓰고 `scripts/check/structure-baseline.json`에 항목을 추가한다. 예외는 `KNOWN`으로 보고되어 `npm run check`를 `INCOMPLETE`로 남긴다. 3.7이 남은 예외를 판정한다.

## 2. 도구와 고정 버전

| 도구 | 버전 | 설정 파일 | 실행 |
| --- | --- | --- | --- |
| Node.js | 22 또는 24 LTS (`engines: ^22.12.0 \|\| ^24.0.0`, `.nvmrc` = 24) | `package.json` | — |
| TypeScript | 6.0.3 | `tsconfig.base.json` + 패키지별 `tsconfig.json` | `npm run check:types` |
| tsx | 4.23.15 | — | host·scripts 실행 |
| ESLint | 10.13.0 + typescript-eslint 8.71.2 (`recommendedTypeChecked`) | `eslint.config.js` | `npm run check:lint` |
| Prettier | 3.9.10 | `.prettierrc.json`, `.prettierignore` | `npm run check:format` |
| Ajv | 8.20.0 (+ ajv-formats 3.0.1) | `contracts/src/validator.ts` | 계약 검증 |
| json-schema-to-typescript | 16.0.0 | `contracts/scripts/generateTypes.ts` | `npm run generate:contracts` |

TypeScript 7.x는 typescript-eslint의 지원 범위(`<6.1`) 밖이라 쓰지 않는다. 버전 변경은 루트 `package.json`과 `package-lock.json`을 함께 바꾸고 `npm run check`와 `npm run probe:sdk`를 다시 실행한 증거를 남긴다.

## 3. 컴파일러 설정

모든 패키지는 `tsconfig.base.json`을 상속한다.

- `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, `noImplicitReturns`, `noFallthroughCasesInSwitch`, `useUnknownInCatchVariables`를 켠다.
- `module: ESNext`와 `moduleResolution: Bundler`를 쓴다. **`NodeNext`는 금지한다.** 3.1 C-01에서 확인했듯이 `@cline/sdk@0.2.0`의 `.d.ts`는 NodeNext에서 457개 모듈이 해석되지 않는다. 그러면 SDK 타입이 조용히 `any`가 되고 타입 검사가 사실상 꺼진다.
- `verbatimModuleSyntax`, `isolatedModules`: 타입만 가져올 때는 반드시 `import type`을 쓴다(ESLint `consistent-type-imports`).
- 상대 import에는 `.js` 확장자를 붙인다(`./router.js`). 실행은 tsx로 한다. 배포 번들 방식은 3.7이 정한다.

## 4. 이름과 파일

| 대상 | 형식 | 예 | 강제 |
| --- | --- | --- | --- |
| 변수·함수·메서드·매개변수 | `camelCase` | `loadHostConfig`, `requestId` | ESLint `naming-convention` |
| 모듈 수준 상수 | `UPPER_CASE` 또는 `camelCase` | `MAX_LOG_CHARS` | 같은 규칙 |
| 타입·인터페이스·클래스·enum·React 컴포넌트 | `PascalCase` | `RunSnapshot`, `ApprovalPanel` | 같은 규칙 |
| JSON 전송 필드 | `snake_case` | `schema_version`, `run_id` | 계약 스키마. 객체 리터럴·타입 속성은 이름 규칙 예외 |
| TS 모듈 파일 | `camelCase.ts` | `httpContextServiceClient.ts` | 리뷰 |
| React 컴포넌트 파일 | `PascalCase.tsx`, 컴포넌트 하나 | `RunTimeline.tsx` | 리뷰 |
| 테스트 | `tests/**/<대상>.test.ts(x)` | `tests/unit/router.test.ts` | `check:structure` (`src/` 안 테스트 금지) |

`tools/sdk-probe`는 3.1 검증 도구라 기존 `kebab-case.ts` 파일명을 유지한다. 제품 코드(`apps/`, `contracts/`, `scripts/`)에는 적용하지 않는다.

wire 필드(snake_case)를 UI 표시용 camelCase 모델로 바꾸는 일은 **`apps/ui/src/api/mappers` 한 곳**에서만 한다. host와 contracts는 wire 형식을 그대로 다룬다.

## 5. 타입 규칙

- 의미 없는 `any`를 금지한다(`no-explicit-any: error`). 모르는 값은 `unknown`으로 받고 검증한 뒤 좁힌다.
- **네트워크·프로세스 경계에서 받은 JSON은 반드시 계약 검증을 거친다.** `ContractValidator.parse<T>(SCHEMA_REFS.x, body)`를 쓰고, 손으로 DTO 타입을 다시 선언하지 않는다. 생성 타입은 `@securecode/contracts`에서 가져온다(`contracts/generated/ts/contracts.ts`, 수정 금지).
- 외부로 내보내는 함수는 반환 타입을 명시한다(`explicit-module-boundary-types`).
- `switch`는 판별 유니온 전체를 다룬다(`switch-exhaustiveness-check`).
- 타입 단언(`as`)은 검증 직후나 SDK 공개 타입에서 유도할 때만 쓴다. SDK가 export하지 않는 hook 타입은 `Parameters<NonNullable<AgentHooks["afterTool"]>>[0]`처럼 공개 타입에서 유도한다(3.1 3절).

## 6. 비동기와 오류

- 처리하지 않은 Promise를 금지한다(`no-floating-promises`, `no-misused-promises`). 의도적으로 기다리지 않을 때는 `void`를 붙이고 이유를 주석으로 쓴다. `node:test`의 `describe/it`만 예외로 등록했다.
- 오류는 삼키지 않는다. 경계마다 계약 `ErrorCode`를 가진 오류로 바꾼다(host: `ContextServiceError`, `RouteError`). 사용자에게 보이는 메시지에는 서버 경로·키·토큰·원문을 넣지 않는다.
- 취소와 시간 제한은 `AbortSignal`로 명시한다(`AbortSignal.timeout`, `AbortSignal.any`). SDK hook timeout을 기대하지 않는다(3.1 S-04).
- **fail-closed:** 포인터 저장·예산 계수가 실패하면 원문을 그대로 넘기지 않고 오류를 던진다(`ToolResultTransformer`, `ModelRequestGate` 포트 계약).
- `async`인데 `await`가 없는 함수는 허용한다(`require-await` off). Promise를 반환해야 하는 SDK·포트 인터페이스를 구현하기 때문이다.

## 7. 모듈 경계 (금지 의존성)

| 규칙 | 강제 |
| --- | --- |
| `@cline/*`는 `apps/host/src/cline/**`(어댑터)와 `tools/sdk-probe`에서만 import한다. routes·context-client·config·security·logging·contracts·scripts에서는 금지 | ESLint `no-restricted-imports` |
| UI(`apps/ui/**`)는 host `/api/v1`만 호출한다. `@cline/*`, `/internal/v1`, context-service 포트 사용 금지 | `check:structure` `ui-boundary` |
| 실험 코드(`../experiments`, `*_bench`)·`sys.path` 조작·RAPTOR·임베딩/벡터 DB 라이브러리 금지 | `check:structure` `forbidden-dependency` |
| 소스에서 commit/push를 실행하는 문자열이나 argv 금지 | `check:structure` `git-mutation` |
| 비밀값은 `VITE_` 접두사를 쓰지 않는다. `.env.example`의 키·토큰 값은 비운다 | `check:structure` `env-secret` |
| feature 간 순환 import 금지. 공용 코드는 `components/`·`hooks/`·`api/`로 올린다 | 리뷰(1.1에서 import 규칙 추가) |

## 8. 파일 분할과 길이

- production 파일 300줄, 테스트 500줄 이하(`check:structure` `max-lines`). 생성 코드·lockfile·fixture·문서는 제외한다.
- 함수 60줄과 React 컴포넌트 150줄을 분리 검토 기준으로 삼는다.
- `main`·`index`·`App`·`server` 조립 파일에는 연결만 둔다. 업무 로직은 route handler·service·model로 나눈다.
- 한 파일에 UI·네트워크·상태·SDK·저장·파서를 섞지 않는다. 길이 검사를 피하려고 줄을 압축하거나 `utils.ts` 하나에 모으지 않는다(Prettier가 120자로 줄을 다시 나눈다).

## 9. React (1.1부터 적용)

- 함수 컴포넌트와 hooks만 쓴다. hook 이름은 `useX`다.
- 화면 상태는 `features/<기능>/model`, 공통 구독은 `hooks/`에 둔다. 컴포넌트 안에서 `fetch`를 직접 호출하지 않고 `api/client`를 쓴다.
- 서버가 주지 않은 값(토큰 수, 성공 상태)을 화면에서 지어내지 않는다. `count_mode`가 `provider_estimate`면 "추정"으로 표시한다.
- 개발 환경은 Vite proxy로 host와 origin을 맞춘다. cookie는 HttpOnly·SameSite=Strict이며 JS에서 읽지 않는다.
- 접근성: 의미 있는 HTML 요소, 키보드 조작, 상태 변화 알림(2.1 UI-33)을 지킨다.

## 10. 주석

- export하는 모듈의 맨 위에 그 파일의 책임을 TSDoc 한 단락으로 쓴다. 복잡한 함수는 무엇·왜를 쓴다.
- Python식 "함수 이름/작성 날짜" 블록은 TypeScript에 쓰지 않는다. 날짜와 작성자는 Git과 작업 증거가 관리한다.

## 11. Python 검사 기준 (요약)

원본 규약은 [CODING_CONVENTIONS.md](../../CODING_CONVENTIONS.md)다. 도구 설정은 `services/context-service/pyproject.toml`에 있다.

| 검사 | 기준 | 명령(서비스 폴더) |
| --- | --- | --- |
| Ruff lint | `E,W,F,I,N,B,UP,SIM,RUF,T20`. 코드 100자. docstring·주석은 한글 폭(2칸) 때문에 120자 | `uv run ruff check .` |
| Ruff format | 큰따옴표, 공백 4칸 | `uv run ruff format --check .` |
| mypy | `strict = true`, `src/securecode_context` | `uv run mypy` |
| pytest | `tests/{unit,contract,integration}`, `--strict-markers`, `integration` marker | `uv run pytest` |
| docstring 필드 | 함수: 함수 이름·기능·인자·반환값·작성 날짜. 클래스: 클래스 이름·기능·작성 날짜 | `uv run python ../../scripts/check/python_docstrings.py` |

## 12. 검사 명령과 종료 코드

| 명령 | 내용 |
| --- | --- |
| `npm run check` | ESLint, Prettier, 모든 tsconfig, 구조 검사, 생성 타입 최신성, Ruff/mypy/docstring, host·서비스 unit 시험 |
| `npm run check:lint` / `check:format` / `check:types` / `check:structure` | 개별 검사 |

종료 코드: `0` 모두 PASS, `1` FAIL, `3` INCOMPLETE(`KNOWN` 예외·`PENDING` 미구현·`SKIPPED` 남음). 미구현 검사를 성공으로 보고하지 않는다. 각 담당은 자기 범위의 `PENDING` 항목을 `scripts/lib/pendingSuites.ts`에서 실제 검사로 바꿔야 한다.
