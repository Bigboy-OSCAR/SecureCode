# 포인터·컨텍스트·PDF 통합 시나리오 (4.10)

통합 시나리오는 실제로 실행되는 두 곳에 있다. `npm run test:integration`이 둘을 모두 돌린다. 이 폴더에 있던 `test_pointer_context_pdf_integration.py`는 지워진 예전 API(`ContextBudgetCalculator`, `BoundedSourceReader`)를 import해 실행되지 않았다. 2026-11-10 4.10에서 삭제했다.

## 실제 SDK 경로 (apps/host/tests/integration, 설치 `@cline/sdk` + 실제 context-service)

| 시험 | 확인하는 것 |
| --- | --- |
| `pointerLifecycleSdk.test.ts` | 다음을 확인한다. <br>- 작은 결과는 원문, 큰 결과는 포인터 <br>- run과 turn을 넘는 부분 재조회 <br>- 다른 세션 차단, Source 변경 후 새 revision <br>- 서비스 재시작 뒤 포인터 유지 <br>- PDF skill이 실제 system prompt에 등록되는지 <br>- SSE·run snapshot·SDK 기록에 원문이 없는지 <br>- gate·transformer 미등록 시 세션 거절 |
| `integratedContextSdk.test.ts` | 다음을 확인한다. <br>- 무관 파일 1,000개, 2.2 MB 로그, PDF 미선택 페이지가 provider 요청과 SDK 기록에 없는지 <br>- R0 fragment 한 번 삽입 |
| `publicContextRoutes.test.ts` | Source·미리보기·run 생성 공개 경로, stale preview·해시 불일치 거절 |
| `runtimePointerSdk.test.ts`, `runtimePointerFailures.test.ts` | 실행기 스트리밍 저장, 저장 실패·지연, 업로드 실패, 취소, 삭제·만료·세션 종료 포인터 |
| `requestBudgetSdk.test.ts`, `openAiCompatibleGateSdk.test.ts` | 요청마다 전체 본문 계수, 창 초과 차단, hard-cap |
| `pdfTools.test.ts`, `sdkSafety.test.ts`, `sdkRuns.test.ts` | PDF 도구, hook 실패 차단, 승인·취소 |

## 서비스 (services/context-service/tests)

Runtime 저장소 복구·용량·TTL, Source 경로·부분 읽기·JSON 상한, Selector 시나리오, PDF 파싱·캐시·job, 작업 공간·R0 경로를 다룬다. 실행: `services/context-service/.venv` Python으로 `pytest`.

## 실 provider

`SECURECODE_LIVE_SMOKE=1 npm run test:live`(로컬 llama.cpp 서버 필요, [운용 안내](../../docs/handoffs/4.10-pointer-operations.md)).
