"""등록 요청 대상을 허용 root·파일 목록·외부 허용 항목으로 바꾸는 계획 단계."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import RLock

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.directory import list_directory
from securecode_context.pointers.source.models import (
    ExternalGrant,
    SourceIssue,
    SourceLocation,
    SourceTarget,
)
from securecode_context.pointers.source.paths import (
    check_inside,
    forbidden,
    normalize_relative,
    resolve_external_root,
)
from securecode_context.pointers.source.registry_db import SourceDb


@dataclass(frozen=True)
class RegistrationPlan:
    """
    클래스 이름: RegistrationPlan
    기능: 등록할 파일(root 기준 상대 경로)과 미리 제외한 항목.
    작성 날짜: 2026/11/10
    """

    location: SourceLocation
    grant_id: str | None
    root: Path
    prefix: PurePosixPath
    is_directory: bool
    files: list[PurePosixPath] = field(default_factory=list)
    issues: list[SourceIssue] = field(default_factory=list)


def _kind_mismatch() -> ServiceError:
    """
    함수 이름: _kind_mismatch()
    기능: 요청 kind와 실제 대상 종류가 다를 때의 오류를 만든다.
    인자: 없음
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(
        ErrorCode.UNSUPPORTED_FORMAT,
        "요청한 종류와 실제 대상이 다릅니다.",
        {"reason": "kind_mismatch"},
    )


class RegistrationPlanner:
    """
    클래스 이름: RegistrationPlanner
    기능: 작업 공간 내부 대상과 외부 허용 대상을 분리해 검사하고 외부 허용 항목을 관리한다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        db: SourceDb,
        lock: RLock,
        workspace_root: Callable[[str], Path],
        forbidden_roots: tuple[Path, ...],
    ) -> None:
        """
        함수 이름: __init__()
        기능: 등록부 DB·잠금·workspace root 해석기·서비스 소유 경로를 보관한다.
        인자: db -> SourceDb, lock -> 등록부 잠금, workspace_root -> root 해석 함수,
            forbidden_roots -> 외부 등록을 막을 경로
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._db = db
        self._lock = lock
        self._workspace_root = workspace_root
        self._forbidden_roots = forbidden_roots

    def plan(self, workspace_id: str, target: SourceTarget) -> RegistrationPlan:
        """
        함수 이름: plan()
        기능: 대상 위치에 맞는 root와 등록 후보를 만든다.
        인자: workspace_id -> 범위, target -> 요청 대상
        반환값: RegistrationPlan
        작성 날짜: 2026/11/10
        """
        if target.location is SourceLocation.WORKSPACE:
            return self._plan_workspace(workspace_id, target)
        return self._plan_external(workspace_id, target)

    def verify_grant_root(self, real_root: Path) -> Path:
        """
        함수 이름: verify_grant_root()
        기능: 저장한 외부 root가 아직 링크가 아니고 같은 실제 경로인지 확인한다.
        인자: real_root -> 등록 때 확인한 실제 root
        반환값: 같은 root
        작성 날짜: 2026/11/10
        """
        if real_root.is_symlink() or real_root.is_junction():
            raise forbidden("external_root_replaced")
        try:
            current = real_root.resolve(strict=True)
        except OSError as error:
            raise ServiceError(
                ErrorCode.NOT_FOUND, "원본 파일이 삭제됐습니다.", {"reason": "original_missing"}
            ) from error
        if str(current) != str(real_root) or not current.is_dir():
            raise forbidden("external_root_replaced")
        return current

    def release_grant(self, grant_id: str | None) -> None:
        """
        함수 이름: release_grant()
        기능: 등록이 하나도 남지 않은 외부 허용 항목을 지운다.
        인자: grant_id -> 허용 ID 또는 None
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if grant_id is not None:
            with self._lock:
                self._db.links.drop_unused_grant(grant_id)

    def _plan_workspace(self, workspace_id: str, target: SourceTarget) -> RegistrationPlan:
        """
        함수 이름: _plan_workspace()
        기능: 작업 공간 상대 경로를 검사하고 파일 또는 디렉터리 후보를 만든다.
        인자: workspace_id -> 범위, target -> workspace 대상
        반환값: RegistrationPlan
        작성 날짜: 2026/11/10
        """
        root = self._workspace_root(workspace_id)
        relative = normalize_relative(target.path)
        real = check_inside(root, relative)
        location = SourceLocation.WORKSPACE
        if target.kind == "file":
            if not real.is_file():
                raise _kind_mismatch()
            return RegistrationPlan(location, None, root, relative.parent, False, [relative])
        if not real.is_dir():
            raise _kind_mismatch()
        files, issues = list_directory(real)
        return RegistrationPlan(
            location, None, root, relative, True, [relative / name for name in files], issues
        )

    def _plan_external(self, workspace_id: str, target: SourceTarget) -> RegistrationPlan:
        """
        함수 이름: _plan_external()
        기능: 사용자가 명시한 외부 경로를 허용 root로 만들고 workspace 범위 허용 항목을 기록한다.
            파일은 그 파일 하나만, 디렉터리는 그 아래만 허용한다.
        인자: workspace_id -> 범위, target -> external 대상
        반환값: RegistrationPlan
        작성 날짜: 2026/11/10
        """
        real = resolve_external_root(target.path, self._forbidden_roots)
        location = SourceLocation.EXTERNAL
        if target.kind == "file":
            if not real.is_file():
                raise _kind_mismatch()
            name = normalize_relative(real.name)
            grant_id = self._grant(workspace_id, real.parent, real.name)
            return RegistrationPlan(location, grant_id, real.parent, PurePosixPath(), False, [name])
        if not real.is_dir():
            raise _kind_mismatch()
        files, issues = list_directory(real)
        grant_id = self._grant(workspace_id, real, None)
        return RegistrationPlan(location, grant_id, real, PurePosixPath(), True, files, issues)

    def _grant(self, workspace_id: str, real_root: Path, file_name: str | None) -> str:
        """
        함수 이름: _grant()
        기능: 같은 workspace의 같은 외부 허용 항목을 재사용하거나 새로 만든다.
        인자: workspace_id -> 범위, real_root -> 실제 root, file_name -> 단일 파일 이름
        반환값: grant_id
        작성 날짜: 2026/11/10
        """
        with self._lock:
            existing = self._db.links.find_grant(workspace_id, real_root, file_name)
            if existing is not None:
                return existing
            grant = ExternalGrant(f"grt_{uuid.uuid4().hex}", workspace_id, real_root, file_name)
            self._db.links.add_grant(grant)
            return grant.grant_id
