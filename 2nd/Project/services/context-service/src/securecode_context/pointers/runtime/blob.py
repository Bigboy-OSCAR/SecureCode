"""Runtime blob 원자적 저장.

작성일: 2026-11-06
"""

import hashlib
import os
import tempfile
from pathlib import Path

from ..models.runtime import RuntimeStoreError


class BlobStore:
    """클래스 이름: BlobStore
    기능: BlobStore 기능을 정의한다.
    작성 날짜: 2026/11/06
    """

    def __init__(self, root: Path) -> None:
        """함수 이름: __init__()
        기능: __init__ 기능을 수행한다.
        인자: root
        반환값: None
        작성 날짜: 2026/11/06
        """
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def write(
        self, workspace_id: str, session_id: str, pointer_id: str, content: bytes
    ) -> tuple[Path, str]:
        """함수 이름: write()
        기능: write 기능을 수행한다.
        인자: workspace_id, session_id, pointer_id, content
        반환값: tuple[Path, str]
        작성 날짜: 2026/11/06
        """
        target_dir = self._root / workspace_id / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{pointer_id}.blob"
        checksum = hashlib.sha256(content).hexdigest()
        fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=target_dir)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, target)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return target, checksum

    def read(self, path: Path) -> bytes:
        """함수 이름: read()
        기능: read 기능을 수행한다.
        인자: path
        반환값: bytes
        작성 날짜: 2026/11/06
        """
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeStoreError("RUNTIME_BLOB_MISSING") from exc

    def delete(self, path: Path) -> None:
        """함수 이름: delete()
        기능: delete 기능을 수행한다.
        인자: path
        반환값: None
        작성 날짜: 2026/11/06
        """
        path.unlink(missing_ok=True)

    def remove_session(self, workspace_id: str, session_id: str) -> None:
        """함수 이름: remove_session()
        기능: remove_session 기능을 수행한다.
        인자: workspace_id, session_id
        반환값: None
        작성 날짜: 2026/11/06
        """
        target = self._root / workspace_id / session_id
        if not target.exists():
            return
        for child in target.iterdir():
            child.unlink(missing_ok=True)
        target.rmdir()
