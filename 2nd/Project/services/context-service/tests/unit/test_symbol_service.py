"""R0SymbolService의 다섯 언어 검색·원문 묶음·무결과·중복·예산·stale·페이지 계약 시험."""

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.models import TokenCount
from securecode_context.symbols.index import RevisionStore, SymbolIndexService
from securecode_context.symbols.ports import StaticWorkspaceRoots
from securecode_context.symbols.public_ids import candidate_id, symbol_id
from securecode_context.symbols.symbol_service import R0SymbolService
from support.helpers import FixedTokenCounter
from support.symbol_projects import LANGUAGE_PROJECTS, SHARED_NAME_FILES, write_project

WORKSPACE_ID = "ws_01J9Z6Q4TEST"
SEARCH_SCHEMA = "symbols/symbol.schema.json#/definitions/SymbolSearchResponse"
BUNDLE_SCHEMA = "symbols/symbol.schema.json#/definitions/SymbolBundle"
# 언어별 식별자 검색어와 1위가 돼야 하는 시작 심볼(경로::이름).
LANGUAGE_QUERIES = {
    "python": ("compute traced", "pkg/service.py::compute"),
    "c": ("run clamp item size", "c/main.c::run"),
    "cpp": ("total shape area", "cpp/main.cpp::total"),
    "java": ("Main Limits MAX", "java/src/com/acme/app/Main.java::Main"),
    "javascript": ("run twice", "javascript/main.js::run"),
}


class CountingCounter(FixedTokenCounter):
    """
    클래스 이름: CountingCounter
    기능: [fixture] UTF-8 바이트 수를 토큰으로 세고 호출한 텍스트를 기록한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self) -> None:
        """
        함수 이름: __init__()
        기능: 호출 기록을 비운다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.calls: list[str] = []

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 호출을 기록하고 고정 규칙으로 센다.
        인자: text -> 본문, model_id -> 모델
        반환값: TokenCount
        작성 날짜: 2026/11/05
        """
        self.calls.append(text)
        return super().count(text, model_id)


@pytest.fixture
def setup(tmp_path: Path) -> tuple[R0SymbolService, Path, CountingCounter]:
    """
    함수 이름: setup()
    기능: 다섯 언어 혼합 프로젝트를 색인하고 검색 서비스를 만든다.
    인자: tmp_path -> pytest 임시 폴더
    반환값: (서비스, 작업 공간 루트, 계수기)
    작성 날짜: 2026/11/05
    """
    root = tmp_path / "workspace"
    for language, files in LANGUAGE_PROJECTS.items():
        # Python 절대 import(pkg.helpers)가 루트 기준으로 풀리도록 Python만 루트에 둔다.
        write_project(root if language == "python" else root / language, files)
    write_project(root, SHARED_NAME_FILES)
    index = SymbolIndexService(RevisionStore(tmp_path / "data"))
    index.build(WORKSPACE_ID, root)
    counter = CountingCounter()
    roots = StaticWorkspaceRoots({WORKSPACE_ID: root})
    return R0SymbolService(index, counter, roots), root, counter


def _search(service: R0SymbolService, query: str, **extra: Any) -> dict[str, Any]:
    """
    함수 이름: _search()
    기능: 기본 작업 공간으로 검색한다.
    인자: service -> 서비스, query -> 검색어, extra -> 추가 요청 필드
    반환값: SymbolSearchResponse 값
    작성 날짜: 2026/11/05
    """
    return service.search({"workspace_id": WORKSPACE_ID, "query": query, **extra})


def _with_references(response: dict[str, Any], primary: str) -> dict[str, Any]:
    """
    함수 이름: _with_references()
    기능: 같은 시작 심볼의 후보 중 참조를 포함한 깊이 1 이상 bundle 후보를 고른다.
    인자: response -> 검색 응답, primary -> 경로::이름
    반환값: SymbolCandidate 값
    작성 날짜: 2026/11/05
    """
    wanted = symbol_id("memory://symbol/" + primary)
    return next(
        candidate
        for candidate in response["candidates"]
        if candidate["primary"]["symbol_id"] == wanted and candidate["depth"] >= 1
    )


def _bundle(service: R0SymbolService, candidate: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """
    함수 이름: _bundle()
    기능: 후보의 원문 묶음을 큰 예산으로 읽는다.
    인자: service -> 서비스, candidate -> 검색 후보, extra -> 예산 덮어쓰기
    반환값: SymbolBundle 값
    작성 날짜: 2026/11/05
    """
    request = {
        "workspace_id": WORKSPACE_ID,
        "candidate_id": candidate["candidate_id"],
        "index_revision": candidate["index_revision"],
        "max_tokens": 100_000,
    }
    return service.read_bundle(request | extra)


@pytest.mark.parametrize("language", sorted(LANGUAGE_QUERIES))
def test_identifier_search_per_language(setup, contract_check, language: str) -> None:
    """
    함수 이름: test_identifier_search_per_language()
    기능: 다섯 언어 각각의 식별자 검색 1위와 묶음 원문·출처가 계약과 디스크에 맞는지 확인한다.
    인자: setup -> 서비스 묶음, contract_check -> 계약 검사, language -> 언어
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, root, _ = setup
    query, expected = LANGUAGE_QUERIES[language]
    response = _search(service, query)
    assert contract_check(SEARCH_SCHEMA, response) == []
    first = response["candidates"][0]
    # R0와 같이 단일 원문(atomic)이 1위, 같은 심볼의 참조 bundle이 그 뒤에 온다.
    assert first["primary"]["symbol_id"] == symbol_id("memory://symbol/" + expected)
    assert first["depth"] == 0 and 0 < first["score"] <= 1
    top = _with_references(response, expected)
    assert top["score"] <= first["score"]
    assert "source" not in json.dumps(response) and str(root) not in json.dumps(response)
    bundle = _bundle(service, top)
    assert contract_check(BUNDLE_SCHEMA, bundle) == []
    assert len(bundle["fragments"]) == len(top["symbol_ids"]) > 1
    for fragment in bundle["fragments"]:
        content = (root / fragment["provenance"]["relative_path"]).read_bytes().decode()
        assert fragment["content"] in content
        start = content.index(fragment["content"])
        assert content[:start].count("\n") + 1 == fragment["start_line"]


