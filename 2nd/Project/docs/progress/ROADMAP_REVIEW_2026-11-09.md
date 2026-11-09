# 완료 표시 작업 재검토 — 2026-11-09

- 범위: 로드맵 대표 완료 체크 19개와 체크된 하위 조건, 작업별 증거, 실제 소스 및 테스트.
- 기준: Asia/Seoul, 현재 checkout. 기존 작업 폴더는 검토 시작 시 깨끗했다. commit/push는 수행하지 않았다.
- 판정: **12개 유지, 7개 재개방**. 4.10은 원래 대표 체크가 비어 있었으나 하위 조건과 COMPLETED 기록이 잘못되어 함께 정정했다.
- 이 보고서가 이전 작업 기록의 완료 주장과 충돌하면 이 재검토 판정을 적용한다. 테스트 통과는 그 테스트의 범위를 의미하며 제품 전체 완료를 뜻하지 않는다.

## 작업별 판정

| 작업 | 판정 | 근거 및 남은 조건 |
| --- | --- | --- |
| 1.1·1.2·1.3 | 유지 | fixture UI 및 행동 구현. 승인 표시·지연 응답·실제 Vite proxy 결함 수정 후 렌더링/행동/프록시 26개 통과. 실 API 연동은 1.4 이후 범위다. |
| 2.1·2.2 | 유지 | 화면/행동/인수 설계와 계약 fixture 대응 확인. 최종 화면 인수는 2.3이다. |
| 3.1 | 유지 | 설치 SDK 0.2.0으로 오프라인 probe 71개 통과. 실제 SDK와 scripted provider 사용이며 외부 provider 검증은 아니다. |
| 3.2 | 유지 | 고정 의존성, 생성 계약, 오류/인증/프로세스 골격 확인. 공통 검사에 빠진 UI 테스트/빌드를 연결했다. 이후 추가된 Python 모듈의 정적 검사 실패를 성공으로 숨기지 않는다. |
| 3.3·3.4 | 유지 | 다섯 언어 R0 시험 58개 통과, Windows 전용 1개 제외. 응답 상한 및 revision/hash 재검증 결함 수정. |
| 3.5 | 유지 | 실제 SDK 호스트 승인·취소·SSE·프로세스 시험 통과. 기본 파일 읽기의 전체 파일 로딩 제거 및 Git 명령 검사 보완. 운영은 미완성 gate 때문에 세션을 차단한다. |
| 4.1·4.2 | 유지 | 설계/계약 작업. 4.1의 appendContext, 최종 예산 검사 위치, quota와 실패 정책 설명을 바로잡았다. 계약 시험 TypeScript 232개·Python 200개 통과. |
| 4.3 | INCOMPLETE | 디스크 기본 수명주기와 10,001개 발급 시험은 통과. 다중 store의 quota 원자성, DB 실패 시 orphan 정리, checksum 확인, token cap, cursor scope와 selector 계약은 미완료. |
| 4.4 | BLOCKED | 결과 교체 hook/실제 SDK fixture 시험은 통과. 호스트의 잘못된 Runtime API·provider URL 사용을 수정하고 실제 Python 저장/읽기를 검증. 4.3 선행과 streaming executor 인수는 남음. |
| 4.5 | INCOMPLETE | stat/unregister의 호출자 workspace 권한, 외부 파일 허용 목록 격리, revision 갱신/resolve/provenance 계약 부족. 기존 `collected 0 items (PASSED)`는 유효한 증거가 아니다. |
| 4.6 | BLOCKED | 경로·변경 감지·긴 줄·JSON 결함은 수정. stat의 전체 hash 읽기 및 앞부분 line scan이 남으며 seek-index 연결, token/cursor/section/byte selector는 미완료. |
| 4.7 | INCOMPLETE | 안전 마진 부호 수정. 모델/tokenizer/framing, 범위 정규화, 0 예산/무결과/권한 등의 계약 fixture 보완 필요. |
| 4.8 | BLOCKED | 문자 길이 추정 구현은 `ModelRequestGate.check(request, signal)` 포트 및 최종 outbound 계수가 아님. strict 모드의 가짜 지원 허용은 차단. bounded resolver와 범위 중복 제거도 미완료. |
| 4.9 | BLOCKED | 일반 PDF parser 의존성 없음. 정규식 분할은 page tree/압축 stream/한글 폰트를 해석하지 못함. job/취소/버전 캐시/출력 상한/SDK 등록 export 필요. |
| 4.10 | BLOCKED | 3.6·4.8·4.9 선행 미충족. Python 모듈 연결 시험만으로 실제 SDK·provider 통합을 완료했다고 기록한 주장 철회. |

## 수정한 결함과 회귀 검증

