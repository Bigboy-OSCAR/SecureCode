# PDF Pointer Skill Guidelines

- **Skill ID**: pdf-pointer
- **버전**: 1.0.0
- **작성일**: 2026-11-07

---

## 1. 개요 및 사용 순서
PDF Pointer 사용 시 전체 본문을 한 번에 가져오지 말고 다음 표준 4단계 프로토콜을 준수해야 한다:

1. **등록 (`source.register`)**: PDF 디스크 파일을 Source Pointer 포맷(`securecode://source/...`)으로 등록
2. **파싱 파이프라인 (`pdf.parse`)**: PDF 총 페이지 수 및 메타데이터 캐시 상태 조율 (전체 텍스트 반환 금지)
3. **페이지 범위 조회 (`pdf.read_pages`)**: 필요한 시작/종료 페이지 범위(`start_page`, `end_page`)만 부분 조회
4. **출처 인용 (`Provenance Citation`)**: 응답 내용 뒤에 해당 PDF 식별자 및 페이지 번호(`[securecode://source/...] Page N`) 명시

---

## 2. 제한 및 에러 핸들링
- **용량 상한**: 파일 최대 50 MiB, 500 페이지 한도
- **암호화/스캔 PDF**: 암호화된 PDF는 `UNSUPPORTED_FORMAT` 에러를 반환
- **버전 변경**: 원본 PDF 수정 시 `SOURCE_CHANGED` 예외 반환 후 자동 재파싱 수행
