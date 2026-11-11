"""R0 Symbol Bundle 후보 resolver(4.8). 후보는 R0 TF-IDF 검색 결과, 원문은 3.4 read_bundle로만 읽는다.

심볼 후보의 대상은 시작 심볼 파일의 (경로, 파일 SHA-256)이고 구간은 색인한 시작 심볼 바이트 범위다.
그래서 같은 파일의 Source 포인터 구간과 중복을 비교할 수 있다. 심볼 묶음은 나누지 않는다.
"""

from dataclasses import replace
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.context.models import Candidate, Material, Span
from securecode_context.symbols.bundle.wire import symbol_location
from securecode_context.symbols.graph import SourceNode
from securecode_context.symbols.symbol_service import R0SymbolService

MAX_BUNDLE_READ_BYTES = 16 * 1024
FRAGMENT_SEPARATOR = "\n\n"
# 묶음 일부가 빠진 이유 중 이 값들은 "끝까지 넣지 못함"이다.
_INCOMPLETE = {"budget_exceeded", "too_large"}


class SymbolResolver:
    """
    클래스 이름: SymbolResolver
    기능: workspace 하나의 R0 후보를 만들고(r0) 명시·자동 심볼 후보를 해석·읽는다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, service: R0SymbolService, counter: TokenCounter, workspace_id: str) -> None:
        """
        함수 이름: __init__()
        기능: R0 서비스·계수기·범위를 저장한다.
        인자: service -> R0SymbolService, counter -> TokenCounter, workspace_id -> 범위
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._service = service
        self._counter = counter
        self._workspace_id = workspace_id

    def search(self, prompt: str, index_revision: int, limit: int) -> list[dict[str, Any]]:
        """
        함수 이름: search()
        기능: 프롬프트로 R0 후보 메타데이터(원문 없음)를 limit개까지 가져온다. 무결과면 빈 목록이다.
        인자: prompt -> 사용자 요청, index_revision -> 요청 revision, limit -> 최대 개수
        반환값: SymbolCandidate 사전 목록
        작성 날짜: 2026/11/10
        """
        request = {
            "workspace_id": self._workspace_id,
            "query": prompt[:512],
            "index_revision": index_revision,
            "page": {"limit": limit},
        }
        response = self._service.search(request)
        return list(response.get("candidates") or [])

    def _nodes(self, candidate_id: str, index_revision: int) -> list[SourceNode]:
        """
        함수 이름: _nodes()
        기능: 요청 revision이 현재 ready revision인지 확인하고 후보의 시작 심볼 노드를 찾는다.
        인자: candidate_id -> CandidateId, index_revision -> 요청 revision
        반환값: SourceNode 사전
        작성 날짜: 2026/11/10
        """
        index = self._service.index
        record, prepared = index.prepared(self._workspace_id)
        index.require_revision(self._workspace_id, index_revision)
        if prepared is None or record["index_revision"] != index_revision:
            raise ServiceError(ErrorCode.INDEX_NOT_READY, "색인이 바뀌었습니다.")
        raw_id = prepared.raw_by_public_id.get(candidate_id)
        if raw_id is None:
            raise ServiceError(ErrorCode.NOT_FOUND, "후보를 찾을 수 없습니다.")
        return [record["nodes"][member] for member in prepared.infos[raw_id].members]

    def inspect(self, candidate: Candidate) -> Candidate:
        """
        함수 이름: inspect()
        기능: revision을 확인하고 시작 심볼의 파일·바이트 구간을 대상 구간으로 정한다.
        인자: candidate -> 심볼 후보
        반환값: 상태와 구간을 채운 후보
        작성 날짜: 2026/11/10
        """
        ref = candidate.ref
        try:
            nodes = self._nodes(ref["candidate_id"], ref["index_revision"])
            node = nodes[0]
        except ServiceError as error:
            if error.code in (ErrorCode.INDEX_NOT_READY, ErrorCode.SOURCE_CHANGED):
                return replace(candidate, status="stale")
            if error.code == ErrorCode.TOKENIZER_UNAVAILABLE:
                raise
            return replace(candidate, status="no_match")
        key = ("file", node["path"], node["content_sha256"])
        span = Span(key, node["start_byte"], node["end_byte"])
        if span.end <= span.start:
            return replace(candidate, status="no_match")
        covered = tuple(
            Span(
                ("file", member["path"], member["content_sha256"]),
                member["start_byte"],
                member["end_byte"],
            )
            for member in nodes
        )
        return replace(candidate, span=span, handle=symbol_location(node), covered_spans=covered)

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: read_bundle로 묶음을 상한 안에서 읽고 이어 붙인 본문을 다시 센다.
            일부가 예산·크기로 빠졌으면 complete=False(나누지 않으므로 over_budget)다.
        인자: candidate -> 심볼 후보, span -> 대상 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        ref = candidate.ref
        nodes = self._nodes(ref["candidate_id"], ref["index_revision"])
        selected = {
            symbol_location(node)["symbol_id"]
            for node in nodes
            if Span(
                ("file", node["path"], node["content_sha256"]), node["start_byte"], node["end_byte"]
            )
            in candidate.covered_spans
        }
        deduplicated = len(selected) < len(nodes)
        bundle = self._service.read_bundle(
            {
                "workspace_id": self._workspace_id,
                "candidate_id": ref["candidate_id"],
                "index_revision": ref["index_revision"],
                "max_tokens": 32768 if deduplicated else max_tokens,
                "max_bytes": MAX_BUNDLE_READ_BYTES,
            }
        )
        fragments = [
            fragment for fragment in bundle["fragments"] if fragment["symbol_id"] in selected
        ]
        content = FRAGMENT_SEPARATOR.join(
            f"# {fragment['provenance']['relative_path']}:{fragment['start_line']}-{fragment['end_line']}\n"
            + fragment["content"]
            for fragment in fragments
        )
        included = {fragment["symbol_id"] for fragment in fragments}
        locations = [symbol_location(node) for node in nodes]
        locations = [location for location in locations if location["symbol_id"] in included]
        omitted = {omission["reason"] for omission in bundle["omissions"]}
        complete = bool(fragments) and not omitted & _INCOMPLETE
        counted = self._counter.count(content) if content else None
        tokens = counted.token_count if counted is not None else 0
        if len(content.encode("utf-8")) > MAX_BUNDLE_READ_BYTES or tokens > max_tokens:
            complete = False
        return Material(
            content=content if complete else "",
            token_count=tokens if complete else 0,
            count_mode=counted.count_mode.value if counted is not None else "exact",
            span=span,
            citation={
                "ref": dict(ref),
                "location": locations[0] if locations else candidate.handle,
                "related_locations": locations[1:],
            },
            complete=complete,
        )
