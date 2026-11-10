"""4.8 /internal/v1/context/select를 실제 앱(Source 등록부·Runtime 저장소·R0 색인)으로 시험한다.

선택 → 부분 원문 조회 → 실계수·중복 제거 → 계약 ContextSelectResponse를 확인하고, 0/음수 예산·여러 turn·
권한·stale·한글 경계·큰 도구 정의를 다룬다. 계수기는 시험용 FixedTokenCounter(토큰 = UTF-8 바이트)다.
"""

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from securecode_context.common.tokens import UnavailableTokenCounter
from securecode_context.context.service import ContextSelectService
from securecode_context.symbols.index import RevisionStore, SymbolIndexService
from securecode_context.symbols.ports import StaticWorkspaceRoots
from securecode_context.symbols.symbol_service import R0SymbolService
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter
from support.source_fixtures import WS_A, FixedRoots

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
SES = "ses_00000001"
RESPONSE_REF = "context/context.schema.json#/definitions/ContextSelectResponse"
REQUEST_REF = "context/context.schema.json#/definitions/ContextSelectRequest"
NOTES = ("한글 설명 줄입니다. " * 40 + "\n") * 60
SERVICE_PY = "def compute_total(items):\n    return sum(items)\n\n\ndef helper():\n    return 1\n"
BOUNDARY = len(("한글 설명 줄입니다. " * 10).encode("utf-8"))
CONTENTS = {"notes.md": NOTES, "pkg/service.py": SERVICE_PY}
LOG = "".join(f"로그 {i:05d} 상태=정상\n" for i in range(3000))


