"""원문을 내보내기 직전에 디스크 파일 해시를 다시 확인하고 SourceProvenance를 만든다."""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..graph import SourceNode
from .ports import SourceRegistryPort
from .source_reader import read_source


@dataclass(frozen=True)
class VerifiedSymbol:
    """
    클래스 이름: VerifiedSymbol
    기능: 현재 revision의 심볼과 디스크 해시를 다시 확인한 SourceProvenance를 묶는다.
    작성 날짜: 2026/11/05
    """

    index_revision: int
    node: SourceNode
    provenance: dict[str, str | None]


def _file_hash(root: Path, relative_path: str) -> str | None:
    """
    함수 이름: _file_hash()
    기능: 루트 안의 파일을 안전하게 읽어 해시를 계산한다.
    인자: root -> 실제 루트, relative_path -> POSIX 상대 경로
    반환값: SHA-256, 읽을 수 없으면 None
    작성 날짜: 2026/11/05
    """
    try:
        source = read_source(root, root.joinpath(*relative_path.split("/")))
    except OSError:
        return None
    return hashlib.sha256(source).hexdigest()


def verify_symbols(
    workspace_id: str,
    index_revision: int,
    root: Path,
    nodes: Mapping[str, SourceNode],
    uris: Iterable[str],
    registry: SourceRegistryPort,
) -> dict[str, VerifiedSymbol | None]:
    """
    함수 이름: verify_symbols()
    기능: 심볼 파일마다 한 번만 다시 해시한다. 색인 때와 다르면 그 파일의 심볼은 None이다.
    인자: workspace_id -> 작업 공간, index_revision -> revision, root -> 검사한 실제 루트,
        nodes -> revision 그래프, uris -> 확인할 내부 심볼 ID, registry -> Source 등록부 포트
    반환값: 심볼별 VerifiedSymbol, 바뀐 파일이면 None
    작성 날짜: 2026/11/05
    """
    hashes: dict[str, str | None] = {}
    result: dict[str, VerifiedSymbol | None] = {}
    for uri in uris:
        node = nodes[uri]
        path = node["path"]
        if path not in hashes:
            hashes[path] = _file_hash(root, path)
        if hashes[path] != node["content_sha256"]:
            result[uri] = None
            continue
        provenance = {
            "pointer": registry.lookup(workspace_id, path, node["content_sha256"]),
            "relative_path": path,
            "content_sha256": node["content_sha256"],
        }
        result[uri] = VerifiedSymbol(index_revision, node, provenance)
    return result
