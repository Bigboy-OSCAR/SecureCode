# LocalDesk 최종 앱 도구 검증 — 2026-11-11–12

**상태: 검증 완료. 실제 앱에서 13개 도구 각각의 성공을 확인했다. 발견한 6개 결함을 수정하고 해당 경로를 재검증했으며, 최종 전체 검사·앱 빌드·서명 검증을 통과했다. 최종 앱을 재실행한 뒤 기존 Runtime 결과의 부분 읽기와 화면의 검증 출처 표시까지 확인했다.**

## 대상과 판정 기준

- 앱: `dist/LocalDesk.app`, 실제 macOS 창에서 질문 입력·전송·승인 조작.
- 모델: 로컬 `qwen2.5-7b-instruct`.
- 시험 프로젝트: `/private/tmp/LocalDesk-Tools-20261111/project`.
- Workspace: `ws_4c7371146aee1a4e1f277ec3` (`전체 도구 검증`).
- 앱 데이터: `~/Library/Application Support/LocalDesk`.
- 앱은 이 Mac의 checkout에 고정된 native shell이다. `local-config.json`의 projectRoot에서 host/context-service를 시작하고 `apps/ui/dist`를 제공한다.
- 시험은 23:26 생성본에서 시작했다. Source 범위 수정은 23:43 빌드, 목록 갱신·반복 보호 수정은 11/12 00:06 빌드에서 재검증했다.
- 여섯 수정이 모두 포함된 최종 앱의 native executable은 2026-11-12 00:30:14 KST 생성본이다. 전체 `npm run check`, `npm run build:app`, `codesign --verify --deep --strict`가 통과했다. 이 앱을 재실행해 기존 Runtime 대화·포인터의 범위 읽기와 화면의 출처 표시를 확인했다.
- 수정 커밋: `9a87cf19`(Source 범위), `38a09f51`(자료 목록), `cb2c1ee6`(stale 반복 보호), `4f0f9bc8`(직접 코드 읽기 출처), `e72bd6f9`(Runtime 직접 읽기 출처), `bf79ea20`(Runtime SQLite 동시 접근). 여섯 커밋 모두 GitHub에 push했다.

성공 판정은 답변 문장만으로 내리지 않는다. 실제 앱의 `host/runs` 기록에서 도구 완료를 확인하고, 해당 시험 대화의 SDK `tool_use`/`tool_result`와 결과 범위·식별 문자열을 대조한다. 모델이 잘못 입력한 인자와 재시도는 삭제하지 않는다. 격리된 자동 시험은 별도 증거이며 실제 앱 시험을 대신하지 않는다.

## 실제 native 앱에서 확인한 항목

아래는 13개 도구 각각의 최초 성공 증거다. 이후 수정·재시작 회귀는 다음 절에 기록했다. `PASS`는 해당 도구의 명시된 경로가 실제 실행됐다는 뜻이며 모든 가능한 입력 조합에 대한 보장은 아니다.

| 도구 | 현재 판정 | 실제 실행 증거 |
| --- | --- | --- |
| `list_files` | PASS | `run_9005f5a9d5e80eb716ef9b61`: 프로젝트 목록 반환, SDK 오류 없음 |
| `search_file` | PASS | 같은 run: `notes.txt` 대상 문자열 검색 1건 |
| `read_file` | PASS | 같은 run: `notes.txt` byte 34–57, 23 bytes, 대상 문자열 포함. Source 출처 등록 |
| `code_search` | PASS | `run_feb6d88862037ac1569cf44e`: 코드 후보 3개 반환 |
| `code_read` | PASS | `run_849bb376ea047888946e2756`: 실제 후보 코드 읽기 완료, 코드 출처 1개 |
| `run_command` | PASS | `run_b493dc104707b8fef3502885`: 앱에서 승인한 `node gen.js`, 출력 1,168,859 bytes가 Runtime Pointer로 저장됨 |
| `runtime_search` | PASS | 같은 run: 생성된 Runtime Pointer에서 목표 줄 검색 1건, SDK 오류 없음 |
| `runtime_read` | PASS | `run_1bfd7e8a8ede3a06a702e249`: 13,579번째 줄만 읽음, byte 789,996–790,019의 23 bytes, `total=42` 포함 |
| `write_file` | PASS | `run_ecd8a756637fce2b723a5625`: 승인 후 `approved.txt` 작성, 입력·실제 파일 모두 13 bytes, 후속 `read_file` 성공 |
| `pdf_parse` | PASS | `run_17649330e23935ed71b9d654`: 등록된 PDF로 파싱, ready·3페이지 반환 |
| `pdf_status` | PASS | 같은 run: 실제 parse job 조회, ready·3페이지 반환 |
| `pdf_search` | PASS | `run_79a225cc4bb62d9ecee097db`: 2쪽 대상 문자열 검색 1건, 다른 페이지 sentinel 없음 |
| `pdf_read_pages` | PASS | `run_93f9607a754d465712e1a17b`: 2쪽만 읽음, 52 bytes, PDF 2쪽 출처 등록. 1·3쪽 sentinel 없음 |

