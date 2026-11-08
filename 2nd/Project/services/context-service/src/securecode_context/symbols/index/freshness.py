"""저장한 revision과 현재 디스크를 비교해 오래된 색인을 감지한다."""

import hashlib
from collections.abc import Mapping
from pathlib import Path

from ..parser import EXTENSIONS
from .changes import ManifestChanges, diff_manifests
from .source_reader import MAX_FILE_BYTES, read_source
from .walker import walk_workspace


def _current_hash(root: Path, path: Path) -> str | None:
    """
    함수 이름: _current_hash()
    기능: 지원 파일을 안전하게 다시 읽어 해시를 계산한다.
    인자: root -> 실제 루트, path -> 파일
    반환값: SHA-256, 읽을 수 없거나 상한을 넘으면 None
    작성 날짜: 2026/11/05
    """
    try:
        source = read_source(root, path)
    except OSError:
        return None
    if len(source) > MAX_FILE_BYTES:
        return None
    return hashlib.sha256(source).hexdigest()


def probe_changes(
    root: Path,
    manifest: Mapping[str, str],
    file_stats: Mapping[str, list[int]],
    excluded: frozenset[Path] = frozenset(),
) -> ManifestChanges:
    """
    함수 이름: probe_changes()
    기능: 크기·수정 시각이 같으면 재해시하지 않고, 달라진 파일과 새 파일만 다시 해시해 비교한다.
        색인 당시 제외된(크기·경로) 파일은 정보가 그대로면 변화로 보지 않는다.
    인자: root -> 실제 루트, manifest -> revision의 경로별 해시,
        file_stats -> revision의 경로별 [크기, 수정 시각 ns], excluded -> 탐색 제외 경로
    반환값: revision 대비 디스크의 ManifestChanges
    작성 날짜: 2026/11/05
    """
    current: dict[str, str] = {}
    unreadable_changed: list[str] = []
    for item in walk_workspace(root, excluded):
        if item.path.suffix not in EXTENSIONS:
            continue
        try:
            info = item.path.lstat()
        except OSError:
            continue
        recorded = file_stats.get(item.relative)
        same_stat = recorded == [info.st_size, info.st_mtime_ns]
        if same_stat and item.relative in manifest:
            current[item.relative] = manifest[item.relative]
            continue
        if same_stat:
            continue
        file_hash = _current_hash(root, item.path)
        if file_hash is not None:
            current[item.relative] = file_hash
        elif item.relative in manifest:
            unreadable_changed.append(item.relative)
    changes = diff_manifests(manifest, current)
    # 색인됐던 파일이 이제 읽을 수 없으면 원문을 제공할 수 없으므로 삭제와 같이 다룬다.
    changes["deleted"] = sorted(set(changes["deleted"]) | set(unreadable_changed))
    return changes
