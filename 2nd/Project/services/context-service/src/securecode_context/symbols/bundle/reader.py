"""후보 하나의 원문 fragment를 R0 pack 순서로 토큰·바이트 예산 안에서 고른다."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens.counter import TokenCounter

from ..graph import SourceNode
from ..index import VerifiedSymbol
from ..public_ids import candidate_id, symbol_id
from ..retrieval import CandidateInfo
from .wire import MAX_LISTED, unresolved_references

MAX_BUNDLE_BYTES = 32 * 1024
MAX_FRAGMENT_CHARS = 32768
SEPARATOR = "\n\n"


@dataclass(frozen=True)
class BundleBudget:
    """
    클래스 이름: BundleBudget
    기능: 요청의 토큰 상한과 원문 UTF-8 바이트 상한(최대 32 KiB)을 묶는다.
    작성 날짜: 2026/11/05
    """

    max_tokens: int
    max_bytes: int = MAX_BUNDLE_BYTES


@dataclass
class _Selection:
    """
    클래스 이름: _Selection
    기능: 고른 fragment와 누락 사유, 사용한 바이트·토큰 합을 모은다.
    작성 날짜: 2026/11/05
    """

    fragments: list[dict[str, Any]]
    contents: list[str]
    included: list[SourceNode]
    omissions: list[dict[str, str]]
    used_bytes: int = 0
    used_tokens: int = 0

    def omit(self, uri: str, reason: str) -> None:
        """
        함수 이름: omit()
        기능: 누락 심볼을 최대 64개까지 기록한다.
        인자: uri -> 내부 심볼 ID, reason -> 계약 누락 사유
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        if len(self.omissions) < MAX_LISTED:
            self.omissions.append({"symbol_id": symbol_id(uri), "reason": reason})


def _fragment(node: SourceNode, verified: VerifiedSymbol) -> dict[str, Any]:
    """
    함수 이름: _fragment()
    기능: 색인한 바이트 범위의 원문과 다시 확인한 출처를 fragment로 만든다.
    인자: node -> 심볼, verified -> 디스크 해시를 확인한 결과
    반환값: SymbolFragment 값
    작성 날짜: 2026/11/05
    """
    return {
        "symbol_id": symbol_id(node["id"]),
        "start_line": node["start"],
        "end_line": node["end"],
        "content": node["source"],
        "provenance": verified.provenance,
    }


def _select(
    info: CandidateInfo,
    nodes: Mapping[str, SourceNode],
    verified: Mapping[str, VerifiedSymbol | None],
    counter: TokenCounter,
    budget: BundleBudget,
) -> _Selection:
    """
    함수 이름: _select()
    기능: 시작 심볼부터 BFS 순서로 넣고, 넘치는 심볼은 건너뛰며 누락으로 기록한다.
        시작 심볼이 예산을 넘으면 참조도 넣지 않는다. 시작 심볼 파일이 바뀌었으면
        SOURCE_CHANGED, 참조 심볼 파일이 바뀌었으면 stale_revision 누락이다.
    인자: info -> 후보, nodes -> 그래프, verified -> 재확인 결과, counter -> TokenCounter,
        budget -> 예산
    반환값: _Selection
    작성 날짜: 2026/11/05
    """
    selection = _Selection([], [], [], [])
    for uri in info.members:
        if uri != info.primary and not selection.included:
            # 시작 원문을 넣지 못한 묶음은 참조만 보내지 않는다(atomic 후보나 더 큰 예산 사용).
            selection.omit(uri, "budget_exceeded")
            continue
        node, checked = nodes[uri], verified[uri]
        if checked is None:
            if uri == info.primary:
                raise ServiceError(
                    ErrorCode.SOURCE_CHANGED,
                    "원본 파일이 색인 이후 바뀌었습니다. 다시 색인하세요.",
                    {"reason": "content_changed"},
                )
            selection.omit(uri, "stale_revision")
            continue
        content = node["source"]
        size = len(content.encode()) + (len(SEPARATOR) if selection.contents else 0)
        if len(content) > MAX_FRAGMENT_CHARS or len(content.encode()) > budget.max_bytes:
            selection.omit(uri, "too_large")
            continue
        if selection.used_bytes + size > budget.max_bytes:
            selection.omit(uri, "budget_exceeded")
            continue
        tokens = counter.count(content).token_count
        if selection.used_tokens + tokens > budget.max_tokens:
            selection.omit(uri, "budget_exceeded" if uri != info.primary else "too_large")
            continue
        selection.fragments.append(_fragment(node, checked))
        selection.contents.append(content)
        selection.included.append(node)
        selection.used_bytes += size
        selection.used_tokens += tokens
    return selection


def assemble_bundle(
    info: CandidateInfo,
    nodes: Mapping[str, SourceNode],
    verified: Mapping[str, VerifiedSymbol | None],
    counter: TokenCounter,
    budget: BundleBudget,
    index_revision: int,
) -> dict[str, Any]:
    """
    함수 이름: assemble_bundle()
    기능: 고른 원문을 이어 붙인 전체를 다시 계수하고, 상한을 넘으면 뒤 fragment부터 뺀다.
        깊이 3·크기 상한으로 후보에 들어가지 못한 참조도 누락으로 알린다.
    인자: info -> 후보, nodes -> 그래프, verified -> 재확인 결과, counter -> TokenCounter,
        budget -> 예산, index_revision -> revision
    반환값: SymbolBundle 값
    작성 날짜: 2026/11/05
    """
    selection = _select(info, nodes, verified, counter, budget)
    token_total: dict[str, Any] = {"token_count": 0, "count_mode": "exact"}
    while selection.contents:
        counted = counter.count(SEPARATOR.join(selection.contents))
        token_total = {"token_count": counted.token_count, "count_mode": counted.count_mode.value}
        if counted.token_count <= budget.max_tokens:
            break
        selection.contents.pop()
        selection.fragments.pop()
        selection.omit(selection.included.pop()["id"], "budget_exceeded")
        token_total = {"token_count": 0, "count_mode": "exact"}
    for uri, reason in info.boundary:
        selection.omit(uri, reason)
    return {
        "schema_version": "1",
        "candidate_id": candidate_id(info.raw_id),
        "index_revision": index_revision,
        "fragments": selection.fragments,
        "omissions": selection.omissions,
        "unresolved_references": unresolved_references(selection.included),
        "token_count": token_total,
    }
