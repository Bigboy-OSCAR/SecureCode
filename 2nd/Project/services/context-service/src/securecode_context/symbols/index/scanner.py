"""워크스페이스를 읽어 R0 후보 JSON으로 보관할 수 있는 스냅샷을 만든다."""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import NotRequired, TypedDict

from ..graph import RawCandidate, SourceGraph, SourceNode, raw_candidates
from ..parser import EXTENSIONS, PythonLayout, parse_source
from .source_reader import MAX_FILE_BYTES, read_source
from .walker import walk_workspace

type FileStat = tuple[int, int]


class Diagnostic(TypedDict):
    """
    클래스 이름: Diagnostic
    기능: 색인에서 빠진 파일의 상대 경로와 원인을 기록한다.
    작성 날짜: 2026/11/05
    """

    relative_path: str
    reason_code: str
    line: NotRequired[int]


class R0Index(TypedDict):
    """
    클래스 이름: R0Index
    기능: 파일 해시와 진단, R0 원문 그래프 및 검색 후보를 함께 저장한다.
    작성 날짜: 2026/11/05
    """

    format_version: int
    manifest: dict[str, str]
    nodes: dict[str, SourceNode]
    raw: list[RawCandidate]
    diagnostics: list[Diagnostic]


@dataclass
class ScanResult:
    """
    클래스 이름: ScanResult
    기능: R0 스냅샷과 변경 감지용 파일 크기·수정 시각, 파일별 언어와 탐색 파일 수를 묶는다.
    작성 날짜: 2026/11/05
    """

    index: R0Index
    file_stats: dict[str, FileStat] = field(default_factory=dict)
    file_languages: dict[str, str] = field(default_factory=dict)
    discovered: int = 0


def _parse_file(
    graph: SourceGraph, relative: str, source: bytes, file_hash: str, layout: PythonLayout
) -> tuple[str | None, Diagnostic | None]:
    """
    함수 이름: _parse_file()
    기능: 파일 하나를 파싱해 그래프에 넣는다. 파일 단위 오류는 진단으로만 남긴다.
    인자: graph -> 빌드 중 그래프, relative -> 상대 경로, source -> 원문,
        file_hash -> SHA-256, layout -> Python import 경계
    반환값: (성공한 언어 또는 None, 진단 또는 None)
    작성 날짜: 2026/11/05
    """
    try:
        language, declarations = parse_source(relative, source, python_layout=layout)
    except UnicodeDecodeError:
        return None, Diagnostic(relative_path=relative, reason_code="encoding_error")
    except SyntaxError as error:
        diagnostic = Diagnostic(relative_path=relative, reason_code="syntax_error")
        if error.lineno:
            diagnostic["line"] = error.lineno
        return None, diagnostic
    except RecursionError:
        return None, Diagnostic(relative_path=relative, reason_code="too_large")
    if not graph.add_file(relative, language, source, file_hash, declarations):
        return None, Diagnostic(relative_path=relative, reason_code="too_large")
    return language, None


def scan_workspace(root: Path, *, excluded: frozenset[Path] = frozenset()) -> ScanResult:
    """
    함수 이름: scan_workspace()
    기능: 지원 파일을 한번씩 읽고 참조 그래프 및 깊이 3의 R0 원문 후보를 생성한다.
    인자: root -> 워크스페이스, excluded -> 탐색에서 뺄 산출물·저장소의 실제 경로
    반환값: R0 스냅샷과 변경 감지용 파일 정보
    작성 날짜: 2026/11/05
    """
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    graph = SourceGraph()
    result = ScanResult(
        index=R0Index(format_version=1, manifest={}, nodes={}, raw=[], diagnostics=[])
    )
    manifest = result.index["manifest"]
    diagnostics = result.index["diagnostics"]
    for item in walk_workspace(root, excluded):
        result.discovered += 1
        relative = item.relative
        try:
            relative.encode("utf-8")
        except UnicodeEncodeError:
            display = os.fsencode(relative).decode("utf-8", errors="replace")
            diagnostics.append(Diagnostic(relative_path=display, reason_code="path_rejected"))
            continue
        if item.path.is_symlink() or item.path.is_junction():
            diagnostics.append(Diagnostic(relative_path=relative, reason_code="path_rejected"))
            continue
        if item.path.suffix not in EXTENSIONS:
            diagnostics.append(
                Diagnostic(relative_path=relative, reason_code="unsupported_language")
            )
            continue
        try:
            info = item.path.lstat()
            result.file_stats[relative] = (info.st_size, info.st_mtime_ns)
            source = read_source(root, item.path)
        except OSError:
            diagnostics.append(Diagnostic(relative_path=relative, reason_code="path_rejected"))
            continue
        if len(source) > MAX_FILE_BYTES:
            diagnostics.append(Diagnostic(relative_path=relative, reason_code="too_large"))
            continue
        file_hash = hashlib.sha256(source).hexdigest()
        manifest[relative] = file_hash
        language, diagnostic = _parse_file(graph, relative, source, file_hash, item.layout)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        elif language is not None:
            result.file_languages[relative] = language
    graph.link()
    result.index["nodes"] = graph.nodes
    result.index["raw"] = raw_candidates(graph.nodes)
    return result


def build_index(root: Path, *, output: Path | None = None) -> R0Index:
    """
    함수 이름: build_index()
    기능: 로컬 CLI용으로 R0 스냅샷만 생성한다. 출력 JSON 자신은 탐색에서 제외한다.
    인자: root -> 워크스페이스, output -> 재생성 때 탐색에서 제외할 산출물
    반환값: 입력 파일 해시, 그래프, 후보, 진단을 포함한 R0 스냅샷
    작성 날짜: 2026/11/05
    """
    excluded = frozenset({output.parent.resolve() / output.name}) if output else frozenset()
    return scan_workspace(root, excluded=excluded).index