R0 인덱스 자동 컨텍스트는 `run_367c088d7197a58b2357d0da`에 `billing.py` 함수와 `Invoice.java`의 위치가 등록된 것으로 확인했다. 이후 명시적 `code_search`와 `code_read`도 각각 실행했다. 인덱스는 revision 1→2→3으로 갱신했고, 재시작 후 revision 3의 실제 코드와 출처를 다시 확인했다.

### 자료·컨텍스트 공개 UI 경로

모델 도구 호출과 별도로 실제 앱의 자료·컨텍스트 패널에서 확인했다.

- `formatTotal` 검색: `format.js` 1–1줄, score 0.636, 정확 계수 14 tokens.
- 선택 원문 묶음 읽기: revision 2의 실제 `toFixed(2)` 코드 반환.
- 질문 컨텍스트 미리보기: 계획 digest 생성, 선택 자료 22 / 가용 25,539 tokens(제공자 추정), R0 선택 예산 추정 14 tokens, 실제 삽입 22 tokens와 `format.js` 1–1줄·revision 2 표시.
- Source JSON 범위 읽기(11/12 00:00): `config.json` 등록 후 JSON 경로 `/limits/retries` 선택. 요청 범위 `json_path`, revision 1, 정확 계수 1 token과 본문 `3`만 표시.

이 수치는 해당 미리보기 1회의 관찰값이다. 모델의 실제 도구 호출 결과와 혼합해 계산하지 않는다.

## 발견한 결함과 수정 후 실제 앱 확인

`read_file`에 `end_line`만 전달하면 기존 구현은 selector를 생략해 파일 전체를 읽었다. `end_line`만 있을 때 시작 줄을 1로 설정하도록 수정했다. 그 외 범위 읽기와 역순 범위 거부는 유지했다.

- 수정 파일: `apps/host/src/cline/tools/sourceTools.ts`.
- 회귀 시험: `apps/host/tests/integration/sourceTools.test.ts`.
- 수정 전 실제 context-service 연동 시험: 2개 중 1개 실패.
- 수정 후 같은 시험: 2/2 통과.
- 재빌드·재시작된 앱의 `run_e9e63d3fe8a9d8682be8ba38`: 실제 입력 `{ path: "notes.txt", end_line: 1 }`, 읽은 범위 byte 0–33, 본문 33 bytes, 2번째 줄 대상 문자열 미포함, Source 출처 동일 범위 등록. SDK 오류 없음.

모델 입력 실수도 별도로 보존했다.

- 최초 `code_read`에서 실제 candidate ID의 `...b85...`를 `...b885...`로 잘못 복사해 `NOT_FOUND`를 받았다. 모델이 받은 context ID와 tool input을 직접 비교해 확인했다. 올바른 후보 검색·읽기는 후속 run에서 성공했다.
- 최초 `read_file`에서 존재하지 않는 cursor를 만들어 `INVALID_POINTER`를 받았다. cursor 없는 범위 읽기는 성공했다.
- Runtime 검색 뒤 모델이 부분 읽기를 실행하지 않고 서술한 경우가 있었다. 후속 질문으로 실제 `runtime_read`를 호출해 결과를 확인했다. 개별 도구 성공을 여러 도구를 한 번의 질문으로 항상 정확하게 수행한다는 의미로 해석하지 않는다.
- 최종 앱에서도 `run_8d0e2383c9d7ce21249b89cd`의 Runtime 읽기 두 번과 `run_e458e3d3b84de15515502541`의 한 번은 모델이 요청하지 않은 cursor를 추가해 `INVALID_POINTER`로 실패했다. 모델은 과거 결과를 답변에 재서술했지만 현재 질문의 출처는 비어 있었다. 이를 성공으로 세지 않았으며, cursor 없이 정확한 byte 범위를 지정한 후속 실제 호출만 성공 증거로 사용했다.

