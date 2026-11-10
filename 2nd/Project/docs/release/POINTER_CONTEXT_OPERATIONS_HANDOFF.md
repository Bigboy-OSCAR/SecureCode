# Pointer / Context Selector / PDF 운용 인계 문서

> 2026-11-11: 이 문서는 대체됐다. 현재 운용 기준은 [4.10 운용 안내](../handoffs/4.10-pointer-operations.md)와 [RUNBOOK](RUNBOOK.md)이다. 아래는 2026-11-07 기록으로 남긴다.

> 2026-11-09 재검토: 인수 준비 미완료. 아래 상한은 목표 정책이며 전부 구현·검증된 값이 아니다. 4.3~4.9 재개방 및 4.10 BLOCKED. [현재 판정](../progress/ROADMAP_REVIEW_2026-11-09.md)을 먼저 확인한다.

- **작성일**: 2026-11-07
- **담당자**: 임우형
- **인계 대상자**: 박준형 (R0/Host 통합 3.7), 김민지 (UI 연동 1.6)

---

## 1. 개요 및 모듈 위치
본 모듈은 거대한 실행 출력 및 디스크 파일을 URI 포인터로 캡슐화하고, 토큰 예산 내에서 안전하게 Bounded Read를 수행하는 파이프라인을 제공한다.

- **Source Pointer**: `securecode_context.pointers.source` (`models`, `registry`, `index`, `readers`, `search`)
- **Runtime Pointer**: `securecode_context.pointers.runtime` (`models`, `store`)
- **Context Selector**: `securecode_context.context` (`models`, `budget`, `policy`)
- **PDF Service**: `securecode_context.pdf` (`parser`, `cache`, `tools`)

---

## 2. 예산 및 용량 상한 기준 (Invariants)
- **Runtime 객체 상한**: 단일 32 MiB, 세션 합계 128 MiB (TTL 24시간)
- **Source 디스크 파일**: 256 MiB 상한, JSON path 8 MiB 상한
- **PDF 파일 한도**: 최대 50 MiB, 500 페이지 한도 (암호화 PDF 미지원 `UNSUPPORTED_FORMAT`)
- **부분 읽기 (Bounded Read)**: `max_bytes` 16,384, `max_tokens` 32,768 한도 준수

---

## 3. 예외 핸들링 및 장애 복구 가이드
1. **`SOURCE_CHANGED`**: 원본 디스크 파일 수정 시 발생 → `pdf.parse` 또는 `source.register`로 새 revision 갱신 필요
2. **`BUDGET_EXCEEDED`**: 전체 예산 초과 시 발생 → 자동 요약기/전체 수용을 적용하지 않고 사용자에게 새 세션 개설 안내
3. **`FORBIDDEN`**: Workspace root 외부 경로 접근 시 발생 → 허용 외부 경로 등록 필요
