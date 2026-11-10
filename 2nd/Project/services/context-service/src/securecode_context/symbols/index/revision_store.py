"""작업 공간별 불변 revision 파일과 현재 revision 포인터를 원자적으로 저장한다."""

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast

from securecode_context.common.errors import ErrorCode, ServiceError

from .records import RECORD_FORMAT_VERSION, IndexRevisionRecord

_WORKSPACE_ID = re.compile(r"^ws_[A-Za-z0-9-]{8,64}$")
_REVISION_FILE = re.compile(r"^(\d+)\.json$")
_CURRENT_FILE = "current.json"


class RevisionStoreError(RuntimeError):
    """
    클래스 이름: RevisionStoreError
    기능: 저장된 revision이 손상됐거나 다른 작업 공간의 기록과 섞였음을 표시한다.
    작성 날짜: 2026/11/05
    """


# Windows: os.replace와 읽기가 겹치면 공유 위반이 PermissionError로 난다(3.6에서 재현). 잠깐 다시 시도한다.
_SHARING_RETRIES = 50
_SHARING_DELAY_SECONDS = 0.01


def _retry_sharing[T](action: Callable[[], T]) -> T:
    """
    함수 이름: _retry_sharing()
    기능: 다른 스레드의 교체·읽기와 겹친 PermissionError만 짧게 다시 시도한다(최대 약 0.5초).
    인자: action -> 파일 읽기 또는 교체
    반환값: action 결과
    작성 날짜: 2026/11/10
    """
    for _attempt in range(_SHARING_RETRIES - 1):
        try:
            return action()
        except PermissionError:
            time.sleep(_SHARING_DELAY_SECONDS)
    return action()


def _read_json(path: Path) -> Any:
    """
    함수 이름: _read_json()
    기능: JSON 파일을 읽는다. 교체 중 공유 위반은 다시 시도한다.
    인자: path -> 파일 경로
    반환값: JSON 값
    작성 날짜: 2026/11/10
    """
    return json.loads(_retry_sharing(lambda: path.read_text(encoding="utf-8")))


