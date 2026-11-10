"""context.select(4.8): 후보 수집 → 해석 → 예산 → 선택·읽기 → ContextPreviewPlan.

후보는 사용자 명시 선택, current_task 포인터, R0 검색 결과뿐이다. 요약·전체 파일 대체·임베딩은 없다.
"""

from dataclasses import dataclass, field, replace
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.context.budget import CostInput, count_costs
from securecode_context.context.models import (
    Candidate,
    SelectorLimits,
    Span,
    Wire,
)
from securecode_context.context.pdf_resolver import PdfResolver
from securecode_context.context.plan_wire import plan_wire
from securecode_context.context.pointer_resolvers import RuntimeResolver, SourceResolver
from securecode_context.context.policy import relevant_r0, run_create_error
from securecode_context.context.reader import RequestReader, Resolver, pointer_candidate_id
from securecode_context.context.selector import select
from securecode_context.context.symbol_resolver import SymbolResolver
from securecode_context.pdf.pages import PdfPages
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.symbols.symbol_service import R0SymbolService


@dataclass(frozen=True)
class SelectRequest:
    """
    클래스 이름: SelectRequest
    기능: 검증된 ContextSelectRequest. current_task_refs는 최신 순서다.
    작성 날짜: 2026/11/10
    """

    workspace_id: str
    session_id: str
    index_revision: int
    prompt: str
    context_refs: list[Wire]
    costs: CostInput
    current_task_refs: list[Wire] = field(default_factory=list)
    history_refs: list[Wire] = field(default_factory=list)


