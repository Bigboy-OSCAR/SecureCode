"""내부 심볼·후보를 계약 SymbolLocation·SymbolCandidate·UnresolvedReference 값으로 바꾼다."""

from typing import Any

from ..graph import SourceNode
from ..public_ids import candidate_id, symbol_id
from ..retrieval import RankedCandidate

MAX_LISTED = 64
_MAX_NAME_CHARS = 256


def symbol_location(node: SourceNode) -> dict[str, Any]:
    """
    함수 이름: symbol_location()
    기능: 심볼의 공개 ID·이름·종류·상대 경로·줄 범위·파일 해시를 만든다(절대 경로·원문 제외).
    인자: node -> 내부 심볼
    반환값: SymbolLocation 값
    작성 날짜: 2026/11/05
    """
    return {
        "symbol_id": symbol_id(node["id"]),
        "qualname": node["name"][:512],
        "kind": node["kind"],
        "relative_path": node["path"],
        "start_line": node["start"],
        "end_line": node["end"],
        "content_sha256": node["content_sha256"],
    }


def candidate_wire(
    ranked: RankedCandidate,
    node: SourceNode,
    index_revision: int,
    estimated_tokens: dict[str, Any],
) -> dict[str, Any]:
    """
    함수 이름: candidate_wire()
    기능: 원문 없이 후보 ID·구성 심볼 ID·점수·깊이·추정 토큰만 담는다.
    인자: ranked -> 순위 후보, node -> 시작 심볼, index_revision -> revision,
        estimated_tokens -> TokenCountSummary 값
    반환값: SymbolCandidate 값
    작성 날짜: 2026/11/05
    """
    info = ranked.info
    return {
        "candidate_id": candidate_id(info.raw_id),
        "symbol_ids": [symbol_id(uri) for uri in info.members[:MAX_LISTED]],
        "primary": symbol_location(node),
        "score": round(ranked.score, 6),
        "index_revision": index_revision,
        "depth": info.depth,
        "estimated_tokens": estimated_tokens,
    }


def _reason(name: str) -> str:
    """
    함수 이름: _reason()
    기능: 파서가 남긴 미해결 표기를 계약 사유로 분류한다.
    인자: name -> 참조 표기
    반환값: dynamic_import·dynamic_dispatch·not_found 중 하나
    작성 날짜: 2026/11/05
    """
    lowered = name.lower()
    if "import" in lowered or lowered.startswith("require"):
        return "dynamic_import"
    if any(mark in name for mark in ("(", ")", "<", "->", ".", "[")):
        return "dynamic_dispatch"
    return "not_found"


def unresolved_references(nodes: list[SourceNode]) -> list[dict[str, str]]:
    """
    함수 이름: unresolved_references()
    기능: 포함한 심볼의 미해결 참조를 최대 64개까지 사유와 함께 나열한다.
    인자: nodes -> 묶음에 포함한 심볼
    반환값: UnresolvedReference 값 목록
    작성 날짜: 2026/11/05
    """
    items: list[dict[str, str]] = []
    for node in nodes:
        for name in node["unresolved_reference"]:
            if len(items) == MAX_LISTED:
                return items
            items.append(
                {
                    "from_symbol_id": symbol_id(node["id"]),
                    "name": name[:_MAX_NAME_CHARS],
                    "reason": _reason(name),
                }
            )
    return items