Runtime 대량 출력은 SDK에 898 bytes의 포인터 설명으로 전달됐고, 검색 결과는 122 bytes, 정확한 한 줄 읽기 결과는 142 bytes였다. 최종 11/12 00:33:26 KST 수집 기준 13/13 도구에 실제 성공 기록이 있고 진행 중인 run은 0개였다. 시험 대화의 도구 결과·삽입 context·assistant text에서 숫자가 붙은 대량 로그 sentinel과 무관한 소스 sentinel은 각각 0건이었다.

파일 작성은 승인 대기 중 파일이 없었고, 승인 후 `TOOL-WRITE-OK` 13 bytes가 생성된 것을 확인했다. 모델이 줄바꿈을 생략했으므로 사용자의 원래 문구 형식까지 정확히 따랐다고 주장하지 않는다. 실제 도구 입력과 디스크 내용의 일치를 확인한 결과다.

## 승인·거절·취소 경계

| 항목 | 실제 앱 증거 | 현재 판정 |
| --- | --- | --- |
| 파일 작성 거절 | `run_c2ef8387ca95b855fd997972`: approval/tool 모두 rejected, `rejected-write.txt` 미생성 | PASS |
| 명령 실행 거절 | `run_7710fca699c2285a85af83d7`: `node rejected-command.js` approval/tool 모두 rejected, `rejected-command.txt` 미생성 | PASS |
| 실행 중 취소 | `run_6583af1b278aff685cf0096d`: 승인된 `node slow.js`의 결과가 `command aborted`, run terminal CANCELLED. 프로세스 조회도 종료 확인. 후속 run의 파일 읽기 성공 | PASS |
| Runtime 세션 격리 | `run_a9e8fd8373c245f99abd543f`: 다른 대화의 Runtime Pointer는 FORBIDDEN. 같은 run의 `approved.txt` 읽기는 정상 완료 | PASS |

거절 도구가 SDK의 `is_error: true`로 기록되는 것은 의도된 제어 결과다. 실제 서비스 결함이나 모델의 잘못된 인자와 구분한다.

Source 원문을 변경한 뒤 `run_28d978b69f03de0e9dbae963`에서 새 `v=2` 포인터·revision 2·새 내용 `amount=91`을 확인했다. R0 원본 코드 변경 후 이전 revision 읽기는 실제 `SOURCE_CHANGED`로 거부됐다.

앱에서 R0를 revision 2로 갱신했다(발견 13·색인 8·지원하지 않는 형식 5·실패 0). `run_e4ba5700d3011c3e19506250`은 `code_search`/`code_read` 모두 완료됐고, 새 `billing.py`의 `+ 5` 내용과 1–4줄·revision 2·새 hash 출처를 확인했다. 모델 답변은 중국어로 작성됐고 본문 설명의 줄 번호는 정확하지 않았다. 권위 있는 읽기 범위는 도구 결과와 출처의 1–4줄이며, 도구 정상 동작을 답변 언어·설명 정확성 보장으로 해석하지 않는다.

### 추가 발견과 최종 빌드 회귀