class ContextSelectService:
    """
    클래스 이름: ContextSelectService
    기능: 앱 단위 Selector. 요청마다 범위에 묶인 resolver를 만들어 계획을 만든다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        sources: SourceAdapter,
        runtime: tuple[RuntimeStore, RuntimeReader],
        counter: TokenCounter,
        symbols: R0SymbolService | None = None,
        limits: SelectorLimits | None = None,
        pdf: PdfPages | None = None,
    ) -> None:
        """
        함수 이름: __init__()
        기능: Source·Runtime·R0 연결과 계수기, 상한을 저장한다.
        인자: sources -> SourceAdapter, runtime -> (저장소, reader), counter -> TokenCounter,
            symbols -> R0 서비스(없으면 R0 후보 없음), limits -> 정책 상한,
            pdf -> 4.9 PDF 페이지 reader(없으면 PDF 후보는 no_match)
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._sources = sources
        self._runtime = runtime
        self._counter = counter
        self._symbols = symbols
        self.limits = limits or SelectorLimits()
        self._pdf = pdf

    def _reader(self, request: SelectRequest) -> RequestReader:
        """
        함수 이름: _reader()
        기능: 요청 범위에 묶인 resolver 묶음을 만든다.
        인자: request -> 요청
        반환값: RequestReader
        작성 날짜: 2026/11/10
        """
        pdf = PdfResolver(self._pdf, request.workspace_id) if self._pdf is not None else None
        resolvers: dict[str, Resolver] = {
            "source": SourceResolver(self._sources, request.workspace_id, pdf),
            "runtime": RuntimeResolver(*self._runtime, request.workspace_id, request.session_id),
        }
        if self._symbols is not None:
            resolvers["symbol"] = SymbolResolver(self._symbols, self._counter, request.workspace_id)
        return RequestReader(resolvers, self._counter)

    def _candidates(self, request: SelectRequest, reader: RequestReader) -> list[Candidate]:
        """
        함수 이름: _candidates()
        기능: 명시·current_task·R0 후보를 상한 개수까지 만들고 해석한다.
        인자: request -> 요청, reader -> resolver 묶음
        반환값: 해석한 후보 목록
        작성 날짜: 2026/11/10
        """
        raw: list[Candidate] = []
        caps = self.limits.max_candidates
        for position, ref in enumerate(request.context_refs[: caps["explicit"]]):
            cid = ref["candidate_id"] if ref["kind"] == "symbol" else pointer_candidate_id(ref)
            raw.append(Candidate(cid, "explicit", ref["kind"], ref, 1.0, position, 0))
        for rank, ref in enumerate(request.current_task_refs[: caps["current_task"]]):
            cid = pointer_candidate_id(ref)
            raw.append(Candidate(cid, "current_task", ref["kind"], ref, 1.0, rank, 0))
        if self._symbols is not None and caps["r0"] > 0:
            symbols = reader.resolver("symbol")
            assert isinstance(symbols, SymbolResolver)
            items = _r0_items(symbols, request, caps["r0"])
            keep = relevant_r0([float(item["score"]) for item in items])
            for item in (item for item, kept in zip(items, keep, strict=True) if kept):
                ref = {
                    "kind": "symbol",
                    "candidate_id": item["candidate_id"],
                    "index_revision": item["index_revision"],
                }
                tokens = item["estimated_tokens"]["token_count"]
                raw.append(
                    Candidate(item["candidate_id"], "r0", "symbol", ref, item["score"], 0, tokens)
                )
        return [self._inspect(candidate, reader) for candidate in _unique(raw)]

    def _inspect(self, candidate: Candidate, reader: RequestReader) -> Candidate:
        """
        함수 이름: _inspect()
        기능: 종류별 resolver로 해석한다. 심볼 색인이 없으면 stale로 둔다.
        인자: candidate -> 후보, reader -> resolver 묶음
        반환값: 해석한 후보
        작성 날짜: 2026/11/10
        """
        try:
            return reader.resolver(candidate.kind).inspect(candidate)
        except ServiceError as error:
            if error.code != ErrorCode.INDEX_NOT_READY:
                raise
            return replace(candidate, status="stale")

    def _history(self, request: SelectRequest, reader: RequestReader) -> list[Span]:
        """
        함수 이름: _history()
        기능: 이력에 원문이 실린 ref를 같은 방법으로 해석해 구간 목록을 만든다.
        인자: request -> 요청, reader -> resolver 묶음
        반환값: 해석에 성공한 이력 구간
        작성 날짜: 2026/11/10
        """
        spans: list[Span] = []
        for ref in request.history_refs:
            cid = ref["candidate_id"] if ref["kind"] == "symbol" else pointer_candidate_id(ref)
            resolved = self._inspect(
                Candidate(cid, "explicit", ref["kind"], ref, 0.0, 0, 0), reader
            )
            if resolved.status == "ok" and resolved.span is not None:
                spans.append(resolved.span)
        return spans

    def plan(self, request: SelectRequest) -> dict[str, Any]:
        """
        함수 이름: plan()
        기능: 고정 비용을 세고(음수면 BUDGET_EXCEEDED) 후보를 선택·읽어 계획과 run 생성 오류를 돌려준다.
        인자: request -> 검증된 요청
        반환값: {"plan": ContextPreviewPlan, "run_create_error": ErrorCode|None}
        작성 날짜: 2026/11/10
        """
        costs = count_costs(self._counter, request.costs)
        reader = self._reader(request)
        candidates = self._candidates(request, reader)
        history = self._history(request, reader)
        selection = select(candidates, history, costs.base_budget(), self.limits, reader)
        return {
            "schema_version": "1",
            "plan": plan_wire(selection, costs, request.index_revision),
            "run_create_error": run_create_error(selection.order, selection.omissions),
        }


def _r0_items(symbols: SymbolResolver, request: SelectRequest, limit: int) -> list[dict[str, Any]]:
    """
    함수 이름: _r0_items()
    기능: R0 후보를 찾는다. 색인이 아직 없거나(INDEX_NOT_READY·NOT_FOUND) 요청 revision이 현재와
        다르면(SOURCE_CHANGED) R0 후보 없이 계획한다. 색인 상태는 host가 따로 보여 준다.
    인자: symbols -> R0 resolver, request -> 요청, limit -> 최대 후보 수
    반환값: SymbolCandidate 목록
    작성 날짜: 2026/11/10
    """
    try:
        return symbols.search(request.prompt, request.index_revision, limit)
    except ServiceError as error:
        skip = (ErrorCode.INDEX_NOT_READY, ErrorCode.NOT_FOUND, ErrorCode.SOURCE_CHANGED)
        if error.code in skip:
            return []
        raise


def _unique(candidates: list[Candidate]) -> list[Candidate]:
    """
    함수 이름: _unique()
    기능: 같은 candidate_id는 앞(우선순위가 높은 origin)의 것만 남긴다.
    인자: candidates -> 후보
    반환값: 중복 ID를 뺀 후보
    작성 날짜: 2026/11/10
    """
    seen: set[str] = set()
    kept: list[Candidate] = []
    for candidate in candidates:
        if candidate.candidate_id not in seen:
            seen.add(candidate.candidate_id)
            kept.append(candidate)
    return kept
