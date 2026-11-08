"""revision의 R0 후보마다 구성 심볼의 참조 깊이·경계 누락·원문 범위 키를 계산한다."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from ..graph import RawCandidate, SourceNode

MAX_DEPTH = 3
type FragmentKey = tuple[str, str, int, int]


@dataclass(frozen=True)
class CandidateInfo:
    """
    클래스 이름: CandidateInfo
    기능: 내부 후보 ID, 시작 심볼, BFS 순서의 구성 심볼과 깊이, 포함하지 못한 참조를 보관한다.
    작성 날짜: 2026/11/05
    """

    raw_id: str
    primary: str
    members: tuple[str, ...]
    depth: int
    boundary: tuple[tuple[str, str], ...]
    fragment_keys: frozenset[FragmentKey]


def fragment_key(node: SourceNode) -> FragmentKey:
    """
    함수 이름: fragment_key()
    기능: 같은 원문 범위를 식별하는 (경로, 파일 해시, 시작·끝 바이트) 키를 만든다.
    인자: node -> 심볼
    반환값: FragmentKey
    작성 날짜: 2026/11/05
    """
    return node["path"], node["content_sha256"], node["start_byte"], node["end_byte"]


def _depths(nodes: Mapping[str, SourceNode], primary: str, members: set[str]) -> dict[str, int]:
    """
    함수 이름: _depths()
    기능: 시작 심볼에서 구성 심볼까지의 최단 참조 edge 수를 구한다.
    인자: nodes -> 그래프, primary -> 시작 심볼, members -> 후보 구성 심볼
    반환값: 심볼별 깊이
    작성 날짜: 2026/11/05
    """
    depths = {primary: 0}
    pending = deque([primary])
    while pending:
        current = pending.popleft()
        if depths[current] == MAX_DEPTH:
            continue
        for dependency in nodes[current]["deps"]:
            if dependency in members and dependency not in depths:
                depths[dependency] = depths[current] + 1
                pending.append(dependency)
    return depths


def describe_candidate(nodes: Mapping[str, SourceNode], candidate: RawCandidate) -> CandidateInfo:
    """
    함수 이름: describe_candidate()
    기능: 후보 구성 밖의 참조를 깊이 3 도달(depth_limit)과 크기 상한(too_large)으로 나눈다.
        단일 원문(atomic) 후보는 참조를 포함하지 않으므로 경계 누락을 기록하지 않는다.
    인자: nodes -> 그래프, candidate -> R0 후보
    반환값: CandidateInfo
    작성 날짜: 2026/11/05
    """
    members = tuple(candidate["source_uris"])
    primary = members[0]
    member_set = set(members)
    depths = _depths(nodes, primary, member_set)
    boundary: dict[str, str] = {}
    if candidate["kind"] != "raw_atomic":
        for member in members:
            for dependency in nodes[member]["deps"]:
                if dependency in member_set or dependency in boundary:
                    continue
                at_limit = depths.get(member, MAX_DEPTH) >= MAX_DEPTH
                boundary[dependency] = "depth_limit" if at_limit else "too_large"
    return CandidateInfo(
        raw_id=candidate["id"],
        primary=primary,
        members=members,
        depth=max(depths.values()),
        boundary=tuple(boundary.items()),
        fragment_keys=frozenset(fragment_key(nodes[member]) for member in members),
    )
