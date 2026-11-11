# LocalDesk Figma 화면 구현 대응

작성일: 2026-11-11. 상태: **COMPLETED — 화면 구성·연결 구현과 최신 native 앱의 결함 재검증 완료**. 사용자의 기준은 같은 화면 구성·팝업·의도한 동작이며 픽셀 단위 일치는 요구하지 않는다.

Figma 파일 `oDegAXjc7iIY8yb138uHG1`의 페이지 `0:1`을 조회해 아래 최상위 화면과 ID를 확인했다. 메인·프로젝트·모델·검색·시작·이어가기·인덱스 팝업의 design context와 screenshot을 구현 기준으로 사용했다. 사용자 링크 `5:757`은 새 대화 제안 영역으로, 전체 화면과 팝업을 함께 검토했다. `00 · 프로토타입 안내`(`7:34`)는 Figma 사용 안내이며 앱의 작업 화면이 아니다.

공통 구현은 [LiveApp](../../apps/ui/src/app/LiveApp.tsx), [DeskSidebar](../../apps/ui/src/features/workspace/components/DeskSidebar.tsx), `styles/tokens.css`, `styles/desk*.css`다. 어두운 배경, 250px 프로젝트 사이드바, 상단 프로젝트/모델 선택, 중앙 대화, 아래 입력창, 오른쪽 이전 대화 패널, 중앙 팝업 구성을 유지한다. Figma의 원본 SVG 아이콘은 `apps/ui/public/figma/`에 보존했다.