1. **승인·UI 상태**: 180자 이후 승인 본문이 가려지던 문제를 고쳤다. 확인창을 검토한 approval ID/digest에 고정하고, 복구 중 중복 승인과 늦은 snapshot의 최신 run 덮어쓰기·영구 대기를 차단했다. 사이드바 링크 대상 ID와 실제 Vite Host rewrite도 수정했다.
2. **R0 상한·변경 감지**: 64 KiB 제한에 JSON envelope/cursor를 포함했다. 검색/묶음 계수 중 재색인되거나 원본 파일이 변경되면 응답 직전 거부한다. 신규 4개 시험은 수정 전 실패, 수정 후 통과했다.
3. **호스트 읽기**: `read_file`이 파일 전체를 읽은 뒤 자르던 동작을 seek + 제한된 buffer로 교체했다. UTF-8 경계, 유효하지 않은 범위 및 일반 파일 여부를 검사한다. sparse 1 GiB 파일의 작은 범위 읽기 회귀가 통과했다.
4. **Runtime 경로·부분 읽기**: scope의 경로 이탈 입력을 차단했다. 전체 blob 로딩을 없애고 UTF-8 바이트 커서와 읽기·목록·검색 상한을 확인한다. 내부 API와 레거시 API를 구별하고 provider URL과 context-service URL을 분리했다. 내부 API의 조각 크기/전체 크기와 문자열 커서를 호스트에서 정확히 해석한다.
5. **Source 읽기**: 등록 뒤 symlink 교체·조회 도중 변경을 감지한다. 거대한 한 줄과 검색에 상한을 적용하고 JSON은 등록 포인터를 통해서만 읽으며 입력 8 MiB/출력 상한을 검사한다. 마지막 개행 없는 줄 인덱스도 보존한다.
6. **예산·설계**: 모델 이름에 gpt/claude가 있다는 이유만으로 strict tokenizer를 허용하지 않는다. 검증된 계수가 없는 strict 요청은 `TOKENIZER_UNAVAILABLE`이다. 안전 마진을 오히려 예산에 더하던 문서 공식도 수정했다.
7. **명령 검사**: 따옴표/이스케이프/환경변수 prefix/실행 wrapper/명시적 alias override로 Git 금지 명령이 빠져나가던 경우를 보완했다. 회귀 시험은 명령 문자열만 검사하며 해당 명령을 실행하지 않는다. 임의 스크립트·기존 repository alias·동적 shell expansion까지 분석하는 격리 장치는 아니다.
8. **검사 연결**: 루트 check/unit에 실제 UI 시험을, build에 실제 UI 빌드를 넣고 오래된 UI PENDING 표시를 제거했다. dev의 UI 동시 실행과 배포 패키징은 아직 후속 작업이다.

## 실행 결과

검사 준비로 `npm ci --ignore-scripts --no-audit --no-fund`를 실행했다. lockfile은 변경하지 않았다. 최초 일반 실행은 tsx의 로컬 IPC 권한으로 시작되지 않아 허용된 로컬 실행으로 재시도했다. Python 개별 검사는 기존 `.venv/bin/python`으로 실행했다.

| 명령/검사 | 결과 |
| --- | --- |
| `npm run probe:sdk -- --no-evidence` | 71/71 PASS, 저장된 probe 증거를 덮어쓰지 않음, repository refs/stash 변경 없음 |
| `npm run test:contracts` | 생성 타입 최신성 PASS, TypeScript 232 PASS, Python 200 PASS |
| UI tests/build/typecheck/ESLint | 26 PASS, 실제 Vite proxy 포함, production build PASS |
| R0 표적 시험 | 58 PASS, Windows 전용 junction 1 SKIP; Ruff/mypy PASS |
| Runtime/Source/Selector/PDF 표적 회귀 | Python 36 PASS. 기존 PDF 합성 fixture 통과는 실제 PDF 기능 보장이 아님 |
| strict gate 회귀 | TypeScript 3 PASS |
| `npm run check` | 호스트 72·UI 26·Python 145 PASS, Windows 전용 1 SKIP. ESLint/Prettier/TypeScript/구조/생성 타입 PASS. Python 정적 검사 실패로 전체 FAIL |
| `npm run test:integration` | 서비스 프로세스 1, SDK 호스트 11, launcher 2 및 실제 host/service 체인 PASS. Runtime 저장/한글 9바이트 읽기도 PASS. 후속 통합 4개 PENDING으로 exit 3 |
| `npm run build` | host 타입·UI·Python wheel 생성 PASS. 3.7 배포 패키징 PENDING으로 exit 3 |

전체 Python 정적 검사 잔여: Ruff 58건, 포맷 10파일, mypy 7건/4파일, docstring 12파일. 주로 재개방한 context/pdf/source 모델 및 기존 관련 시험이다. 이 오류는 자동화된 검사가 드러내며 baseline 예외나 성공으로 바꾸지 않았다. 이번에 변경한 Python 동작 파일은 별도 Ruff/mypy 검사로 확인했다.

## 남은 작업의 재개 순서

- 4.3 저장소의 실패·동시성·계약을 닫고 4.4 streaming 저장/잘림 정책을 실제 executor까지 검증한다.
- 4.5의 scope/등록 갱신 계약을 완성한 다음 4.6의 전체 파일 재읽기 없는 범위 해석·계수·cursor를 완성한다.
- 4.7의 명세/fixture를 보완한 뒤 4.8에서 검증된 tokenizer 및 최종 요청 포트를 연결한다. 동점 후보를 입력 순서와 무관하게 정렬하고, 서로 다른 범위를 URI만으로 중복 제거하지 않아야 한다.
- 4.9는 실제 PDF 라이브러리와 유효한 다중 페이지/한글/압축 PDF fixture부터 구현한다. 현재 `/Type /Pages`도 페이지로 세어 한 페이지를 두 페이지로 반환하고, 잘못된 bytes를 빈 결과로 처리한 뒤 도구가 COMPLETED를 반환할 수 있다.
- 이후 3.6·4.10에서 SDK/service/UI/provider 전체 연결을 인수한다. 외부 provider 호출, Windows 실행 및 브라우저 전체 사용자 흐름 E2E는 이번 검토에서 실행하지 않았다.

운영 `main.ts`의 예산 gate는 계속 null이고 세션은 `PROTECTION_UNAVAILABLE`로 거부된다. 미검증 포인터/PDF/예산 구현을 운영 준비 완료로 사용하면 안 된다.
