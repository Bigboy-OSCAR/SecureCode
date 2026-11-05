"""워크스페이스를 읽어 R0 후보 JSON으로 보관할 수 있는 스냅샷을 만든다."""

import hashlib
import os
import stat
import sys
from pathlib import Path
from typing import NotRequired, TypedDict

from .graph import RawCandidate, SourceGraph, SourceNode, raw_candidates
from .parser import EXTENSIONS, parse_source
from .python_layout import WORKSPACE_LAYOUT, directory_layout

MAX_FILE_BYTES = 1024 * 1024
EXCLUDED_DIRS = {"node_modules", "venv", "build", "generated", "dist", "__pycache__", "target"}


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


def _raise_walk_error(error: OSError) -> None:
    """
    함수 이름: _raise_walk_error()
    기능: 읽을 수 없는 디렉터리를 빠뜨린 상태로 새 스냅샷을 발행하지 않게 한다.
    인자: error -> 탐색 중 발생한 오류
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    raise error


def _open_source(root: Path, path: Path, flags: int) -> int:
    """
    함수 이름: _open_source()
    기능: 지원하는 OS에서는 디렉터리 핸들을 따라 각 경로 요소의 심볼릭 링크를 거부한다.
    인자: root -> 기준 디렉터리, path -> 읽을 파일, flags -> 열기 플래그
    반환값: 열린 파일 디스크립터
    작성 날짜: 2026/11/05
    """
    if sys.platform == "win32":
        if any(os.path.isreserved(part) for part in path.relative_to(root).parts):
            raise PermissionError("reserved source path")
        return os.open(path, flags | os.O_BINARY)
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, dir_flags)
    try:
        for part in path.parent.relative_to(root).parts:
            child = os.open(part, dir_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(path.name, flags | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)


def _read_source(root: Path, path: Path) -> bytes:
    """
    함수 이름: _read_source()
    기능: 루트 안의 일반 파일만 크기 제한 내에서 읽고 열기 중 파일 교체를 검사한다.
    인자: root -> 실제 루트, path -> 파일 경로
    반환값: 원문 바이트(상한 초과 확인용 1바이트 포함)
    작성 날짜: 2026/11/05
    """
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise OSError("path_rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(_open_source(root, path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(info, opened) or not path.resolve().is_relative_to(root):
            raise OSError("path_rejected")
        if sys.platform == "win32":
            from securecode_context.common.windows_file import final_path

            if final_path(stream.fileno()) != path:
                raise OSError("path_rejected")
        source = stream.read(MAX_FILE_BYTES + 1)
        after_read = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns) != (after_read.st_size, after_read.st_mtime_ns):
            raise OSError("source_changed")
        return source


def build_index(root: Path, *, output: Path | None = None) -> R0Index:
    """
    함수 이름: build_index()
    기능: 지원 파일을 한번씩 읽고 참조 그래프 및 깊이 3의 R0 원문 후보를 생성한다.
    인자: root -> 워크스페이스, output -> 재생성 때 탐색에서 제외할 산출물
    반환값: 입력 파일 해시, 그래프, 후보, 진단을 포함한 R0 스냅샷
    작성 날짜: 2026/11/05
    """
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    graph = SourceGraph()
    manifest: dict[str, str] = {}
    diagnostics: list[Diagnostic] = []
    excluded_output = (output.parent.resolve() / output.name) if output else None
    layouts = {root: WORKSPACE_LAYOUT}
    for directory, folders, files in root.walk(on_error=_raise_walk_error):
        folders[:] = sorted(d for d in folders if not d.startswith(".") and d not in EXCLUDED_DIRS)
        layout = directory_layout(root, directory, folders, files, layouts.pop(directory))
        layouts.update((directory / folder, layout) for folder in folders)
        for filename in sorted(files):
            path = directory / filename
            if filename.startswith(".") or path == excluded_output:
                continue
            relative = path.relative_to(root).as_posix()
            try:
                relative.encode("utf-8")
            except UnicodeEncodeError:
                display = os.fsencode(relative).decode("utf-8", errors="backslashreplace")
                diagnostics.append(Diagnostic(relative_path=display, reason_code="path_rejected"))
                continue
            if path.suffix not in EXTENSIONS:
                diagnostics.append(
                    Diagnostic(relative_path=relative, reason_code="unsupported_language")
                )
                continue
            try:
                source = _read_source(root, path)
            except OSError:
                diagnostics.append(Diagnostic(relative_path=relative, reason_code="path_rejected"))
                continue
            if len(source) > MAX_FILE_BYTES:
                diagnostics.append(Diagnostic(relative_path=relative, reason_code="too_large"))
                continue
            file_hash = hashlib.sha256(source).hexdigest()
            manifest[relative] = file_hash
            try:
                language, declarations = parse_source(relative, source, python_layout=layout)
            except UnicodeDecodeError:
                diagnostics.append(Diagnostic(relative_path=relative, reason_code="encoding_error"))
                continue
            except SyntaxError as error:
                diagnostic = Diagnostic(relative_path=relative, reason_code="syntax_error")
                if error.lineno:
                    diagnostic["line"] = error.lineno
                diagnostics.append(diagnostic)
                continue
            except RecursionError:
                diagnostics.append(Diagnostic(relative_path=relative, reason_code="too_large"))
                continue
            if not graph.add_file(relative, language, source, file_hash, declarations):
                diagnostics.append(Diagnostic(relative_path=relative, reason_code="too_large"))
    graph.link()
    return R0Index(
        format_version=1,
        manifest=manifest,
        nodes=graph.nodes,
        raw=raw_candidates(graph.nodes),
        diagnostics=diagnostics,
    )