def test_python_function_helper_constant_bundle(setup) -> None:
    """
    함수 이름: test_python_function_helper_constant_bundle()
    기능: compute→scale→RATE와 decorator가 BFS 순서로 묶이고 동적 호출이 미해결로 보이는지 확인한다.
    인자: setup -> 서비스 묶음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, _ = setup
    top = _with_references(_search(service, "compute"), "pkg/service.py::compute")
    bundle = _bundle(service, top)
    contents = [fragment["content"] for fragment in bundle["fragments"]]
    assert contents[0].startswith("@traced\ndef compute")
    assert contents[1:] == [
        "def scale(x):\n    return x * R",
        "def traced(fn):\n    return fn",
        "RATE = 3",
    ]
    assert {item["name"] for item in bundle["unresolved_references"]} >= {"getattr()"}
    assert bundle["token_count"]["count_mode"] == "provider_estimate"


def test_cycle_and_partial_duplicates_are_removed(setup) -> None:
    """
    함수 이름: test_cycle_and_partial_duplicates_are_removed()
    기능: 순환 ping↔pong의 두 bundle은 같은 원문 범위이므로 하나만, 이미 덮인 atomic은 빼는지 확인한다.
    인자: setup -> 서비스 묶음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, _ = setup
    ping = symbol_id("memory://symbol/cycle/a.py::ping")
    pong = symbol_id("memory://symbol/cycle/b.py::pong")
    candidates = _search(service, "ping pong", page={"limit": 100})["candidates"]
    # 두 atomic이 먼저 오면 ping·pong bundle은 이미 덮인 범위라 둘 다 빠진다.
    cycle = [c for c in candidates if {ping, pong} & set(c["symbol_ids"])]
    assert [c["symbol_ids"] for c in cycle] == [[ping], [pong]]
    seen: set[str] = set()
    for candidate in candidates:
        assert not set(candidate["symbol_ids"]) <= seen
        seen.update(candidate["symbol_ids"])
    looped = {
        "candidate_id": candidate_id("memory://symbol/cycle/a.py::ping"),
        "index_revision": candidates[0]["index_revision"],
    }
    fragments = _bundle(service, looped)["fragments"]
    assert [fragment["symbol_id"] for fragment in fragments] == [ping, pong]