@pytest.fixture
def env(service_settings: ServiceSettings, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """
    함수 이름: env()
    기능: 작업 공간 파일, R0 색인, Selector를 연결한 앱 client를 만든다.
    인자: service_settings -> 시험 설정, tmp_path -> 임시 폴더
    반환값: client·root·index_revision 사전
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "notes.md").write_bytes(NOTES.encode("utf-8"))
    (root / "pkg" / "service.py").write_bytes(SERVICE_PY.encode("utf-8"))
    counter = FixedTokenCounter()
    app = create_app(
        service_settings, token_counter=counter, workspace_roots=FixedRoots({WS_A: root})
    )
    index = SymbolIndexService(RevisionStore(tmp_path / "symbols"))
    index.build(WS_A, root)
    revision = index.prepared(WS_A)[0]["index_revision"]
    symbols = R0SymbolService(index, counter, StaticWorkspaceRoots({WS_A: root}))
    with TestClient(app) as client:
        state = app.state
        state.context_select = ContextSelectService(
            state.source_adapter, (state.pointer_store, state.runtime_reader), counter, symbols
        )
        yield {"client": client, "root": root, "revision": revision}


def register(client: TestClient, path: str) -> dict[str, Any]:
    """
    함수 이름: register()
    기능: 파일을 Source로 등록하고 항목을 돌려준다.
    인자: client -> 앱 client, path -> 상대 경로
    반환값: SourceItem 사전
    작성 날짜: 2026/11/10
    """
    key = "reg-" + "".join(c if c.isalnum() else "-" for c in path)
    body = {
        "schema_version": "1", "idempotency_key": key, "operation": "register",
        "workspace_id": WS_A, "target": {"location": "workspace", "kind": "file", "path": path},
    }  # fmt: skip
    item: dict[str, Any] = client.post(
        "/internal/v1/source/register", json=body, headers=AUTH
    ).json()["items"][0]
    return item


def runtime(client: TestClient, content: str, session: str = SES) -> str:
    """
    함수 이름: runtime()
    기능: Runtime 출력을 저장하고 포인터를 돌려준다.
    인자: client -> 앱 client, content -> 출력, session -> 세션
    반환값: Runtime URI
    작성 날짜: 2026/11/10
    """
    body = {"workspace_id": WS_A, "session_id": session, "content": content}
    return str(
        client.post("/internal/v1/runtime/pointers", json=body, headers=AUTH).json()["pointer_uri"]
    )


def source_ref(item: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    """
    함수 이름: source_ref()
    기능: 등록 항목의 바이트 selection ref를 만든다.
    인자: item -> SourceItem, start/end -> 바이트 구간
    반환값: SelectedPointerContextRef
    작성 날짜: 2026/11/10
    """
    sha = hashlib.sha256(CONTENTS[item["relative_path"]].encode("utf-8")).hexdigest()
    selection = {
        "revision": item["revision"],
        "content_sha256": sha,
        "range": {"type": "byte", "start": start, "end": end},
    }
    return {"kind": "source", "pointer": item["pointer"], "selection": selection}


def request(env: dict[str, Any], prompt: str, **extra: Any) -> dict[str, Any]:
    """
    함수 이름: request()
    기능: 기본 비용으로 ContextSelectRequest를 만든다.
    인자: env -> 시험 환경, prompt -> 요청, extra -> 덮어쓸 필드(context_refs, costs 등)
    반환값: 요청 사전
    작성 날짜: 2026/11/10
    """
    costs = {
        "model_context_limit": 200_000, "reserved_output_tokens": 8192, "safety_margin_tokens": 2048,
        "message_overhead_tokens": 64, "system": "You are SecureCode.", "tool_schema": '{"tools":[]}',
        "history": [],
    }  # fmt: skip
    costs.update(extra.pop("costs", {}))
    plan_input = {
        "workspace_id": WS_A, "session_id": SES, "index_revision": env["revision"],
        "prompt": prompt, "context_refs": extra.pop("context_refs", []),
    }  # fmt: skip
    return {"schema_version": "1", "input": plan_input, "costs": costs, **extra}


def select(env: dict[str, Any], body: dict[str, Any], check: ContractCheck) -> dict[str, Any]:
    """
    함수 이름: select()
    기능: 요청·응답을 계약으로 검사하고 산술 불변식을 확인한다.
    인자: env -> 시험 환경, body -> 요청, check -> 계약 검사기
    반환값: 응답 사전
    작성 날짜: 2026/11/10
    """
    assert check(REQUEST_REF, body) == []
    response = env["client"].post("/internal/v1/context/select", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    assert check(RESPONSE_REF, data) == []
    plan = data["plan"]
    budget = plan["budget"]
    costs = budget["costs"]
    assert budget["budget_tokens"] == costs["model_context_limit"] - sum(
        value for key, value in costs.items() if key != "model_context_limit"
    )
    assert (
        budget["used_tokens"]
        == sum(f["token_count"] for f in plan["fragments"])
        <= budget["budget_tokens"]
    )
    assert budget["count_mode"] == "provider_estimate"
    for fragment in plan["fragments"]:
        selection = fragment["provenance"]["ref"].get("selection")
        if selection is not None:
            width = selection["range"]["end"] - selection["range"]["start"]
            assert width == len(fragment["content"].encode("utf-8"))
    return data


def reasons(data: dict[str, Any]) -> dict[str, str]:
    """
    함수 이름: reasons()
    기능: 누락 이유를 candidate_id별로 모은다.
    인자: data -> 응답
    반환값: {candidate_id: reason}
    작성 날짜: 2026/11/10
    """
    return {row["candidate_id"]: row["reason"] for row in data["plan"]["omitted"]}


def test_select_reads_partial_ranges_dedups_and_respects_history(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_select_reads_partial_ranges_dedups_and_respects_history()
    기능: 명시 Source 범위는 그대로, 큰 자동 Runtime은 16 KiB에서 UTF-8 경계로 자르고, 명시 범위 안
        자동 범위는 duplicate, 이력에 있는 범위는 in_history, 같은 파일의 R0 심볼은 Source와 비교한다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    client = env["client"]
    notes, service = register(client, "notes.md"), register(client, "pkg/service.py")
    log = runtime(client, LOG)
    seen = runtime(client, "이미 본 출력\n" * 50)
    explicit = [source_ref(notes, 0, BOUNDARY), source_ref(service, 0, len(SERVICE_PY))]
    inside = source_ref(notes, 30, 120)
    history = [
        {
            "kind": "runtime",
            "pointer": seen,
            "selection": {
                **_runtime_selection(client, seen),
                "range": {"type": "byte", "start": 0, "end": 900},
            },
        }
    ]
    body = request(
        env, "compute_total items", context_refs=explicit,
        current_task_refs=[{"kind": "runtime", "pointer": log}, inside, {"kind": "runtime", "pointer": seen}],
        history_refs=history,
    )  # fmt: skip
    data = select(env, body, contract_check)
    plan = data["plan"]
    by_id = {f["candidate_id"]: f for f in plan["fragments"]}
    notes_text = NOTES.encode("utf-8")
    first = plan["fragments"][0]
    assert (
        first["content"].encode("utf-8") == notes_text[0:BOUNDARY] and first["inclusion"] == "full"
    )
    log_fragment = next(f for f in by_id.values() if f["ref"].get("pointer") == log)
    assert log_fragment["inclusion"] == "partial_size"
    assert len(log_fragment["content"].encode("utf-8")) <= 16 * 1024
    assert LOG.encode("utf-8").startswith(log_fragment["content"].encode("utf-8"))
    omitted = {row["reason"] for row in plan["omitted"]}
    assert {"duplicate", "in_history"} <= omitted
    symbol_rows = [row for row in plan["omitted"] if row["origin"] == "r0"]
    assert symbol_rows and all(row["reason"] == "duplicate" for row in symbol_rows)
    assert data["run_create_error"] is None


def _runtime_selection(client: TestClient, pointer: str) -> dict[str, Any]:
    """
    함수 이름: _runtime_selection()
    기능: Runtime 읽기 결과의 selection(checksum)을 얻는다.
    인자: client -> 앱 client, pointer -> URI
    반환값: PointerSelection
    작성 날짜: 2026/11/10
    """
    body = {
        "schema_version": "1",
        "workspace_id": WS_A,
        "session_id": SES,
        "pointer": pointer,
        "max_bytes": 16,
    }
    read = client.post("/internal/v1/runtime/read", json=body, headers=AUTH).json()
    selection: dict[str, Any] = read["provenance"]["selection"]
    return selection


def test_second_turn_skips_what_the_first_turn_inserted(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_second_turn_skips_what_the_first_turn_inserted()
    기능: 첫 turn fragment의 provenance를 다음 turn history_refs로 넘기면 같은 원문을 다시 넣지 않는다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    log = runtime(env["client"], LOG)
    body = request(env, "다음 단계", current_task_refs=[{"kind": "runtime", "pointer": log}])
    first = select(env, body, contract_check)["plan"]
    inserted = [f["provenance"]["ref"] for f in first["fragments"]]
    second = select(env, {**body, "history_refs": inserted}, contract_check)["plan"]
    first_end = first["fragments"][0]["provenance"]["ref"]["selection"]["range"]["end"]
    next_range = second["fragments"][0]["provenance"]["ref"]["selection"]["range"]
    assert next_range["start"] == first_end > 0
    covered = {
        **inserted[0],
        "selection": {
            **inserted[0]["selection"],
            "range": {"type": "byte", "start": 0, "end": len(LOG.encode("utf-8"))},
        },
    }
    third = select(env, {**body, "history_refs": [covered]}, contract_check)["plan"]
    assert not third["fragments"] and set(reasons({"plan": third}).values()) == {"in_history"}
    assert select(env, body, contract_check)["plan"]["preview_digest"] == first["preview_digest"]


def test_unauthorized_and_stale_choices_block_run_creation(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_unauthorized_and_stale_choices_block_run_creation()
    기능: 다른 세션 Runtime·다른 workspace Source는 unauthorized, 바뀐 파일의 확인 범위는 stale이며
        run 생성 오류는 처리 순서상 첫 명시 누락(FORBIDDEN)이다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    client = env["client"]
    notes = register(client, "notes.md")
    old = source_ref(notes, 0, 50)
    (env["root"] / "notes.md").write_bytes(("바뀐 내용\n" * 10).encode("utf-8"))
    foreign = runtime(client, "다른 세션", session="ses_00000099")
    foreign_ref = {
        "kind": "runtime",
        "pointer": foreign,
        "selection": {
            "revision": 1,
            "content_sha256": "0" * 64,
            "range": {"type": "byte", "start": 0, "end": 3},
        },
    }
    other_ws = {**old, "pointer": old["pointer"].replace(WS_A, "ws_00000002")}
    data = select(
        env, request(env, "확인", context_refs=[foreign_ref, other_ws, old]), contract_check
    )
    assert list(reasons(data).values()) == ["unauthorized", "unauthorized", "stale"]
    assert data["run_create_error"] == "FORBIDDEN"
    assert data["plan"]["fragments"] == []


def test_zero_budget_omits_everything_and_negative_budget_is_an_error(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_zero_budget_omits_everything_and_negative_budget_is_an_error()
    기능: 예산 0이면 빈 계획과 over_budget(run 생성 BUDGET_EXCEEDED), 음수면 계획 없이 BUDGET_EXCEEDED다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    notes = register(env["client"], "notes.md")
    prompt = "질문"
    fixed = (
        len("You are SecureCode.") + len('{"tools":[]}') + len(prompt.encode()) + 64 + 8192 + 2048
    )
    zero = request(
        env, prompt, context_refs=[source_ref(notes, 0, 10)], costs={"model_context_limit": fixed}
    )
    data = select(env, zero, contract_check)
    assert data["plan"]["budget"]["budget_tokens"] == 0
    assert reasons(data) and set(reasons(data).values()) == {"over_budget"}
    assert data["run_create_error"] == "BUDGET_EXCEEDED"
    negative = request(env, prompt, costs={"model_context_limit": fixed - 1})
    response = env["client"].post("/internal/v1/context/select", json=negative, headers=AUTH)
    assert response.json()["error"]["code"] == "BUDGET_EXCEEDED"


def test_large_tool_schema_and_history_shrink_the_budget(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_large_tool_schema_and_history_shrink_the_budget()
    기능: 큰 도구 정의·이력(한글)을 실제로 세어 예산을 줄이고, 남은 예산이 작으면 자동 후보를 넣지 않는다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    log = runtime(env["client"], LOG)
    tools = (
        '{"tools":['
        + ",".join(f'{{"name":"t{i}","description":"{"설명" * 50}"}}' for i in range(300))
        + "]}"
    )
    history = ["사용자: 이전 질문 " * 100, "도구 결과: 짧음"]
    body = request(
        env, "질문", current_task_refs=[{"kind": "runtime", "pointer": log}],
        costs={"model_context_limit": 200_000, "tool_schema": tools, "history": history},
    )  # fmt: skip
    data = select(env, body, contract_check)
    costs = data["plan"]["budget"]["costs"]
    assert costs["tool_schema_tokens"] == len(tools.encode("utf-8"))
    assert costs["history_tokens"] == sum(len(h.encode("utf-8")) for h in history)
    reserve = 8192 + data["plan"]["budget"]["budget_tokens"] - 200
    tight = request(
        env, "질문", current_task_refs=[{"kind": "runtime", "pointer": log}],
        costs={"reserved_output_tokens": reserve, "tool_schema": tools, "history": history},
    )  # fmt: skip
    small = select(env, tight, contract_check)
    assert small["plan"]["fragments"] == []
    assert set(reasons(small).values()) == {"over_budget"}


def test_unavailable_counter_refuses_selection(service_settings: ServiceSettings) -> None:
    """
    함수 이름: test_unavailable_counter_refuses_selection()
    기능: 계수기가 없으면 길이/4로 대신하지 않고 TOKENIZER_UNAVAILABLE을 돌려준다.
    인자: service_settings -> 시험 설정
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    app = create_app(service_settings, token_counter=UnavailableTokenCounter("api_key_missing"))
    plan_input = {
        "workspace_id": WS_A,
        "session_id": SES,
        "index_revision": 1,
        "prompt": "q",
        "context_refs": [],
    }
    costs = {
        "model_context_limit": 9000,
        "reserved_output_tokens": 1,
        "safety_margin_tokens": 0,
        "message_overhead_tokens": 0,
        "system": "s",
        "tool_schema": "",
        "history": [],
    }
    with TestClient(app) as client:
        response = client.post(
            "/internal/v1/context/select",
            json={"schema_version": "1", "input": plan_input, "costs": costs},
            headers=AUTH,
        )
    assert response.json()["error"]["code"] == "TOKENIZER_UNAVAILABLE"


def test_response_stays_inside_the_host_response_limit(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_response_stays_inside_the_host_response_limit()
    기능: 16 KiB 자동 후보가 많아도 응답 JSON은 256 KiB(host loopback 상한) 안이고 나머지는 over_budget이다.
    인자: env -> 시험 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    refs = [
        {"kind": "runtime", "pointer": runtime(env["client"], f"{i}번 " + LOG)} for i in range(16)
    ]
    data = select(env, request(env, "많은 출력", current_task_refs=refs), contract_check)
    raw = (
        env["client"]
        .post(
            "/internal/v1/context/select",
            json=request(env, "많은 출력", current_task_refs=refs),
            headers=AUTH,
        )
        .content
    )
    assert len(raw) <= 256 * 1024
    assert 0 < len(data["plan"]["fragments"]) < 16
    assert set(reasons(data).values()) == {"over_budget"}
