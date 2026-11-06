"""색인과 변경 감지가 같은 제외 규칙으로 작업 공간 파일을 나열한다."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..parser import WORKSPACE_LAYOUT, PythonLayout, directory_layout

# 점으로 시작하는 디렉터리(.git, .securecode, .venv 등)는 이름 규칙으로 함께 제외한다.
EXCLUDED_DIRS = frozenset(
    {"node_modules", "venv", "build", "generated", "dist", "__pycache__", "target"}
)


@dataclass(frozen=True)
class WorkspaceFile:
    """
    클래스 이름: WorkspaceFile
    기능: 탐색한 파일의 실제 경로, POSIX 상대 경로, Python import 경계를 묶는다.
    작성 날짜: 2026/11/05
    """

    path: Path
    relative: str
    layout: PythonLayout


def _raise_walk_error(error: OSError) -> None:
    """
    함수 이름: _raise_walk_error()
    기능: 읽을 수 없는 디렉터리를 빠뜨린 상태로 새 스냅샷을 발행하지 않게 한다.
    인자: error -> 탐색 중 발생한 오류
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    raise error


def walk_workspace(root: Path, excluded: frozenset[Path] = frozenset()) -> Iterator[WorkspaceFile]:
    """
    함수 이름: walk_workspace()
    기능: 제외 디렉터리·숨김 파일·지정 산출물을 건너뛰고 정렬된 순서로 파일을 나열한다.
        Path.walk는 심볼릭 링크 디렉터리를 따라가지 않고 파일로 보고하므로 읽기 단계에서 거부된다.
    인자: root -> 실제 루트, excluded -> 탐색에서 뺄 파일·디렉터리의 실제 경로
    반환값: WorkspaceFile 반복자
    작성 날짜: 2026/11/05
    """
    layouts = {root: WORKSPACE_LAYOUT}
    for directory, folders, files in root.walk(on_error=_raise_walk_error):
        folders[:] = sorted(
            name
            for name in folders
            if not name.startswith(".")
            and name not in EXCLUDED_DIRS
            and directory / name not in excluded
        )
        layout = directory_layout(root, directory, folders, files, layouts.pop(directory))
        layouts.update((directory / folder, layout) for folder in folders)
        for filename in sorted(files):
            path = directory / filename
            if filename.startswith(".") or path in excluded:
                continue
            yield WorkspaceFile(path, path.relative_to(root).as_posix(), layout)