@pytest.mark.parametrize(
    ("query", "hint"),
    [
        ("설정 값을 계산하는 함수는 무엇인가요?", "try_identifier_or_file_name"),
        ("zebra quantum", "try_identifier_or_file_name"),
    ],
)
def test_no_match_is_http_200_body(setup, contract_check, query: str, hint: str) -> None:
    """
    함수 이름: test_no_match_is_http_200_body()
    기능: 한국어만 있는 질문과 모든 점수가 0인 질문이 빈 후보와 NO_MATCH 안내를 돌려주는지 확인한다.
    인자: setup -> 서비스 묶음, contract_check -> 계약 검사, query -> 검색어, hint -> 기대 안내
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, counter = setup
    response = _search(service, query)
    assert contract_check(SEARCH_SCHEMA, response) == []
    assert response["candidates"] == [] and response["page"]["has_more"] is False
    assert response["no_match"] == {"reason_code": "NO_MATCH", "hint": hint}
    assert counter.calls == []


def test_large_bundle_omits_explicitly(setup, contract_check) -> None:
    """
    함수 이름: test_large_bundle_omits_explicitly()
    기능: 토큰 예산이 작으면 시작 원문만 넣고 나머지를 budget_exceeded로, 바이트 상한보다 큰
        시작 원문은 too_large로 알리며 이어 붙인 전체 토큰이 상한을 넘지 않는지 확인한다.
    인자: setup -> 서비스 묶음, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, _ = setup
    top = _with_references(_search(service, "compute"), "pkg/service.py::compute")
    full = _bundle(service, top)
    first, second = (len(f["content"].encode()) for f in full["fragments"][:2])
    tight = _bundle(service, top, max_tokens=first + second)
    assert contract_check(BUNDLE_SCHEMA, tight) == []
    assert len(tight["fragments"]) == 1 and tight["token_count"]["token_count"] <= first + second
    assert {o["reason"] for o in tight["omissions"]} == {"budget_exceeded"}
    assert len(tight["omissions"]) == len(top["symbol_ids"]) - 1
    tiny = _bundle(service, top, max_bytes=10)
    assert contract_check(BUNDLE_SCHEMA, tiny) == []
    assert tiny["fragments"] == [] and tiny["token_count"] == {
        "token_count": 0,
        "count_mode": "exact",
    }
    assert tiny["omissions"][0] == {"symbol_id": top["symbol_ids"][0], "reason": "too_large"}
    assert {o["reason"] for o in tiny["omissions"][1:]} == {"budget_exceeded"}