- **자료 목록 갱신 결함 — 수정·실앱 확인:** 앱 backend에는 `notes.txt` revision 2와 `approved.txt`가 존재하지만, 자료·컨텍스트 패널을 다시 열었을 때 기존 revision 1 목록이 재사용돼 새 상태가 보이지 않았다. 다시 열 때 목록을 갱신하고 새 revision의 읽기 결과만 무효화하도록 수정했다. 페이지 밖 선택 유지와 늦은 목록 응답의 등록 결과 덮어쓰기도 방지했다. 00:06 빌드 앱에서 `run_1ae749d9aa919a73ba87af35`가 외부 변경된 `notes.txt` revision 3·byte 34–58을 읽었고, 패널 재오픈 시 113 bytes·revision 3·`amount=104`와 `approved.txt`를 표시했다.
- **오류 뒤 모델 반복 — 수정·실앱 확인:** R0 stale 읽기는 원문을 반환하지 않고 올바르게 거부했지만, 모델이 `code_search`/`code_read`를 12회 반복해 수동 취소가 필요했다. 한 질문에서 같은 candidate/revision의 실제 `SOURCE_CHANGED`가 두 번 발생하면 멈추고 인덱스 갱신 안내를 표시하도록 수정했다. 최종 빌드의 `run_00fe658b4a705d5a6d3100d5`에서 동일 후보·revision 2 읽기가 정확히 두 번 실패한 뒤 자동 종료됐고, terminal SOURCE_CHANGED 및 접힌 작업 기록 바깥의 ‘인덱스 갱신이 필요합니다’ 안내를 확인했다. 첫 실패의 직접 파일 읽기 회복, 다른 후보·새 revision, 실제 성공한 재시도는 허용한다. 안내 UI는 SOURCE_CHANGED 실패에만 표시한다. 일반적인 모든 모델 반복을 막는 장치는 아니며, stale 보호 성공을 모델의 오류 복구 성공으로 확대해서 판정하지 않는다.
- **재시작·직접 코드 읽기의 출처 누락 — 수정·실앱 확인:** 자동 중단 후 같은 대화에서 revision 3을 읽은 `run_b83fe7dee2a3771bb76e43a3`은 `code_read` 완료와 새 `+ 7` 코드를 확인했지만 출처 배열은 비어 있었다. Host의 이전 `code_search` 메모리 캐시에만 의존해 출처를 만들기 때문이다. Service가 실제 반환한 각 fragment에 검증된 위치·이름·줄 범위·해시를 포함하고, host가 이를 직접 인용하도록 수정했다. 누락된 참조·빈 결과를 인용하지 않으며 이전 검색의 오래된 hash를 사용하지 않는다. 00:15 최종 빌드 재실행 후 `run_109d2f4e38c0ea4cf227c0be`은 `code_search` 없이 `code_read` 한 번만 성공했다. 저장된 출처와 실제 앱 화면 모두 `billing.py:1-4 · compute_invoice_total · revision 3 · sha256 dd74d0e96137…`를 표시했다.
- **Runtime 직접 읽기의 출처 누락 — 수정·실앱 확인:** `runtime_read`는 실제 저장 범위와 provenance를 반환하지만 도구와 공통 hook 어디에서도 answer citation을 연결하지 않았다. 실행 결과 출처를 제공한다는 요구와 계약에 비춰 의도된 제외가 아닌 연결 누락으로 판정했다. 성공한 `run_1bfd7e8a8ede3a06a702e249`·`run_95e19108a436f2e58447286a`의 빈 citations는 이 결함의 증거다. 성공적으로 반환된 Runtime selection만 현재 질문의 출처로 연결하도록 도구 옵션 전달을 수정했다. 실제 서비스·SDK 회귀 6/6이 통과했다. 최종 00:30 빌드 재실행 후 `run_d504fc6b458067ceaf7809e1`은 기존 포인터를 한 번 읽어 23 bytes의 `RUNTIME-TARGET total=42`를 반환했다. 실제 앱 화면에서 포인터·revision 1·byte 789,996–790,019를 확인했고, 저장된 출처의 sha256은 `b13ceed4dcd8355bfc2c2788f8141f06b89b30aabf82b25718e5afb62462df31`로 대조했다. SDK 결과는 142 bytes이며, 실패한 읽기에는 출처를 만들지 않는다.
- **Runtime 동시 저장 결함 — 수정·반복 검증 완료:** 전체 검사에서 `test_concurrent_puts_in_one_store`가 실패했다. 같은 시험을 100회 반복해 92회 성공·8회 실패를 재현했다(`PointerNotFound` 6회, expiry `TypeError` 2회). 별도의 8개 세션 동시 조회·목록 반복 시험도 수정 전 10/10 실패했고, 새 정식 회귀 시험에서도 재현했다. 같은 SQLite connection에서 `load`/목록 조회가 잠금 없이 쓰기 transaction과 겹친 것이 원인이다. `load`, `list_pointers`, `close`를 기존 RLock으로 보호하도록 최소 수정했다. 수정 후 동시 저장 100/100, 동시 읽기 100/100, 관련 서비스 시험 83/83 및 ruff·mypy가 통과했다. 최종 전체 검사와 앱 빌드도 통과했고, 해당 앱에서 기존 Runtime 결과를 다시 읽었다. 수정 전후 로그는 자동 시험 표에 기록했다.

