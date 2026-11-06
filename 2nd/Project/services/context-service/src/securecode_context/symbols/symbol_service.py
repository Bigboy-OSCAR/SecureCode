"""R0 SymbolService 구현: TF-IDF 후보 검색과 예산 안 Symbol Bundle 읽기."""

import json
from collections.abc import Mapping
from typing import Any, cast

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter

from .bundle import MAX_BUNDLE_BYTES, BundleBudget, assemble_bundle, candidate_wire
from .index import IndexRevisionRecord, SymbolIndexService
from .ports import WorkspaceRootPort
from .retrieval import (
    RankedCandidate,
    decode_cursor,
    encode_cursor,
    has_query_tokens,
    rank_candidates,
)

DEFAULT_PAGE_LIMIT = 20
MAX_SEARCH_RESPONSE_BYTES = 64 * 1024
_SEPARATOR = "\n\n"


def _integer(request: Mapping[str, object], key: str, default: int | None = None) -> int:
    """
    함수 이름: _integer()
    기능: 검증된 요청에서 정수 필드를 꺼낸다(bool 제외).
    인자: request -> 요청, key -> 필드 이름, default -> 없을 때 값
    반환값: 정수
    작성 날짜: 2026/11/05
    """
    value = request.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, f"{key} 값이 올바르지 않습니다.")
    return value


def _no_match(workspace_id: str, index_revision: int, limit: int, hint: str) -> dict[str, Any]:
    """
    함수 이름: _no_match()
    기능: 무결과를 HTTP 200 본문(빈 후보, NO_MATCH, 안내 hint)으로 만든다.
    인자: workspace_id -> 작업 공간, index_revision -> revision, limit -> 페이지 크기,
        hint -> try_identifier_or_file_name·index_not_ready·unsupported_language_only
    반환값: SymbolSearchResponse 값
    작성 날짜: 2026/11/05
    """
    return {
        "schema_version": "1",
        "workspace_id": workspace_id,
        "index_revision": index_revision,
        "candidates": [],
        "page": {"limit": limit, "next_cursor": None, "has_more": False},
        "no_match": {"reason_code": "NO_MATCH", "hint": hint},
    }


def _only_unsupported(record: IndexRevisionRecord) -> bool:
    """
    함수 이름: _only_unsupported()
    기능: 심볼이 하나도 없고 미지원 언어 파일만 진단에 있는지 확인한다.
    인자: record -> 현재 revision
    반환값: 미지원 언어만 있으면 True
    작성 날짜: 2026/11/05
    """
    reasons = {item["reason_code"] for item in record["diagnostics"]}
    return not record["nodes"] and "unsupported_language" in reasons


