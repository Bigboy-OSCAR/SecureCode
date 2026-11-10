"""4.9 PDF: 실제 앱(Source 등록부·파생 캐시·격리 파싱 프로세스)으로 parse → status → 페이지 읽기·검색을 시험한다.

fixture는 tests/support/pdf_fixtures.py가 만드는 텍스트 PDF(한글 CID 글꼴, 압축 stream)다.
"""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter
from support.pdf_fixtures import PageSpec, build_pdf
from support.source_fixtures import WS_A, FixedRoots

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
JOB_REF = "pointers/pdf-job.schema.json#/definitions/PdfJobStatus"
READ_REF = "pointers/read.schema.json#/definitions/PointerReadResult"
SEARCH_REF = "pointers/search.schema.json#/definitions/PointerSearchResult"
KOREAN = [
    PageSpec(("첫째 페이지 PAGE-ONE-SENTINEL", "한글 본문 둘째 줄")),
    PageSpec(("둘째 페이지 PAGE-TWO-SENTINEL", "검색어 바다 포함")),
    PageSpec(("셋째 페이지 PAGE-THREE-SENTINEL",)),
]


@pytest.fixture
def env(service_settings: ServiceSettings, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """
    함수 이름: env()
    기능: PDF fixture가 있는 작업 공간과 앱 client를 만든다.
    인자: service_settings -> 시험 설정, tmp_path -> 임시 폴더
    반환값: client·root·app 사전
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "docs"
    root.mkdir()
    files = {
        "korean.pdf": build_pdf(KOREAN),
        "reversed.pdf": build_pdf(KOREAN, reverse_kids=True),
        "partial.pdf": build_pdf([KOREAN[0], PageSpec(), PageSpec(image=True), KOREAN[2]]),
        "scanned.pdf": build_pdf([PageSpec(image=True), PageSpec(image=True)]),
        "empty.pdf": build_pdf([PageSpec(), PageSpec()]),
        "encrypted.pdf": build_pdf(KOREAN[:1], encrypted=True),
        "toomany.pdf": build_pdf([PageSpec(("p",))] * 501),
        "damaged.pdf": b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 9 0 R >>\n%%EOF\n",
    }
    for name, data in files.items():
        (root / name).write_bytes(data)
    app = create_app(
        service_settings,
        token_counter=FixedTokenCounter(),
        workspace_roots=FixedRoots({WS_A: root}),
    )
    with TestClient(app) as client:
        yield {"client": client, "root": root, "app": app, "data": service_settings.data_dir}


def post(env: dict[str, Any], route: str, **body: Any) -> Any:
    """
    함수 이름: post()
    기능: schema_version·workspace를 넣어 내부 경로를 호출한다.
    인자: env -> 환경, route -> 경로, body -> 본문
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    payload = {"schema_version": "1", "workspace_id": WS_A, **body}
    return env["client"].post(f"/internal/v1/{route}", json=payload, headers=AUTH).json()


def register(env: dict[str, Any], name: str) -> str:
    """
    함수 이름: register()
    기능: 파일을 Source로 등록하고 포인터를 돌려준다.
    인자: env -> 환경, name -> 파일 이름
    반환값: Source URI
    작성 날짜: 2026/11/10
    """
    key = "reg-" + name.replace(".", "-")
    target = {"location": "workspace", "kind": "file", "path": name}
    body = post(env, "source/register", idempotency_key=key, operation="register", target=target)
    return str(body["items"][0]["pointer"])


def parse(env: dict[str, Any], pointer: str, check: ContractCheck, key: str = "parse-0001") -> Any:
    """
    함수 이름: parse()
    기능: parse를 제출하고 끝날 때까지(최대 60초) 상태를 확인한다. 모든 응답을 계약으로 검사한다.
    인자: env -> 환경, pointer -> URI, check -> 계약 검사기, key -> idempotency key
    반환값: 마지막 PdfJobStatus
    작성 날짜: 2026/11/10
    """
    status = post(env, "pdf/parse", pointer=pointer, idempotency_key=key)
    deadline = time.monotonic() + 60
    while status.get("state") in ("queued", "running") and time.monotonic() < deadline:
        assert check(JOB_REF, status) == []
        time.sleep(0.1)
        status = post(env, "pdf/status", job_id=status["job_id"])
    assert check(JOB_REF, status) == [], status
    return status


def read(
    env: dict[str, Any], pointer: str, start: int, end: int | None = None, **extra: Any
) -> Any:
    """
    함수 이름: read()
    기능: pdf_page selector로 페이지를 읽는다.
    인자: env -> 환경, pointer -> URI, start/end -> 페이지, extra -> max_bytes·cursor 등
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    selector: dict[str, Any] = {"type": "pdf_page", "start": start}
    if end is not None:
        selector["end"] = end
    return post(env, "source/read", pointer=pointer, selector=selector, **extra)


def test_parse_returns_metadata_and_reads_only_the_requested_page(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_parse_returns_metadata_and_reads_only_the_requested_page()
    기능: parse·status에는 본문이 없고, 2페이지 읽기에는 1·3페이지 sentinel이 없으며 출처 페이지가 정확하다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    status = parse(env, pointer, contract_check)
    assert (status["state"], status["page_count"]) == ("ready", 3)
    assert "SENTINEL" not in json.dumps(status) and "페이지" not in json.dumps(status)
    page = read(env, pointer, 2)
    assert contract_check(READ_REF, page) == []
    assert "PAGE-TWO-SENTINEL" in page["content"] and "둘째 페이지" in page["content"]
    assert "PAGE-ONE" not in page["content"] and "PAGE-THREE" not in page["content"]
    selection = page["provenance"]["selection"]
    assert selection["range"]["page"] == 2
    assert selection["range"]["parser_version"] == status["parser_version"]
    assert selection["content_sha256"] == status["content_sha256"]
    width = selection["range"]["end"] - selection["range"]["start"]
    assert width == len(page["content"].encode("utf-8"))
    assert read(env, pointer, 4)["error"]["details"]["reason"] == "page_out_of_range"


def test_page_range_streams_one_page_at_a_time_with_cursor(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_page_range_streams_one_page_at_a_time_with_cursor()
    기능: 1~3페이지 요청을 작은 바이트 상한으로 읽으면 한 번에 한 페이지 구간만 오고 cursor로 이어진다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    parse(env, pointer, contract_check)
    seen: list[tuple[int, str]] = []
    result = read(env, pointer, 1, 3, max_bytes=24)
    for _ in range(40):
        assert contract_check(READ_REF, result) == []
        seen.append((result["provenance"]["selection"]["range"]["page"], result["content"]))
        if "next_cursor" not in result:
            break
        result = read(env, pointer, 1, 3, max_bytes=24, cursor=result["next_cursor"])
    pages = {number: "".join(text for n, text in seen if n == number) for number, _ in seen}
    assert sorted(pages) == [1, 2, 3]
    assert "PAGE-ONE-SENTINEL" in pages[1] and "PAGE-THREE-SENTINEL" in pages[3]
    assert all(len(text.encode("utf-8")) <= 24 for _, text in seen)


def test_page_tree_order_not_object_order(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_page_tree_order_not_object_order()
    기능: 페이지 객체 번호가 거꾸로여도 page tree 순서대로 번호를 붙인다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "reversed.pdf")
    parse(env, pointer, contract_check)
    assert "PAGE-ONE-SENTINEL" in read(env, pointer, 1)["content"]
    assert "PAGE-THREE-SENTINEL" in read(env, pointer, 3)["content"]


def test_partial_document_excludes_empty_and_scanned_pages(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_partial_document_excludes_empty_and_scanned_pages()
    기능: 빈·스캔 페이지는 excluded_pages로 알리고 읽기를 거절하며, 범위 읽기는 그 페이지를 건너뛴다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "partial.pdf")
    status = parse(env, pointer, contract_check)
    assert status["state"] == "partial"
    assert status["excluded_pages"] == [
        {"page": 2, "reason": "empty_page"},
        {"page": 3, "reason": "scanned_page"},
    ]
    assert read(env, pointer, 2)["error"]["details"]["reason"] == "page_excluded"
    first = read(env, pointer, 1, 4)
    second = read(env, pointer, 1, 4, cursor=first["next_cursor"])
    assert second["provenance"]["selection"]["range"]["page"] == 4


@pytest.mark.parametrize(
    ("name", "state", "reason", "code"),
    [
        ("scanned.pdf", "unsupported", "scanned_document", "UNSUPPORTED_FORMAT"),
        ("empty.pdf", "unsupported", "empty_document", "UNSUPPORTED_FORMAT"),
        ("encrypted.pdf", "unsupported", "encrypted", "UNSUPPORTED_FORMAT"),
        ("toomany.pdf", "unsupported", "page_limit", "UNSUPPORTED_FORMAT"),
        ("damaged.pdf", "failed", "damaged", "PARSE_FAILED"),
    ],
)
def test_unreadable_documents_are_never_reported_as_ready(
    env: dict[str, Any],
    contract_check: ContractCheck,
    name: str,
    state: str,
    reason: str,
    code: str,
) -> None:
    """
    함수 이름: test_unreadable_documents_are_never_reported_as_ready()
    기능: 스캔·빈·암호화·페이지 초과·손상 PDF는 이유와 함께 unsupported/failed이고 페이지를 읽을 수 없다.
    인자: env -> 환경, contract_check -> 계약 검사기, name/state/reason/code -> 기대값
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, name)
    status = parse(env, pointer, contract_check)
    assert (status["state"], status["reason"]) == (state, reason)
    assert read(env, pointer, 1)["error"]["code"] == code