def test_stale_sources_are_not_returned(setup) -> None:
    """
    함수 이름: test_stale_sources_are_not_returned()
    기능: 참조 파일이 바뀌면 stale_revision 누락, 시작 파일이 바뀌면 SOURCE_CHANGED, 재색인 뒤
        이전 revision·cursor 요청도 SOURCE_CHANGED인지 확인한다.
    인자: setup -> 서비스 묶음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, root, _ = setup
    first_page = _search(service, "run", page={"limit": 1})
    top = _with_references(_search(service, "compute"), "pkg/service.py::compute")
    (root / "pkg/constants.py").write_text("RATE = 30\n")
    partial = _bundle(service, top)
    rate = symbol_id("memory://symbol/pkg/constants.py::RATE")
    assert {"symbol_id": rate, "reason": "stale_revision"} in partial["omissions"]
    assert all("RATE" not in fragment["content"] for fragment in partial["fragments"])
    (root / "pkg/service.py").write_text("def compute():\n    return 0\n")
    with pytest.raises(ServiceError) as changed:
        _bundle(service, top)
    assert changed.value.code is ErrorCode.SOURCE_CHANGED

    service.index.build(WORKSPACE_ID, root)
    with pytest.raises(ServiceError) as superseded:
        _bundle(service, top)
    assert superseded.value.code is ErrorCode.SOURCE_CHANGED
    with pytest.raises(ServiceError):
        _search(service, "compute", index_revision=1)
    with pytest.raises(ServiceError) as cursor:
        _search(service, "run", page={"limit": 1, "cursor": first_page["page"]["next_cursor"]})
    assert cursor.value.code is ErrorCode.SOURCE_CHANGED
    fresh = _search(service, "compute")["candidates"][0]
    assert fresh["index_revision"] == 2 and _bundle(service, fresh)["fragments"]


def test_pagination_cursor_and_caps(setup, contract_check) -> None:
    """
    함수 이름: test_pagination_cursor_and_caps()
    기능: 페이지 크기·cursor 이어 읽기·다른 검색어 cursor 거부·후보 100개 상한을 확인한다.
    인자: setup -> 서비스 묶음, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, _ = setup
    first = _search(service, "helper run", page={"limit": 1})
    assert contract_check(SEARCH_SCHEMA, first) == []
    assert len(first["candidates"]) == 1 and first["page"]["has_more"] is True
    cursor = first["page"]["next_cursor"]
    second = _search(service, "helper run", page={"limit": 1, "cursor": cursor})
    assert second["candidates"][0]["candidate_id"] != first["candidates"][0]["candidate_id"]
    everything = _search(service, "helper run", page={"limit": 100})
    assert everything["candidates"][1] == second["candidates"][0]
    assert len(everything["candidates"]) <= 100 and everything["page"]["has_more"] is False
    with pytest.raises(ServiceError) as wrong:
        _search(service, "other words", page={"limit": 1, "cursor": cursor})
    assert wrong.value.code is ErrorCode.VALIDATION_FAILED


def test_not_ready_and_unsupported_only(tmp_path: Path, contract_check) -> None:
    """
    함수 이름: test_not_ready_and_unsupported_only()
    기능: 색인이 없으면 INDEX_NOT_READY, 벡터 준비 전 기록은 index_not_ready 안내,
        미지원 언어만 있으면 unsupported_language_only 안내를 확인한다.
    인자: tmp_path -> 임시 폴더, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    root = tmp_path / "workspace"
    write_project(root, {"main.ts": "export const typed = 1;\n"})
    store = RevisionStore(tmp_path / "data")
    index = SymbolIndexService(store)
    service = R0SymbolService(index, CountingCounter(), StaticWorkspaceRoots({WORKSPACE_ID: root}))
    with pytest.raises(ServiceError) as missing:
        _search(service, "typed")
    assert missing.value.code is ErrorCode.INDEX_NOT_READY
    index.build(WORKSPACE_ID, root)
    unsupported = _search(service, "typed")
    assert contract_check(SEARCH_SCHEMA, unsupported) == []
    assert unsupported["no_match"]["hint"] == "unsupported_language_only"

    record = store.load(WORKSPACE_ID, 1)
    record["retrieval"] = {"state": "pending", "owner_task": "3.4"}
    record["index_revision"] = 2
    store.publish(record)
    pending = _search(service, "typed")
    assert pending["index_revision"] == 2
    assert pending["no_match"]["hint"] == "index_not_ready"


def test_no_llm_selector_or_summary(setup) -> None:
    """
    함수 이름: test_no_llm_selector_or_summary()
    기능: 검색·묶음 경로의 외부 호출이 주입된 TokenCounter.count뿐이고, symbols 패키지가
        모델 SDK·HTTP 클라이언트를 import하지 않는지 확인한다(사전 요약·후보 선택 LLM 호출 0회).
    인자: setup -> 서비스 묶음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service, _, counter = setup
    top = _with_references(_search(service, "compute"), "pkg/service.py::compute")
    _bundle(service, top)
    assert counter.calls and all(isinstance(text, str) for text in counter.calls)
    package = Path(__file__).resolve().parents[2] / "src" / "securecode_context" / "symbols"
    banned = {"anthropic", "httpx", "openai", "requests", "urllib.request"}
    for source in package.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        roots = {module.split(".")[0] for module in modules}
        assert not (modules | roots) & banned, source.name
        names = {node.name.lower() for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert not any("summar" in name or "embed" in name for name in names), source.name
