# PDF 파싱 외부 의존성(pypdf) 추가 요청서

- **작성자**: 임우형 (컴퓨터공학과 C111151)
- **일자**: 2026-11-10
- **수신자**: 박준형 담당자 (Task 3.6 리드)

## 1. 요청 배경 및 사유
Task 4.9 (PDF Content Parsing) 구현 시, 제품 코드 내 Mock 경로 전면 금지 규정에 따라 자체 정규식 파서 대신 복합 폰트 매핑(CMap) 및 고도화된 FlateDecode Stream 처리가 가능한 검증된 라이브러리가 필요합니다.

## 2. 요청 내역
- **패키지명**: `pypdf` (또는 `pdfplumber`)
- **용도**: 실측 PDF 텍스트 추출, Target Page 범위 지정 추출 및 암호화 여부 검증
- **조치 사항**: `services/context-service/pyproject.toml` 및 lock 파일 반영 요청

---
박준형 담당자님께서는 해당 의존성을 승인 후 lock 파일에 반영해 주시기 바랍니다.