def test_same_source_reuses_one_job_and_one_cache(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_same_source_reuses_one_job_and_one_cache()
    기능: 다른 idempotency key로 다시 보내도 같은 job이며 캐시(원본 해시+파서 버전)는 하나다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    first = parse(env, pointer, contract_check)
    again = post(env, "pdf/parse", pointer=pointer, idempotency_key="parse-0002")
    assert again == first
    caches = list((env["data"] / "derived").glob("pdf-*"))
    assert len(caches) == 1
    manifest = json.loads((caches[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parser_version"] == first["parser_version"]
    assert manifest["content_sha256"] == first["content_sha256"]


def test_changed_source_is_stale_until_refresh_and_reparse(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_changed_source_is_stale_until_refresh_and_reparse()
    기능: 원본이 바뀌면 status는 stale·읽기는 SOURCE_CHANGED이고, refresh 뒤 새 parse가 새 내용을 읽는다.
        이전 revision 캐시는 참조가 풀려 지워진다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    first = parse(env, pointer, contract_check)
    old_caches = set((env["data"] / "derived").glob("pdf-*"))
    (env["root"] / "korean.pdf").write_bytes(build_pdf([PageSpec(("바뀐 문서 CHANGED-SENTINEL",))]))
    stale = post(env, "pdf/status", job_id=first["job_id"])
    assert (stale["state"], stale["reason"]) == ("stale", "source_changed")
    assert read(env, pointer, 1)["error"]["code"] == "SOURCE_CHANGED"
    refreshed = post(
        env, "source/refresh", idempotency_key="refresh-001", operation="refresh", pointer=pointer
    )
    new_pointer = refreshed["items"][0]["pointer"]
    second = parse(env, new_pointer, contract_check, key="parse-0003")
    assert second["state"] == "ready" and second["job_id"] != first["job_id"]
    assert "CHANGED-SENTINEL" in read(env, new_pointer, 1)["content"]
    assert not old_caches & set((env["data"] / "derived").glob("pdf-*"))


def test_unregister_removes_the_page_cache(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_unregister_removes_the_page_cache()
    기능: 등록 해제 시 마지막 참조가 풀린 PDF 페이지 캐시를 지운다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    parse(env, pointer, contract_check)
    assert list((env["data"] / "derived").glob("pdf-*"))
    removed = post(
        env, "source/unregister", idempotency_key="unreg-0001", kind="source", pointer=pointer
    )
    assert "error" not in removed, removed
    assert not list((env["data"] / "derived").glob("pdf-*"))


def test_timeout_is_failed_and_leaves_no_cache(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_timeout_is_failed_and_leaves_no_cache()
    기능: 시간 상한을 넘기면 failed/timeout이고 캐시·작업 폴더가 남지 않으며 페이지를 읽을 수 없다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    env["app"].state.pdf.jobs.timeout = 0.001
    pointer = register(env, "korean.pdf")
    status = parse(env, pointer, contract_check)
    assert (status["state"], status["reason"]) == ("failed", "timeout")
    assert not list((env["data"] / "derived").glob("pdf-*"))
    assert not list((env["data"] / "pdf-work").iterdir())
    assert read(env, pointer, 1)["error"]["details"]["reason"] == "pdf_not_parsed"
    env["app"].state.pdf.jobs.timeout = 60.0
    assert parse(env, pointer, contract_check, key="parse-retry1")["state"] == "ready"


def test_cancel_forgets_the_job_and_cleans_up(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_cancel_forgets_the_job_and_cleans_up()
    기능: 취소한 job은 조회되지 않고 작업 폴더가 비워진다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    started = post(env, "pdf/parse", pointer=pointer, idempotency_key="parse-0001")
    assert post(env, "pdf/cancel", job_id=started["job_id"]) == {"cancelled": True}
    assert post(env, "pdf/status", job_id=started["job_id"])["error"]["code"] == "NOT_FOUND"
    deadline = time.monotonic() + 20
    while list((env["data"] / "pdf-work").iterdir()) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not list((env["data"] / "pdf-work").iterdir())


def test_search_finds_pages_and_cites_them(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_search_finds_pages_and_cites_them()
    기능: PDF 검색은 일치한 페이지 번호와 페이지 안 구간을 출처로 주고 다른 페이지 본문을 싣지 않는다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    parse(env, pointer, contract_check)
    result = post(env, "source/search", pointer=pointer, query="바다")
    assert contract_check(SEARCH_REF, result) == []
    assert [m["selection"]["range"]["page"] for m in result["matches"]] == [2]
    assert "PAGE-ONE" not in json.dumps(result, ensure_ascii=False)


def test_selected_pdf_page_becomes_a_cited_context_fragment(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_selected_pdf_page_becomes_a_cited_context_fragment()
    기능: 페이지 읽기 결과의 selection을 명시 선택으로 넘기면 같은 구간만 fragment로 들어가고,
        원본이 바뀌면 stale로 빠진다(4.8 Selector 연결).
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = register(env, "korean.pdf")
    parse(env, pointer, contract_check)
    page = read(env, pointer, 2)
    ref = {"kind": "source", "pointer": pointer, "selection": page["provenance"]["selection"]}
    plan_input = {"workspace_id": WS_A, "session_id": "ses_00000001", "index_revision": 1,
                  "prompt": "둘째 페이지 요약", "context_refs": [ref]}  # fmt: skip
    costs = {"model_context_limit": 100_000, "reserved_output_tokens": 1000, "safety_margin_tokens": 0,
             "message_overhead_tokens": 0, "system": "s", "tool_schema": "", "history": []}  # fmt: skip
    body = {"schema_version": "1", "input": plan_input, "costs": costs}
    plan = env["client"].post("/internal/v1/context/select", json=body, headers=AUTH).json()
    assert (
        contract_check("context/context.schema.json#/definitions/ContextSelectResponse", plan) == []
    )
    fragment = plan["plan"]["fragments"][0]
    assert fragment["content"] == page["content"]
    assert fragment["provenance"]["ref"]["selection"]["range"]["page"] == 2
    (env["root"] / "korean.pdf").write_bytes(build_pdf([PageSpec(("다른 내용",))]))
    stale = env["client"].post("/internal/v1/context/select", json=body, headers=AUTH).json()
    assert [row["reason"] for row in stale["plan"]["omitted"]] == ["stale"]
    assert stale["run_create_error"] == "SOURCE_CHANGED"


def test_worker_process_is_killed_on_cancel(tmp_path: Path) -> None:
    """
    함수 이름: test_worker_process_is_killed_on_cancel()
    기능: 취소 신호가 오면 격리 파싱 프로세스를 끝내고 결과를 남기지 않는다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    import threading

    from securecode_context.pdf.worker import ParseCancelledError, run_isolated

    source = tmp_path / "a.pdf"
    source.write_bytes(build_pdf(KOREAN))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ParseCancelledError):
        run_isolated(source, tmp_path / "out", 500, 60.0, cancel)
    assert not (tmp_path / "out" / "result.json").exists()
