# Context Selector architecture & Policy Design

- **문서 버전**: 1.0.0
- **작성일**: 2026-11-07
- **담당자**: 임우형

---

## 1. 개요 및 설계 목표
Context Selector는 R0 Symbol Bundle, Source Pointer, Runtime Pointer 자료 간 중복을 방지하고 모델의 토큰 예산(Budget) 내에서 최적의 원문 컨텍스트 묶음(ContextPlan)을 결정적으로(Deterministically) 선별하는 핵심 조정 계층이다.

---

## 2. 예산 계산 모델 (Budget Formula)
로컬 컨텍스트 예산은 아래 공식으로 계산한다:

$$available\_context = model\_context\_limit - (tokens(system + tool\_schema + user + history + overhead) + reserved\_output + safety\_margin)$$

- **system / tool_schema / user**: 기본 시스템 지침 및 사용 도구 메타데이터, 사용자 요청 문자열
- **history**: 기존 대화 이력 (ToolCall - ToolResult 쌍 필수 유지)
- **reserved_output**: 모델 답변 생성용 보장 토큰 (기본 4,096 tokens)
- **safety_margin**: Framing 오버헤드 완화를 위한 안전 마진 (기본 1,024 tokens)

---

## 3. 후보 선택 우선순위 (Selection Priority & Normalization)
1. **Scope & Revision 검증**: 유효한 Workspace Scope 및 Revision 일치 여부 확인
2. **명시적 선택 (Explicit User Selections)**: 사용자가 UI에서 지정한 포인터/파일 우선 할당
3. **현재 요청 연관 자료 (Current Tool/Execution References)**: 최근 실행 결과 및 Runtime Pointer
4. **R0 심볼 점수 (Normalized R0 Scores)**: TF-IDF 코사인 점수를 `[0.0, 1.0]` 범위로 정규화하여 정렬
5. **동점 처리 (Stable Ordering)**: 점수 동점 시 Candidate ID의 사전순 정렬

---

## 4. Materialization 및 Host - Selector 책임 분리
- **Selector의 책임**:
  - 후보 필터링, 토큰 예산 안 범위 선택, 각 Resolver를 통한 bounded read 실행
  - `ContextPlan` DTO 생성 (선택 메타데이터 `selected`와 바운디드 원문 `fragments` 명시 분리)
- **Host의 책임**:
  - `ContextPlan.fragments`를 모델 전달 메시지 본문에 **단 1회만 중복 없이 삽입**

---

## 5. 예산 초과 및 실패 정책 (Failure Policies)
- **BUDGET_EXCEEDED**: History 또는 명시 선택 자체만으로 예산 초과 시 즉시 차단하며, 새 요약기나 파일 전체 전송 fallback을 적용하지 않고 **새 세션 개설 또는 범위 축소**를 안내한다.
- **Tool-Call Pair 보존**: history 내 ToolCall과 ToolResult의 짝을 강제로 자르거나 일부만 제거하지 않는다.
