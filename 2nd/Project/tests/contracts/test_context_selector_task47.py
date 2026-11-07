"""Task 4.7 Context Selector 설계 검증 테스트.

작성일: 2026-11-07
"""

import json
import os

def test_context_selector_fixture_validity():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    fixture_path = os.path.join(base_dir, "contracts/context/fixtures/context_plan_samples.json")
    doc_path = os.path.join(base_dir, "docs/architecture/CONTEXT_SELECTOR.md")

    assert os.path.exists(fixture_path) is True
    assert os.path.exists(doc_path) is True

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == "1.0.0"
    assert len(data["samples"]) >= 2

    # 명시 선택 샘플 검증
    sample1 = data["samples"][0]
    assert sample1["budget"]["used_tokens"] <= sample1["budget"]["available_tokens"]

    # 예산 초과 차단 샘플 검증
    sample2 = data["samples"][1]
    assert len(sample2["selected_candidates"]) == 0
    assert sample2["omitted"][0]["reason_code"] == "BUDGET_EXCEEDED"
