"""Source 등록부 시험 공용 도구: 고정 workspace root 포트, 디렉터리 링크, 등록부 생성."""

import sys
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.derived import DerivedCacheDirectory
from securecode_context.pointers.source.models import SourceLocation, SourceTarget
from securecode_context.pointers.source.registry import SourceRegistry
from support.helpers import FixedTokenCounter

WS_A = "ws_00000001"
WS_B = "ws_00000002"


class FixedRoots:
    """
    클래스 이름: FixedRoots
    기능: [시험용] workspace ID → root 표. 운영 연결은 3.6 host 작업 공간 등록부다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, roots: dict[str, Path]) -> None:
        """
        함수 이름: __init__()
        기능: root 표를 보관한다.
        인자: roots -> ID별 root
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.roots = roots

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: root를 찾고 없으면 NOT_FOUND를 던진다.
        인자: workspace_id -> 작업 공간
        반환값: root 경로
        작성 날짜: 2026/11/10
        """
        if workspace_id not in self.roots:
            raise ServiceError(ErrorCode.NOT_FOUND, "unknown workspace")
        return self.roots[workspace_id]


def make_workspaces(tmp_path: Path) -> FixedRoots:
    """
    함수 이름: make_workspaces()
    기능: 서로 다른 두 workspace root를 만든다.
    인자: tmp_path -> pytest 임시 폴더
    반환값: FixedRoots
    작성 날짜: 2026/11/10
    """
    roots = {WS_A: tmp_path / "ws_a", WS_B: tmp_path / "ws_b"}
    for root in roots.values():
        root.mkdir()
    return FixedRoots(roots)


def open_registry(tmp_path: Path, roots: FixedRoots) -> SourceRegistry:
    """
    함수 이름: open_registry()
    기능: 같은 데이터 폴더에 등록부를 연다(재시작 시험은 두 번 호출한다).
    인자: tmp_path -> 임시 폴더, roots -> root 포트
    반환값: SourceRegistry
    작성 날짜: 2026/11/10
    """
    data = tmp_path / "data"
    return SourceRegistry(
        data / "sources" / "registry.sqlite",
        roots,
        DerivedCacheDirectory(data / "derived"),
        forbidden_roots=(data,),
    )


def open_adapter(tmp_path: Path, roots: FixedRoots) -> SourceAdapter:
    """
    함수 이름: open_adapter()
    기능: 시험 계수기(UTF-8 바이트 = 토큰, provider_estimate 표시)를 쓰는 Source adapter를 연다.
    인자: tmp_path -> 임시 폴더, roots -> root 포트
    반환값: SourceAdapter
    작성 날짜: 2026/11/10
    """
    return SourceAdapter(open_registry(tmp_path, roots), FixedTokenCounter())


def single_workspace(tmp_path: Path) -> tuple[FixedRoots, Path]:
    """
    함수 이름: single_workspace()
    기능: WS_A 하나만 있는 root 포트를 만든다.
    인자: tmp_path -> 임시 폴더
    반환값: root 포트와 root 경로
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "workspace"
    root.mkdir()
    return FixedRoots({WS_A: root}), root


def workspace_file(path: str) -> SourceTarget:
    """
    함수 이름: workspace_file()
    기능: 작업 공간 파일 등록 대상을 만든다.
    인자: path -> 상대 경로
    반환값: SourceTarget
    작성 날짜: 2026/11/10
    """
    return SourceTarget(SourceLocation.WORKSPACE, "file", path)


def make_dir_link(link: Path, target: Path) -> None:
    """
    함수 이름: make_dir_link()
    기능: 디렉터리 링크를 만든다. Windows는 권한 없이 가능한 junction, 그 외는 symlink다.
    인자: link -> 만들 링크, target -> 대상 디렉터리
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    link.symlink_to(target, target_is_directory=True)


def make_file_link(link: Path, target: Path) -> None:
    """
    함수 이름: make_file_link()
    기능: 파일 symlink를 만든다. 권한이 없는 Windows에서는 시험을 건너뛴다.
    인자: link -> 만들 링크, target -> 대상 파일
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip(
            "file symlink needs Developer Mode or admin on Windows; junction cases cover it"
        )


def code_of(error: pytest.ExceptionInfo[ServiceError]) -> ErrorCode:
    """
    함수 이름: code_of()
    기능: 잡은 ServiceError의 계약 코드를 돌려준다.
    인자: error -> pytest.raises 결과
    반환값: ErrorCode
    작성 날짜: 2026/11/10
    """
    return error.value.code
