"""두 파일 manifest의 추가·수정·삭제·이동과 다시 만들 R0 자료를 계산한다."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import TypedDict

from ..graph import RawCandidate, SourceNode


class FileMove(TypedDict):
    """
    클래스 이름: FileMove
    기능: 내용 해시가 같은 파일의 이전·새 상대 경로를 기록한다.
    작성 날짜: 2026/11/05
    """

    from_path: str
    to_path: str


class ManifestChanges(TypedDict):
    """
    클래스 이름: ManifestChanges
    기능: revision 사이 또는 디스크와 revision 사이의 파일 변화를 정렬된 목록으로 보관한다.
    작성 날짜: 2026/11/05
    """

    added: list[str]
    modified: list[str]
    deleted: list[str]
    moved: list[FileMove]


class RevisionChanges(ManifestChanges):
    """
    클래스 이름: RevisionChanges
    기능: 파일 변화와 함께 이전 revision에서 무효가 된 후보와 재계산 필요 여부를 표시한다.
    작성 날짜: 2026/11/05
    """

    stale_candidate_ids: list[str]
    bundle_rebuild_required: bool
    idf_recompute_required: bool


def empty_changes() -> ManifestChanges:
    """
    함수 이름: empty_changes()
    기능: 변화가 없는 결과를 만든다.
    인자: 없음
    반환값: 빈 ManifestChanges
    작성 날짜: 2026/11/05
    """
    return ManifestChanges(added=[], modified=[], deleted=[], moved=[])


def has_changes(changes: ManifestChanges) -> bool:
    """
    함수 이름: has_changes()
    기능: 하나라도 파일 변화가 있는지 확인한다.
    인자: changes -> 파일 변화
    반환값: 변화가 있으면 True
    작성 날짜: 2026/11/05
    """
    return any(changes[key] for key in ("added", "modified", "deleted", "moved"))


def diff_manifests(old: Mapping[str, str], new: Mapping[str, str]) -> ManifestChanges:
    """
    함수 이름: diff_manifests()
    기능: 경로별 SHA-256을 비교한다. 사라진 경로와 새 경로의 해시가 하나씩 같으면 이동으로 본다.
    인자: old -> 이전 manifest, new -> 새 manifest
    반환값: 정렬된 ManifestChanges
    작성 날짜: 2026/11/05
    """
    removed = sorted(set(old) - set(new))
    created = sorted(set(new) - set(old))
    removed_by_hash: defaultdict[str, list[str]] = defaultdict(list)
    created_by_hash: defaultdict[str, list[str]] = defaultdict(list)
    for path in removed:
        removed_by_hash[old[path]].append(path)
    for path in created:
        created_by_hash[new[path]].append(path)
    moved: list[FileMove] = []
    for file_hash, sources in removed_by_hash.items():
        targets = created_by_hash.get(file_hash, [])
        # 같은 내용이 여러 곳으로 갈라지면 어느 쪽이 이동인지 알 수 없으므로 추가·삭제로 남긴다.
        if len(sources) == 1 and len(targets) == 1:
            moved.append(FileMove(from_path=sources[0], to_path=targets[0]))
    moved_from = {move["from_path"] for move in moved}
    moved_to = {move["to_path"] for move in moved}
    return ManifestChanges(
        added=[path for path in created if path not in moved_to],
        modified=sorted(path for path in set(old) & set(new) if old[path] != new[path]),
        deleted=[path for path in removed if path not in moved_from],
        moved=sorted(moved, key=lambda move: move["from_path"]),
    )


def changed_old_paths(changes: ManifestChanges) -> set[str]:
    """
    함수 이름: changed_old_paths()
    기능: 이전 revision 기준으로 내용·위치가 더 이상 유효하지 않은 경로를 모은다.
    인자: changes -> 파일 변화
    반환값: 수정·삭제·이동 전 경로 집합
    작성 날짜: 2026/11/05
    """
    return (
        set(changes["modified"])
        | set(changes["deleted"])
        | {move["from_path"] for move in changes["moved"]}
    )


def stale_candidates(
    nodes: Mapping[str, SourceNode], raw: Iterable[RawCandidate], paths: set[str]
) -> list[str]:
    """
    함수 이름: stale_candidates()
    기능: 변경 파일의 심볼을 하나라도 포함한 이전 후보(의존 bundle 포함)를 찾는다.
    인자: nodes -> 이전 그래프, raw -> 이전 후보, paths -> 바뀐 이전 경로
    반환값: 정렬된 후보 ID 목록
    작성 날짜: 2026/11/05
    """
    return sorted(
        candidate["id"]
        for candidate in raw
        if any(nodes[uri]["path"] in paths for uri in candidate["source_uris"])
    )


def revision_changes(
    old_manifest: Mapping[str, str],
    old_nodes: Mapping[str, SourceNode],
    old_raw: Iterable[RawCandidate],
    new_manifest: Mapping[str, str],
) -> RevisionChanges:
    """
    함수 이름: revision_changes()
    기능: 새 revision을 만들 때 이전 revision과의 차이와 bundle·IDF 재계산 필요성을 기록한다.
        IDF는 전체 후보 집합에 의존하므로 파일이 하나라도 바뀌면 다시 계산해야 한다.
    인자: old_manifest/old_nodes/old_raw -> 이전 revision 자료, new_manifest -> 새 manifest
    반환값: RevisionChanges
    작성 날짜: 2026/11/05
    """
    changes = diff_manifests(old_manifest, new_manifest)
    stale = stale_candidates(old_nodes, old_raw, changed_old_paths(changes))
    changed = has_changes(changes)
    return RevisionChanges(
        added=changes["added"],
        modified=changes["modified"],
        deleted=changes["deleted"],
        moved=changes["moved"],
        stale_candidate_ids=stale,
        bundle_rebuild_required=bool(stale) or bool(changes["added"]),
        idf_recompute_required=changed,
    )