def _write_atomic(path: Path, value: object) -> None:
    """
    함수 이름: _write_atomic()
    기능: 같은 디렉터리의 임시 파일에 완성된 JSON을 쓰고 fsync 후 rename으로 교체한다.
    인자: path -> 최종 경로, value -> JSON 값
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".tmp-", delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            json.dump(value, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        source = temp_path
        _retry_sharing(lambda: os.replace(source, path))
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class RevisionStore:
    """
    클래스 이름: RevisionStore
    기능: <base>/<workspace_id>/symbols/revisions/<n>.json에 불변 기록을 쓰고 current.json으로 전환한다.
        독자는 current.json이 가리키는 완성 파일만 읽으므로 이전·새 revision이 섞이지 않는다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, base_dir: Path, keep_revisions: int = 2) -> None:
        """
        함수 이름: __init__()
        기능: 저장 루트와 보존할 revision 수를 정한다.
        인자: base_dir -> 작업 공간 데이터 루트(.securecode/workspaces), keep_revisions -> 보존 개수
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.base_dir = base_dir.resolve()
        self.keep_revisions = max(1, keep_revisions)

    def symbols_dir(self, workspace_id: str) -> Path:
        """
        함수 이름: symbols_dir()
        기능: 형식을 검사한 작업 공간 ID로만 저장 경로를 만들어 경로 이탈을 막는다.
        인자: workspace_id -> ws_ 접두사 ID
        반환값: 작업 공간의 symbols 디렉터리
        작성 날짜: 2026/11/05
        """
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ServiceError(
                ErrorCode.VALIDATION_FAILED, "작업 공간 ID 형식이 올바르지 않습니다."
            )
        return self.base_dir / workspace_id / "symbols"

    def current_revision(self, workspace_id: str) -> int | None:
        """
        함수 이름: current_revision()
        기능: 검색에 제공 중인 revision 번호를 읽는다.
        인자: workspace_id -> 작업 공간
        반환값: revision 번호, 아직 없으면 None
        작성 날짜: 2026/11/05
        """
        path = self.symbols_dir(workspace_id) / _CURRENT_FILE
        try:
            pointer = _read_json(path)
        except FileNotFoundError:
            return None
        revision = pointer.get("index_revision")
        if not isinstance(revision, int) or revision < 1:
            raise RevisionStoreError("current revision pointer is corrupted")
        return revision

    def next_revision(self, workspace_id: str) -> int:
        """
        함수 이름: next_revision()
        기능: 현재 포인터와 남은 파일 중 가장 큰 번호 다음 값을 돌려줘 번호를 재사용하지 않는다.
        인자: workspace_id -> 작업 공간
        반환값: 새 revision 번호
        작성 날짜: 2026/11/05
        """
        numbers = [self.current_revision(workspace_id) or 0]
        numbers.extend(self._stored_numbers(workspace_id))
        return max(numbers) + 1

    def load(self, workspace_id: str, revision: int) -> IndexRevisionRecord:
        """
        함수 이름: load()
        기능: 불변 revision 파일을 읽고 작업 공간·번호·형식 버전이 요청과 같은지 확인한다.
        인자: workspace_id -> 작업 공간, revision -> 번호
        반환값: IndexRevisionRecord
        작성 날짜: 2026/11/05
        """
        path = self._revision_path(workspace_id, revision)
        record = cast(dict[str, Any], _read_json(path))
        if (
            record.get("workspace_id") != workspace_id
            or record.get("index_revision") != revision
            or record.get("format_version") != RECORD_FORMAT_VERSION
        ):
            raise RevisionStoreError("revision record does not match its location")
        return cast(IndexRevisionRecord, record)

    def publish(self, record: IndexRevisionRecord) -> None:
        """
        함수 이름: publish()
        기능: 새 revision 파일을 완성한 뒤에만 current.json을 교체하고 오래된 파일을 정리한다.
        인자: record -> 완성된 새 revision 기록
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        workspace_id = record["workspace_id"]
        revision = record["index_revision"]
        if revision < self.next_revision(workspace_id):
            raise RevisionStoreError("revision number already used")
        path = self._revision_path(workspace_id, revision)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, record)
        _write_atomic(
            self.symbols_dir(workspace_id) / _CURRENT_FILE,
            {"index_revision": revision, "published_at": record["created_at"]},
        )
        self._prune(workspace_id, revision)

    def _revision_path(self, workspace_id: str, revision: int) -> Path:
        """
        함수 이름: _revision_path()
        기능: revision 번호를 파일 경로로 바꾼다.
        인자: workspace_id -> 작업 공간, revision -> 1 이상의 번호
        반환값: revision JSON 경로
        작성 날짜: 2026/11/05
        """
        if revision < 1:
            raise ValueError("revision must be positive")
        return self.symbols_dir(workspace_id) / "revisions" / f"{revision}.json"

    def _stored_numbers(self, workspace_id: str) -> list[int]:
        """
        함수 이름: _stored_numbers()
        기능: 디스크에 남아 있는 완성 revision 파일 번호를 나열한다.
        인자: workspace_id -> 작업 공간
        반환값: 번호 목록
        작성 날짜: 2026/11/05
        """
        directory = self.symbols_dir(workspace_id) / "revisions"
        if not directory.is_dir():
            return []
        return [
            int(match.group(1))
            for entry in directory.iterdir()
            if (match := _REVISION_FILE.fullmatch(entry.name))
        ]

    def _prune(self, workspace_id: str, current: int) -> None:
        """
        함수 이름: _prune()
        기능: 현재 revision을 포함해 최근 keep_revisions개만 남기고 이전 파일을 삭제한다.
        인자: workspace_id -> 작업 공간, current -> 방금 전환한 번호
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        keep = set(sorted(self._stored_numbers(workspace_id))[-self.keep_revisions :])
        keep.add(current)
        for number in self._stored_numbers(workspace_id):
            if number not in keep:
                self._revision_path(workspace_id, number).unlink(missing_ok=True)
