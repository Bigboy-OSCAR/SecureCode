"""인덱스 경로와 Python import 이름을 구분하고 하위 프로젝트의 이름 공간을 격리한다."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class PythonLayout:
    """
    클래스 이름: PythonLayout
    기능: 작업 공간 안의 한 Python 프로젝트 경계와 src 레이아웃을 보관한다.
    작성 날짜: 2026/11/05
    """

    project: PurePosixPath = field(default_factory=PurePosixPath)
    has_src: bool = False


WORKSPACE_LAYOUT = PythonLayout()


def directory_layout(
    root: Path, directory: Path, folders: list[str], files: list[str], parent: PythonLayout
) -> PythonLayout:
    """
    함수 이름: directory_layout()
    기능: 패키징 파일 또는 독립 src 트리로 확인되는 디렉터리에서 새 import 경계를 연다.
    인자: root -> 작업 공간, directory -> 현재 경로, folders/files -> 직계 항목, parent -> 상위 경계
    반환값: 현재 디렉터리의 Python 레이아웃
    작성 날짜: 2026/11/05
    """
    has_metadata = not {"pyproject.toml", "setup.cfg", "setup.py"}.isdisjoint(files)
    has_src = "src" in folders and not (directory / "src" / "__init__.py").exists()
    relative = PurePosixPath(directory.relative_to(root).as_posix())
    under_src = parent.has_src and relative.relative_to(parent.project).parts[:1] == ("src",)
    if has_metadata or (has_src and "__init__.py" not in files and not under_src):
        return PythonLayout(relative, has_src)
    return parent