class R0SymbolService:
    """
    클래스 이름: R0SymbolService
    기능: ready revision의 TF-IDF로 후보를 찾고 원문 묶음을 예산 안에서 돌려준다. 후보에는
        원문을 넣지 않으며, 원문은 read_bundle에서 디스크 해시를 다시 확인한 뒤에만 반환한다.
        LLM 선택·요약·임베딩·번역 호출이 없고 토큰 계산은 주입된 TokenCounter만 쓴다.
    작성 날짜: 2026/11/05
    """

    def __init__(
        self, index: SymbolIndexService, counter: TokenCounter, roots: WorkspaceRootPort
    ) -> None:
        """
        함수 이름: __init__()
        기능: 색인 서비스·TokenCounter·작업 공간 루트 포트를 주입받는다.
        인자: index -> SymbolIndexService, counter -> TokenCounter, roots -> WorkspaceRootPort
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.index = index
        self.counter = counter
        self.roots = roots

    def search(self, request: Mapping[str, object]) -> dict[str, Any]:
        """
        함수 이름: search()
        기능: SymbolSearchRequest를 받아 점수가 0보다 큰 후보만 페이지로 돌려준다.
        인자: request -> 검증된 SymbolSearchRequest
        반환값: SymbolSearchResponse 값
        작성 날짜: 2026/11/05
        """
        workspace_id = str(request["workspace_id"])
        query = str(request["query"])
        page = cast(Mapping[str, object], request.get("page") or {})
        limit = min(_integer(page, "limit", DEFAULT_PAGE_LIMIT), 100)
        record, prepared = self.index.prepared(workspace_id)
        revision = record["index_revision"]
        if "index_revision" in request:
            self.index.require_revision(workspace_id, _integer(request, "index_revision"))
        cursor = page.get("cursor")
        offset = decode_cursor(str(cursor), revision, query) if cursor else 0
        if prepared is None:
            return _no_match(workspace_id, revision, limit, "index_not_ready")
        if _only_unsupported(record):
            return _no_match(workspace_id, revision, limit, "unsupported_language_only")
        ranked = rank_candidates(prepared.retriever, prepared.infos, query)
        if not has_query_tokens(query) or not ranked:
            return _no_match(workspace_id, revision, limit, "try_identifier_or_file_name")
        return self._page(workspace_id, record, ranked, query, offset, limit)

    def read_bundle(self, request: Mapping[str, object]) -> dict[str, Any]:
        """
        함수 이름: read_bundle()
        기능: SymbolBundleRequest의 후보를 revision·디스크 해시 확인 후 예산 안 원문으로 돌려준다.
        인자: request -> 검증된 SymbolBundleRequest
        반환값: SymbolBundle 값
        작성 날짜: 2026/11/05
        """
        workspace_id = str(request["workspace_id"])
        revision = _integer(request, "index_revision")
        max_tokens = _integer(request, "max_tokens")
        max_bytes = min(_integer(request, "max_bytes", MAX_BUNDLE_BYTES), MAX_BUNDLE_BYTES)
        if max_tokens < 1 or max_bytes < 1:
            raise ServiceError(ErrorCode.VALIDATION_FAILED, "예산 값이 올바르지 않습니다.")
        record, prepared = self.index.prepared(workspace_id)
        self.index.require_revision(workspace_id, revision)
        if prepared is None:
            raise ServiceError(ErrorCode.INDEX_NOT_READY, "검색 색인을 준비하는 중입니다.")
        raw_id = prepared.raw_by_public_id.get(str(request["candidate_id"]))
        if raw_id is None:
            raise ServiceError(ErrorCode.NOT_FOUND, "후보를 찾을 수 없습니다.")
        info = prepared.infos[raw_id]
        root = self.roots.root_for(workspace_id)
        verified = self.index.verified_symbols(workspace_id, root, revision, info.members)
        budget = BundleBudget(max_tokens, max_bytes)
        return assemble_bundle(info, record["nodes"], verified, self.counter, budget, revision)

    def _page(
        self,
        workspace_id: str,
        record: IndexRevisionRecord,
        ranked: list[RankedCandidate],
        query: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """
        함수 이름: _page()
        기능: 페이지 후보마다 묶음 원문의 토큰을 추정하고 응답 64 KiB 상한에서 멈춘다.
        인자: workspace_id -> 작업 공간, record -> revision, ranked -> 순위 후보,
            query -> 검색어(cursor 결속용), offset -> 시작 위치, limit -> 페이지 크기
        반환값: SymbolSearchResponse 값
        작성 날짜: 2026/11/05
        """
        revision = record["index_revision"]
        nodes = record["nodes"]
        items: list[dict[str, Any]] = []
        used_bytes = 0
        truncated = False
        for candidate in ranked[offset : offset + limit]:
            text = _SEPARATOR.join(nodes[uri]["source"] for uri in candidate.info.members)
            counted = self.counter.count(text)
            estimated = {"token_count": counted.token_count, "count_mode": counted.count_mode.value}
            item = candidate_wire(candidate, nodes[candidate.info.primary], revision, estimated)
            size = len(json.dumps(item, ensure_ascii=False).encode())
            if items and used_bytes + size > MAX_SEARCH_RESPONSE_BYTES:
                truncated = True
                break
            items.append(item)
            used_bytes += size
        next_offset = offset + len(items)
        has_more = next_offset < len(ranked)
        page: dict[str, Any] = {
            "limit": limit,
            "next_cursor": encode_cursor(revision, query, next_offset) if has_more else None,
            "has_more": has_more,
        }
        if truncated:
            page["truncated_by_bytes"] = True
        return {
            "schema_version": "1",
            "workspace_id": workspace_id,
            "index_revision": revision,
            "candidates": items,
            "page": page,
            "no_match": None,
        }