### 재시작 후 보존 확인

- 00:06 빌드 재실행 후 원래 Runtime 대화 `ses_8d5ad9d76c539531b350ebb2`에서 `run_95e19108a436f2e58447286a`의 실제 `runtime_read`가 성공했다. 재시작 전 만든 동일 포인터·13,579번째 줄·23 bytes·`total=42`를 확인했다. 앞선 한 번의 질문은 모델이 실제 도구를 호출하지 않았으므로 성공 횟수에 포함하지 않는다.
- 원래 PDF 대화의 `run_032f89a0af0b57d7e1353cf5`에서 저장된 동일 PDF pointer의 2쪽을 다시 읽었다. 52 bytes와 PDF 2쪽 출처를 확인했다.
- Source는 기존 revision 2를 복구한 뒤 revision 3 읽기와 패널 갱신을 확인했다. R0는 revision 3으로 갱신한 뒤 00:15 최종 빌드의 재시작에서 같은 대화를 복구하고, 직접 코드 읽기·최신 hash·출처 표시를 확인했다.
- 여섯 수정이 포함된 00:30 최종 빌드에서도 원래 Runtime 대화와 `1280562c-85c3-49ba-88de-97476a175598?v=1` 포인터를 복구했다. `run_d504fc6b458067ceaf7809e1`의 실제 부분 읽기와 해당 범위의 출처를 기록·접근성 트리·화면으로 확인했다. 이 마지막 시험으로 다른 도구를 다시 실행했다고 주장하지 않으며, 위 도구별 실행과 수정별 회귀 증거를 함께 사용한다.

## 격리된 자동 시험 — native 앱 시험과 구분

| 범위 | 관찰 결과 | 증거 |
| --- | --- | --- |
| Host 도구·포인터 연동 묶음 | 23/23 통과 | `/tmp/localdesk-all-tools-contract-audit.log` |
| Python Source/Runtime/R0/PDF 서비스 묶음 | 179 통과, 1 건너뜀 | `/tmp/localdesk-pointer-r0-service-audit.log` |
| Source `end_line` 회귀 | 수정 전 실패 재현, 수정 후 2/2 | `/tmp/localdesk-source-tool-before.log`, `/tmp/localdesk-source-tool-after.log` |
| 자료 목록 UI 회귀 + 기존 전환·사용 흐름 | 7/7 통과(모의 provider 브라우저 시험) | `/tmp/localdesk-pointer-refresh-final.log` |
| 신규 stale 읽기 SDK 회귀 | `staleCodeReadSdk.test.ts` 4/4 | 실제 SDK·제어된 provider/context 응답, 도구 stdout 관찰 |
| 기존 SDK 실행 회귀 | `sdkRuns.test.ts` 6/6 | 같은 회귀 실행의 도구 stdout 관찰 |
| 종료 상태 변환 | `turnOutcome.test.ts` 3/3 | 도구 stdout 관찰 |
| stale 안내 UI | `toolActivityFailure.test.tsx` 1/1 | `apps/ui` cwd에서 실행, 도구 stdout 관찰 |
| 직접 코드 읽기 출처 SDK + stale SDK 회귀 | 신규 출처 3개 + 기존 stale 4개, 7/7 | `/tmp/localdesk-code-citations-sdk.log` |
| 코드 위치·hash·revision Python 회귀 | 28/28 | `/tmp/localdesk-code-citations-python.log` |
| 변경 계약 회귀 | 246/246 | `/tmp/localdesk-code-citations-contracts.log` |
| Runtime 직접 읽기 출처·기존 포인터 SDK 회귀 | 실제 context-service·SDK 6/6 | `/tmp/localdesk-runtime-citations-sdk.log` |
| Runtime 동시 저장·조회 결함 재현 | 저장 100회 중 8회 실패, 별도 조회 10/10 실패, 새 정식 회귀 실패 | `/tmp/localdesk-runtime-race-before.log`, `/tmp/localdesk-runtime-reader-test-before.log` |
| Runtime 동시 접근 수정 후 반복 회귀 | 저장 100/100, 조회 100/100, 관련 서비스 83/83, ruff·mypy PASS | `/tmp/localdesk-runtime-race-after.log`, `/tmp/localdesk-runtime-race-service-after.log` |
| 네 번째 수정 반영 정적 검사·단위 시험 | `npm run check` PASS | `/tmp/localdesk-tools-release-check.log` |
| 네 번째 수정 반영 앱 빌드·서명 | `npm run build:app` PASS, codesign strict 검증 exit 0 | `/tmp/localdesk-tools-release-build.log`, 서명 검증 도구 출력 |
| 여섯 수정 반영 최종 전체 검사 | `npm run check` PASS. 포함된 Python 묶음 257 통과·1 건너뜀·1 선택 제외 | `/tmp/localdesk-tools-final-check.log` |
| 여섯 수정 반영 최종 앱 빌드·서명 | `npm run build:app` PASS, codesign strict 검증 exit 0 | `/tmp/localdesk-tools-final-build.log`, 서명 검증 도구 출력 |