| Figma 화면·노드 | 현재 구현 | 연결 동작·확인 근거 |
| --- | --- | --- |
| [01 메인 대화 · 3:476](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-476) | `DeskChat`, `AnswerView`, `AnswerText`, `CopyAnswer` | 실제 질문·stream·도구 단계·서버 출처. native CUA에서 코드 블록·인라인 코드·복사, 함수/helper/상수 출처, 최신 대화 위치 복원 확인 |
| [03 새 프로젝트 · 3:478](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-478), 팝업 `5:172` | `ProjectDialog` | 새 프로젝트 팝업, 폴더/이름 입력, 취소/닫기/생성. 실제 등록 성공 전 목록 추가 없음 |
| [04 로컬 폴더 선택 · 3:479](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-479) | `ProjectDialog` + native 폴더 bridge | 이 Mac의 폴더 선택창으로 선택. CUA에서 경로 이동·폴더 선택·경로/이름 자동 입력 확인 |
| [05 프로젝트 생성 준비 · 3:480](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-480) | `ProjectDialog`, `useDeskWorkspace` | 선택 경로·수정 가능한 이름, 생성 중 잠금, 오류 안내. CUA에서 이름 수정 후 생성 확인 |
| [06 프로젝트 시작 · 3:481](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-481) | `DeskWelcome`, `DeskChat` | 새 프로젝트의 폴더 아이콘·시작 안내·실제 표시 경로·입력창 |
| [07 로컬 모델 선택 · 3:482](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-482), 팝업 `5:959` | `ModelDialog`, `useDeskModels`, `ModelClient` | 상단 모델 버튼 → 검색/모델 목록 → 실제 선택 API. 설치된 Qwen2.5/Qwen3.8만 실제 목록으로 표시 |
| [08 모델 불러오는 중 · 3:483](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-483) | `ModelDialog` loading 상태 | 실제 cold load 동안 진행·선택 잠금, 300초 요청 시간, 준비 상태 재조회. 최종 native CUA에서 Qwen2.5/Qwen3.8 cold loading 완료 확인 |
| [09 모델 변경 완료 · 3:484](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-484) | 상단 모델명 + `ModelDialog` | 서버 준비 완료 후 사용 중 표시 변경, 기존 대화 보존. API 및 최신 native 앱의 양방향 전환·후속 실제 질문·대화 유지 확인 |
| [11 내 모델 관리 · 3:486](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-486) | `ModelDialog` manage 상태 | 사이드바 내 모델 → 로컬 모델 목록/검색/불러오기/새로고침. 실제 설치 모델 수·runtime·컨텍스트 한도 표시 |
| [12 대화 검색 · 3:487](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-487), 팝업 `5:1907` | `SearchDialog` in `HistoryPanel.tsx` | Command-K, 제목/질문 검색, 결과 수, 결과→이전 대화. CUA 무결과/1개 결과/결과 선택 확인 |
| [13 대화 이어가기 · 3:488](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-488) | `HistoryPanel`, `DeskChat` | 오른쪽 이전 대화, 서버 기록 조회, 이어가기 버튼으로 실제 session 전환. CUA 이어가기 성공 |
| [14 모델 선택 필요 · 3:489](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=3-489) | `LiveApp` model gate + `DeskChat` | 모델 선택 안내, 자료 준비 유지, 질문 버튼과 Enter 모두 차단. E2E 미설정 상태 확인 |
| [15 현재 프로젝트의 새 대화 · 6:162](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=6-162), 안내 `6:256` | `DeskWelcome`, `useDeskWorkspace.newChat` | 실제 새 session, 시작 제안 클릭→입력창 채우기. CUA 새 대화/제안 클릭 확인 |
| [16 인덱스 프로젝트 선택 · 38:356](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=38-356), 팝업 `48:557` | `IndexDialog` | 프로젝트 체크·선택 수·경로·로컬 처리 안내·생성/갱신. 실제 프로젝트별 요청 |
| [17 인덱스 전체 선택 · 38:519](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=38-519) | `IndexDialog` 전체 선택 | 전체 체크/해제·실제 선택 수, 선택된 프로젝트만 처리. native CUA 3개 프로젝트 전체 선택·실행 확인 |
| [18 단일 프로젝트 진행 · 38:661](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=38-661) | `IndexDialog` job 목록 | 실제 discovered/indexed/skipped/failed와 revision·diagnostics. CUA 1,009파일 진행→완료, 중복 요청 잠금 |
| [19 일괄 진행 · 38:824](https://www.figma.com/design/oDegAXjc7iIY8yb138uHG1/LocalDesk?node-id=38-824) | `IndexDialog` 복수 job | 각 프로젝트의 진행/완료/부분 완료/실패, 팝업을 닫아도 상태 조회 지속. 자동 다중 프로젝트·지연 응답 격리, native CUA 3개 프로젝트 모두 완료 확인 |

Figma의 예시 모델 이름·파일 용량·진행률·대화 내용은 실제 서버 값으로 표시한다. native 폴더 창은 이 Mac의 기본 선택창이다. 모델 관리의 메타정보는 현재 host가 제공하는 runtime·컨텍스트 한도를 사용한다. 색인 진행은 서버 파일 수와 상태를 사용하며 가상의 단계별 수치를 만들지 않는다.

로드맵의 상세 코드·Source·Runtime·PDF·예산 기능은 대화 화면의 `자료 · 컨텍스트` 오른쪽 패널에서 제공한다. Figma의 중심 대화 구성을 유지하면서 실제 승인 검토, 정확한 범위 선택, 근거 목록과 오류 복구를 연결했다. 선택한 PDF 범위는 패널을 닫아도 입력창의 선택 자료로 남고 실제 질문에 전송된다. 최종 native CUA에서 2쪽 선택 후 실제 답변 `바다`와 원본 PDF 2쪽 출처를 확인했다. 파일 변경 거절·승인·실행 취소도 직접 조작과 디스크/프로세스 결과로 검증했다.

## 최신 검증 연결

- [native 앱 조작 기록](CUA_MAC_ACCEPTANCE_2026-11-11.md): 실제 화면/팝업과 모델·자료·검색 동작, 발견 결함과 재검증 결과.
- [Mac 최종 인수 보고서](../release/ACCEPTANCE_REPORT.md): 최종 판정과 34개 UI 인수 대응. native CUA에서 발견된 기능 결함은 수정·재검증을 완료했다.
- [포인터 전환·선택 전송 E2E](../../tests/e2e/pointerSwitch.e2e.ts): 2/2 PASS, 범위/검색 초기화 및 PDF 2쪽만 실제 요청에 전달·서버 인용 확인.
- [대화 스크롤 E2E](../../tests/e2e/chatScroll.e2e.ts): 2/2 PASS, 복원·새 질문은 최신 위치, 이전 답변 읽기 중에는 위치 보존.
- [명도 대비 E2E](../../tests/e2e/contrast.e2e.ts), [측정 결과](evidence/localdesk-macos-contrast.json): 실제 CSS 24표본 최소 6.100:1.
- UI 단위 50/50 PASS, UI type/lint PASS. 안전 Markdown의 HTML 이스케이프와 완료 대화 복구, 선택 자료 재시도 보존 포함.

접근성 검증은 키보드·모달 초점·native 접근성 트리(AX)의 이름/상태·실제 CSS 명도 대비까지 통과했다. **VoiceOver의 실제 음성 낭독은 시험하지 않았다.** AX 조작 성공을 음성 낭독 검증으로 기재하지 않는다.
