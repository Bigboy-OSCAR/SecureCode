# 2.3 검토 증거

2026-11-09 (Asia/Seoul), 기준 소스 `ced79c1e`. 로컬 fixture UI만 실행했다. 실제 API·도구·원본 파일 변경은 없다. [검증 기록](../../tasks/2.3.md) 및 [수정 요청](../../../handoffs/2.3-ui-review-fixes.md)과 함께 읽는다.

| 파일 | 실제 확인한 내용 |
| --- | --- |
| [approval-1280.jpg](approval-1280.jpg) | 승인 검토창의 전체 명령, 결정/닫기 조작 |
| [cancelled-1280.jpg](cancelled-1280.jpg) · [cancel-observation.json](cancel-observation.json) | 취소 terminal 표시와 취소 전후 질문 대체. JSON은 SC-03 텍스트만 포함하며 승인 이력 소실은 별도 브라우저 관찰/코드 검토 근거 |
| [pointer-read-1280.jpg](pointer-read-1280.jpg) | 한글 원문·오류 예시 혼재 및 다음 부분 fixture 미제공 안내 |
| [pdf-unsupported-1280.jpg](pdf-unsupported-1280.jpg) · [pdf-states.json](pdf-states.json) | 7개 PDF 상태를 각각 선택했을 때 실제 표시 문구. 실제 PDF 추출 결과가 아님 |
| [layout-1280.jpg](layout-1280.jpg) · [layout-1280.json](layout-1280.json) | 실제 CSS viewport 1280×900, 3열과 가로 넘침 없음 |
| [layout-768.jpg](layout-768.jpg) · [layout-768.json](layout-768.json) | 실제 CSS viewport 768×900, 1열과 가로 넘침 없음. 패널 접기는 미구현 |
| [ui-tests.log](ui-tests.log) | UI 26/26 자동 시험 출력 |
| [ui-build.log](ui-build.log) | 타입 검사 및 production build 출력 |
| [contracts.log](contracts.log) | 생성 타입·TypeScript 232/232·Python 200/200 검증 출력 |

화면 캡처는 해당 패널의 보이는 영역이다. viewport 요청 크기와 CSS 실측값이 달랐기 때문에 최종 캡처는 `innerWidth`/`innerHeight`를 확인한 후 저장했다. 로그의 개인 절대경로는 `<project>`로 치환했으며 시험 결과는 변경하지 않았다. 스크린리더 낭독·200% 확대·실서비스 인수를 수행했다는 증거로 사용하지 않는다.
