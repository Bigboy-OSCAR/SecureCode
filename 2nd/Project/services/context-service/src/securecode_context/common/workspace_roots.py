"""작업 공간 root 등록부(3.6). host가 검증·등록한 workspace만 서비스가 안다.

Source 등록부(SourceRootPort)와 R0 색인(WorkspaceRootPort)이 같은 구현을 쓴다. 서비스는 host 검사를
믿지 않고 절대 경로·실재 디렉터리·링크 아님·서비스 데이터 폴더 밖인지 다시 확인한다.
"""

import json
import os
import re
import threading
from pathlib import Path

from securecode_context.common.errors import ErrorCode, ServiceError

_WORKSPACE = re.compile(r"^ws_[A-Za-z0-9-]{8,64}$")


def _forbidden(reason: str) -> ServiceError:
    """
    함수 이름: _forbidden()
    기능: root 거절 오류를 만든다(경로는 응답에 넣지 않는다).
    인자: reason -> 기계가 읽는 이유
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(ErrorCode.FORBIDDEN, "작업 공간 root를 쓸 수 없습니다.", {"reason": reason})


class WorkspaceRootRegistry:
    """
    클래스 이름: WorkspaceRootRegistry
    기능: workspace ID → 실제 root 표를 데이터 폴더의 JSON 파일에 유지한다(재시작 후에도 유지).
    작성 날짜: 2026/11/10
    """

    def __init__(self, path: Path, forbidden: tuple[Path, ...] = ()) -> None:
        """
        함수 이름: __init__()
        기능: 저장 파일을 읽어 표를 만든다.
        인자: path -> 저장 파일, forbidden -> root가 될 수 없는 서비스 소유 폴더
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._path = path
        self._forbidden = tuple(p.resolve() for p in forbidden)
        self._lock = threading.Lock()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._roots = {str(k): str(v) for k, v in data.items()}
        except OSError, ValueError, AttributeError:
            self._roots = {}

    def register(self, workspace_id: str, root_path: str) -> Path:
        """
        함수 이름: register()
        기능: root를 검사하고 등록한다. 같은 workspace의 다른 root는 거절한다(멱등).
        인자: workspace_id -> 작업 공간, root_path -> host가 검증한 절대 경로
        반환값: 실제 root 경로
        작성 날짜: 2026/11/10
        """
        if not _WORKSPACE.fullmatch(workspace_id):
            raise ServiceError(
                ErrorCode.VALIDATION_FAILED, "workspace ID 형식이 올바르지 않습니다."
            )
        raw = Path(root_path)
        if not raw.is_absolute():
            raise _forbidden("root_not_absolute")
        if raw.is_symlink() or raw.is_junction() or not raw.is_dir():
            raise _forbidden("root_not_directory")
        root = raw.resolve(strict=True)
        if root.parent == root:
            raise _forbidden("root_is_filesystem_root")
        for owned in self._forbidden:
            if root == owned or owned in root.parents or root in owned.parents:
                raise _forbidden("root_overlaps_service_data")
        with self._lock:
            current = self._roots.get(workspace_id)
            if current is not None and Path(current) != root:
                raise ServiceError(
                    ErrorCode.VALIDATION_FAILED,
                    "이미 다른 root로 등록된 작업 공간입니다.",
                    {"reason": "root_conflict"},
                )
            self._roots[workspace_id] = str(root)
            self._save()
        return root

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: 등록된 root를 돌려준다. 모르면 NOT_FOUND다.
        인자: workspace_id -> 작업 공간
        반환값: 절대 경로
        작성 날짜: 2026/11/10
        """
        with self._lock:
            root = self._roots.get(workspace_id)
        if root is None:
            raise ServiceError(
                ErrorCode.NOT_FOUND,
                "등록되지 않은 작업 공간입니다.",
                {"reason": "workspace_unknown"},
            )
        return Path(root)

    def _save(self) -> None:
        """
        함수 이름: _save()
        기능: 표를 임시 파일에 쓰고 원자적으로 바꾼다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._roots), encoding="utf-8")
        os.replace(temp, self._path)