건너뛴 1건은 `test_windows_junction_escape_is_rejected`이며 NTFS junction이 없는 macOS에서 Windows 전용 시험을 제외한 것이다. 성공으로 계산하지 않는다. 상세 시험 범위는 시험 파일·로그와 대조했다. 기존 `npm run test:live`는 임시 dataDir의 별도 host를 띄우므로 이번 최종 앱의 직접 실행 증거로 사용하지 않았다.

Host 묶음은 `integratedContextSdk`, `runtimePointerSdk`, `runtimePointerFailures`, `pointerLifecycleSdk`, `pdfTools`, `sdkSafety` integration과 `providerToolSchema`, `runCitations` unit을 실행했다. Python은 R0 8개·Source 6개·Runtime 5개 unit 파일, Pointer 계약 4개, Symbol/Runtime/PDF integration 5개 파일이며 JUnit XML의 testcase에 개별 결과가 남아 있다.

자료 목록 UI 묶음은 `pointerCatalogRefresh.e2e.ts` 4개와 기존 `pointerSwitch.e2e.ts` 2개, `userFlow.e2e.ts` 1개다. 도구 등록·수정의 재오픈 반영, Runtime 삭제 반영, 페이지 밖 선택 유지, 늦은 응답 경쟁을 검사했다. 갱신이 실행 중 대화를 중단하거나 추가 모델 호출을 만들지 않는 것도 확인했다.

stale SDK 회귀는 검색을 끼운 동일 실패 반복 중단, 첫 실패 후 직접 파일 읽기 회복과 질문별 범위, 다른 후보·새 revision 허용, 같은 후보의 실제 성공 재시도 허용을 검사한다. UI 단독 시험은 처음 프로젝트 root에서 실행해 JSX 설정 오류가 났고, 올바른 `apps/ui` cwd에서 다시 실행해 통과했다. 전체 `npm run check`의 UI 단위 시험도 통과했다. 이 실행 위치 오류를 앱 결함으로 계산하거나 실패 기록에서 숨기지 않는다.

코드 출처 SDK 회귀는 직접 읽기·다중 fragment·누락 제외·새 revision·실제 host 재시작을 검사한다. Python 묶음은 `test_symbol_service.py`와 `test_symbol_revisions.py`이며 5개 언어의 실제 파일 hash와 줄 범위를 대조한다. 여러 묶음에서 같은 회귀를 다시 실행했으므로 위 숫자를 합산한 총 시험 수를 제시하지 않는다.

Runtime 출처 수정 중 시작한 첫 전체 검사에서는 callback 선언의 `unbound-method` lint 오류가 있었다. callback을 화살표 함수 타입으로 명시해 수정했다. 이전 실패 로그는 `/tmp/localdesk-tools-final-check-before-fix.log`에 보존했다.

다음 전체 검사에서는 TypeScript 검사를 모두 통과했으나 Python `test_concurrent_puts_in_one_store`가 `PointerNotFound`로 실패했다(255 통과·1 실패·1 건너뜀). 이 실패 로그는 `/tmp/localdesk-tools-final-check-before-runtime-lock.log`에 보존했다. 반복 시험으로 실제 동시성 결함을 확인하고 수정한 뒤 전체 검사를 다시 실행했다. 최종 `/tmp/localdesk-tools-final-check.log`는 PASS이며, 그 이후 최종 앱 빌드·서명 검증과 실제 앱의 Runtime 읽기·출처 재검증도 완료했다.

## 재수집 방법

