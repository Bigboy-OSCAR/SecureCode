"""원자 심볼 후보 때문에 정적 참조 묶음이 누락되던 실제 Context Selector 회귀."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter
from support.source_fixtures import WS_A, FixedRoots


@pytest.mark.parametrize(
    "previous", ["none", "atomic_history", "explicit_atomic", "atomic_fallback"]
)
def test_automatic_context_keeps_dependency_bundle_once(
    tmp_path: Path, service_settings: ServiceSettings, contract_check: ContractCheck, previous: str
) -> None:
    """
    함수 이름: test_automatic_context_keeps_dependency_bundle_once()
    기능: 함수→다른 파일 helper→상수 묶음과 모든 출처를 제공하고 원자 후보 중복을 제거한다.
    인자: tmp_path -> 임시 폴더, service_settings -> 설정, contract_check -> 계약 검사, previous -> 기존 원문 위치
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    root = tmp_path / "project"
    root.mkdir()
    files = {
        "billing.py": (
            "from helpers import tax_amount\n\ndef compute_invoice_total(value):\n"
            "    return value + tax_amount(value)\n"
        ),
        "helpers.py": "from constants import TAX_RATE\n\ndef tax_amount(value):\n    return value * TAX_RATE\n",
        "constants.py": "TAX_RATE = 0.1\n",
        "unrelated.py": "def sentinel():\n    return 'UNRELATED_RAW_SENTINEL'\n",
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    app = create_app(
        service_settings,
        token_counter=FixedTokenCounter(),
        workspace_roots=FixedRoots({WS_A: root}),
    )
    with TestClient(app) as client:
        app.state.symbols.index.build(WS_A, root)
        body: dict[str, Any] = {
            "schema_version": "1",
            "input": {
                "workspace_id": WS_A,
                "session_id": "ses_00000001",
                "index_revision": 1,
                "prompt": "compute_invoice_total",
                "context_refs": [],
            },
            "costs": {
                "model_context_limit": 20000,
                "reserved_output_tokens": 1000,
                "safety_margin_tokens": 100,
                "message_overhead_tokens": 0,
                "system": "Local assistant",
                "tool_schema": "{}",
                "history": [],
            },
        }
        if previous == "atomic_fallback":
            body["costs"]["model_context_limit"] = 2300
        found = app.state.symbols.search({"workspace_id": WS_A, "query": "compute_invoice_total"})
        atomic = next(item for item in found["candidates"] if item["depth"] == 0)
        atomic_ref = {"kind": "symbol", "candidate_id": atomic["candidate_id"], "index_revision": 1}
        if previous == "atomic_history":
            body["history_refs"] = [atomic_ref]
        elif previous == "explicit_atomic":
            body["input"]["context_refs"] = [atomic_ref]
        response = client.post(
            "/internal/v1/context/select",
            json=body,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert (
            contract_check("context/context.schema.json#/definitions/ContextSelectResponse", result)
            == []
        )
        fragments = result["plan"]["fragments"]
        text = "\n".join(fragment["content"] for fragment in fragments)
        assert text.count("def compute_invoice_total") == (0 if previous == "atomic_history" else 1)
        assert text.count("def tax_amount") == (0 if previous == "atomic_fallback" else 1)
        assert text.count("TAX_RATE = 0.1") == (0 if previous == "atomic_fallback" else 1)
        assert "UNRELATED_RAW_SENTINEL" not in text
        paths: set[str] = set()
        for fragment in fragments:
            citation = fragment["provenance"]
            paths.add(citation["location"]["relative_path"])
            paths.update(
                location["relative_path"] for location in citation.get("related_locations", [])
            )
        expected = set() if previous == "atomic_fallback" else {"helpers.py", "constants.py"}
        if previous != "atomic_history":
            expected.add("billing.py")
        assert paths == expected
        if previous != "atomic_fallback":
            assert "# helpers.py:3-4" in text and "# constants.py:1-1" in text
        else:
            assert any(item["reason"] == "over_budget" for item in result["plan"]["omitted"])