```sh
node --import tsx scripts/acceptance/collectDesktopTools.ts \
  /private/tmp/LocalDesk-Tools-20261111/project \
  --needle SOURCE-TARGET \
  --needle RUNTIME-TARGET \
  --needle TOOL-WRITE-OK \
  --needle PAGE-TWO-SENTINEL \
  --needle PAGE-ONE-SENTINEL \
  --needle PAGE-THREE-SENTINEL \
  --forbidden-text UNRELATED-SENTINEL \
  > /tmp/localdesk-tools-evidence.json
```

수집기는 해당 workspace의 기록만 읽고 앱·모델·승인 상태를 바꾸지 않는다. 파일·로그·PDF 원문은 바이트 수·해시·대상 일치 수로 요약하며, 정확한 range와 pointer는 남긴다. 누출 검사는 도구 결과·삽입 컨텍스트·assistant text를 대상으로 한다. 질문에 직접 적은 문자열은 누출로 계산하지 않는다. Runtime 원본 로그의 숫자가 붙은 `BULK-PRIVATE-SENTINEL` 계열과 무관한 소스 식별 문자열도 별도로 집계한다.

## 출처 표시의 현재 범위와 모델 한계

‘답변에 사용한 근거’는 실행 완료·실패·취소 후 표시되며, 현재 질문에 기록된 검증 출처가 없으면 빈 상태 문구를 보여준다. 검증된 직접 원문 읽기는 `read_file`, `code_read`, `pdf_read_pages`, `runtime_read`이며, 질문 시작 때 실제 삽입된 context fragment도 출처를 등록한다. 파일 목록·검색 후보·명령 실행 기록은 자동으로 출처가 되지 않는다.

Runtime 범위를 context fragment로 실제 삽입한 경로는 공통 provenance 기록을 사용한다. 직접 `runtime_read`의 출처 연결 누락도 수정했고, 최종 앱에서 같은 포인터·실제 읽은 범위·revision이 표시되는 것을 확인하고 저장된 hash도 대조했다. 출처는 이번 질문에 실제 제공한 원문 위치의 기록이며, 모델의 모든 문장이 그 원문에 의해 뒷받침된다는 판정은 아니다. 이전 답변을 재서술하거나 현재 읽기가 실패한 경우에는 과거 출처를 현재 질문의 출처처럼 복제하지 않는다. 수정 전에 저장된 빈 출처 기록을 소급해 채우지도 않는다.

Qwen 2.5 7B는 임의 ID·cursor, 실제 도구 호출 없는 서술, 요청과 다른 언어·줄 번호 설명을 보였다. 오류를 받은 뒤 명시적으로 다시 요청한 사례를 보존했다. 도구 실행과 검증 출처가 정상이어도 모델 답변의 모든 문장이나 여러 도구를 한 번에 정확히 사용하는 능력까지 보장하지 않는다.

## 확인 현황

- [x] 13개 도구 각각 최종 앱에서 성공 실행·결과 확인.
- [x] Runtime 대량 출력 원문이 SDK 기록에 삽입되지 않음, 실제 저장량·포인터 확인, 검색 후 정확한 부분 읽기.
- [x] PDF parse/status/search/read, 지정 페이지 출처와 페이지 격리.
- [x] 파일 작성 승인·거절, 명령 승인·거절, 실행 취소와 후속 실행.
- [x] 새 대화에서 도구 정상 사용, 앱 재시작 후 대화·출처·인덱스·포인터 상태 유지.
- [x] R0 갱신 및 Source 변경 감지 등 실패 경로와 최종 수정 반영 확인.
- [x] 자료·컨텍스트 패널을 다시 열면 새 포인터와 최신 Source revision이 표시되는지 확인.
- [x] stale 도구 오류 뒤 모델의 반복 호출 보호 감사 및 필요한 수정·검증.
- [x] 검색 캐시가 없는 직접 `code_read`와 재시작·새 revision 읽기에서 검증된 출처가 표시되는지 확인.
- [x] Runtime 직접 읽기의 검증된 출처 표시와 마지막 수정 후 앱 확인.
- [x] 마지막 전체 검사에서 발생한 Runtime 동시 저장 결함의 수정·재검증.
- [x] 여섯 수정이 반영된 최종 빌드·서명·변경 검증.
- [x] 검증 범위와 모델·출처 표시의 한계를 명시.
