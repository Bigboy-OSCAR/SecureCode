"""Runtime Pointer 저장소: 세션 범위의 저장(스트리밍)·stat·목록·삭제·세션 정리·TTL sweep·재시작 복구.

메타데이터는 SQLite, 원문은 객체별 blob 파일이다. 부분 읽기·검색은 reads.py(RuntimeReader)가 한다.
"""

import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from securecode_context.pointers.models.runtime import (
    BOUNDED_READ_ORIGINS,
    InvalidSelector,
    NotStorable,
    PointerExpired,
    PointerNotFound,
    QuotaExceeded,
    RuntimeDescriptor,
    RuntimePut,
    ScopeForbidden,
)
from securecode_context.pointers.runtime.blob import BlobWriter, blob_path
from securecode_context.pointers.runtime.db import (
    MAX_PREVIEW_BYTES,
    MAX_SESSION_BYTES,
    TOMBSTONE_DAYS,
    open_connection,
    transaction,
    utc_now,
)
from securecode_context.pointers.runtime.listing import descriptor_of, list_page
from securecode_context.pointers.runtime.recovery import RecoveryReport, recover
from securecode_context.pointers.runtime.removal import remove_where
from securecode_context.pointers.runtime.writer import RuntimeWriter
from securecode_context.pointers.text.caps import decode_prefix

_SCOPE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
MAX_TTL_SECONDS = 7 * 24 * 60 * 60


def check_scope(workspace_id: str, session_id: str) -> None:
    """
    함수 이름: check_scope()
    기능: 범위 값이 경로 요소로 안전한지 매번 확인한다.
    인자: workspace_id/session_id -> 범위
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if not all(_SCOPE.fullmatch(value) for value in (workspace_id, session_id)):
        raise ScopeForbidden("workspace_id와 session_id 형식이 올바르지 않습니다", "invalid_scope")


class RuntimeStore:
    """
    클래스 이름: RuntimeStore
    기능: 세션 범위 Runtime 저장소. 같은 DB를 여러 인스턴스가 써도 용량 검사는 쓰기 잠금 안에서 한다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, root: Path | None = None) -> None:
        """
        함수 이름: __init__()
        기능: DB와 blob 폴더를 열고 재시작 정합성 복구를 한 번 실행한다.
        인자: root -> 저장 폴더(기본 .securecode/runtime)
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.root = root or Path(".securecode/runtime")
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._connection = open_connection(self.root / "runtime.sqlite3")
        self.last_recovery: RecoveryReport = recover(self._connection, self._lock, self.blobs)

    def open_writer(self, request: RuntimePut) -> RuntimeWriter:
        """
        함수 이름: open_writer()
        기능: 범위·origin·TTL을 검사하고 저장 예약 행을 만든 뒤 스트리밍 writer를 돌려준다.
        인자: request -> 저장 요청(content는 쓰지 않는다)
        반환값: RuntimeWriter
        작성 날짜: 2026/11/10
        """
        check_scope(request.workspace_id, request.session_id)
        if request.origin in BOUNDED_READ_ORIGINS:
            raise NotStorable("제한된 읽기 결과는 다시 포인터로 저장하지 않습니다", "bounded_read")
        if not 1 <= request.ttl_seconds <= MAX_TTL_SECONDS:
            raise InvalidSelector("TTL은 1초~7일이어야 합니다", "invalid_ttl")
        pointer_id = str(uuid.uuid4())
        now = utc_now()
        expires = now + timedelta(seconds=request.ttl_seconds)
        target = blob_path(self.blobs, request.workspace_id, request.session_id, pointer_id)
        with self._lock, transaction(self._connection):
            self._connection.execute(
                "INSERT INTO runtime_pointers VALUES (?, ?, ?, 'pending', ?, 0, '', x'', ?, ?, ?, ?, '')",
                (
                    pointer_id, request.workspace_id, request.session_id, request.media_type,
                    request.origin, int(request.truncated_before_storage),
                    now.isoformat(), expires.isoformat(),
                ),
            )  # fmt: skip
        try:
            blob = BlobWriter(target)
        except Exception:
            self._discard_row(pointer_id)
            raise
        discard = lambda writer: self._discard_row(writer.pointer_id)  # noqa: E731
        return RuntimeWriter(pointer_id, blob, self._finish, discard)

    def put(self, request: RuntimePut) -> RuntimeDescriptor:
        """
        함수 이름: put()
        기능: 메모리에 있는 본문을 스트리밍 writer로 저장한다.
        인자: request -> 저장 요청
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/10
        """
        with self.open_writer(request) as writer:
            for start in range(0, len(request.content), 1024 * 1024):
                writer.write(request.content[start : start + 1024 * 1024])
            return writer.commit()

    def _finish(self, writer: RuntimeWriter) -> RuntimeDescriptor:
        """
        함수 이름: _finish()
        기능: blob을 확정하고 쓰기 잠금 안에서 세션 합계를 다시 세어 넘으면 거절·정리, 아니면 ready로 바꾼다.
        인자: writer -> 완료할 writer
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/10
        """
        checksum, digests = writer.blob.commit()
        preview, _ = decode_prefix(writer.blob.head[:MAX_PREVIEW_BYTES], False, 0)
        size = writer.blob.size
        try:
            with self._lock, transaction(self._connection):
                row = self._connection.execute(
                    "SELECT workspace_id, session_id FROM runtime_pointers WHERE pointer_id = ?",
                    (writer.pointer_id,),
                ).fetchone()
                used = self._connection.execute(
                    "SELECT COALESCE(SUM(byte_size), 0) FROM runtime_pointers "
                    "WHERE workspace_id = ? AND session_id = ? AND state = 'ready'",
                    (row["workspace_id"], row["session_id"]),
                ).fetchone()[0]
                if int(used) + size > MAX_SESSION_BYTES:
                    raise QuotaExceeded("세션 용량 한도를 초과했습니다", "session_limit")
                self._connection.execute(
                    "UPDATE runtime_pointers SET state = 'ready', byte_size = ?, checksum = ?, "
                    "chunk_digests = ?, preview = ? WHERE pointer_id = ?",
                    (size, checksum, digests, preview, writer.pointer_id),
                )
        except BaseException:
            writer.blob.target.unlink(missing_ok=True)
            self._discard_row(writer.pointer_id)
            raise
        return self.stat(row["workspace_id"], row["session_id"], writer.pointer_id)

    def _discard_row(self, pointer_id: str) -> None:
        """
        함수 이름: _discard_row()
        기능: pending 행 하나를 지운다.
        인자: pointer_id -> 예약 ID
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        with self._lock, transaction(self._connection):
            self._connection.execute(
                "DELETE FROM runtime_pointers WHERE pointer_id = ? AND state = 'pending'",
                (pointer_id,),
            )

    def load(self, workspace_id: str, session_id: str, pointer_id: str) -> Any:
        """
        함수 이름: load()
        기능: 범위가 맞는 ready 행을 읽는다. 없으면 tombstone 사유로 EXPIRED/NOT_FOUND를 구분한다.
        인자: workspace_id/session_id -> 범위, pointer_id -> UUID
        반환값: sqlite3.Row
        작성 날짜: 2026/11/10
        """
        check_scope(workspace_id, session_id)
        if not _UUID.fullmatch(pointer_id):
            raise PointerNotFound("포인터를 찾을 수 없습니다", "unknown")
        scope = (pointer_id, workspace_id, session_id)
        row = self._connection.execute(
            "SELECT * FROM runtime_pointers WHERE pointer_id = ? AND workspace_id = ? "
            "AND session_id = ? AND state = 'ready'",
            scope,
        ).fetchone()
        if row is None:
            gone = self._connection.execute(
                "SELECT reason FROM runtime_tombstones WHERE pointer_id = ? AND workspace_id = ? "
                "AND session_id = ?",
                scope,
            ).fetchone()
            if gone is not None and gone["reason"] == "expired":
                raise PointerExpired("포인터가 만료되었습니다", "expired")
            raise PointerNotFound(
                "포인터를 찾을 수 없습니다", gone["reason"] if gone else "unknown"
            )
        if datetime.fromisoformat(row["expires_at"]) <= utc_now():
            raise PointerExpired("포인터가 만료되었습니다", "expired")
        return row

    def stat(self, workspace_id: str, session_id: str, pointer_id: str) -> RuntimeDescriptor:
        """
        함수 이름: stat()
        기능: 범위·만료를 확인한 descriptor를 돌려준다.
        인자: workspace_id/session_id -> 범위, pointer_id -> UUID
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/10
        """
        return descriptor_of(self.load(workspace_id, session_id, pointer_id))

    def list_pointers(
        self, workspace_id: str, session_id: str, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]:
        """
        함수 이름: list_pointers()
        기능: 만료 전 ready 포인터를 ID 순으로 최대 100개, 응답 64 KiB 이하로 돌려준다.
        인자: workspace_id/session_id -> 범위, limit -> 1~100, cursor -> 직전 마지막 ID
        반환값: items·has_more·next_cursor·truncated_by_bytes
        작성 날짜: 2026/11/10
        """
        check_scope(workspace_id, session_id)
        if cursor is not None and not _UUID.fullmatch(cursor):
            raise InvalidSelector("목록 cursor가 올바르지 않습니다", "invalid_page")
        return list_page(self._connection, (workspace_id, session_id), limit, cursor)

    def delete(self, workspace_id: str, session_id: str, pointer_id: str) -> None:
        """
        함수 이름: delete()
        기능: 범위가 맞는 blob과 행만 지운다. 다시 불러도 같은 결과다.
        인자: workspace_id/session_id -> 범위, pointer_id -> UUID
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        check_scope(workspace_id, session_id)
        self._remove("pointer_id = ? AND workspace_id = ? AND session_id = ?",
                     (pointer_id, workspace_id, session_id), "deleted")  # fmt: skip

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        """
        함수 이름: clear_session()
        기능: 세션 종료 정책. 그 세션의 모든 ready 출력을 지우고 빈 폴더를 정리한다.
        인자: workspace_id/session_id -> 범위
        반환값: 지운 개수
        작성 날짜: 2026/11/10
        """
        check_scope(workspace_id, session_id)
        count = self._remove("workspace_id = ? AND session_id = ? AND state = 'ready'",
                             (workspace_id, session_id), "session_cleared")  # fmt: skip
        session_dir = self.blobs / workspace_id / session_id
        if session_dir.is_dir() and not any(session_dir.iterdir()):
            session_dir.rmdir()
        return count

    def sweep_expired(self) -> int:
        """
        함수 이름: sweep_expired()
        기능: TTL이 지난 출력을 지우고 7일 지난 tombstone을 정리한다(세션 종료 정책과 별개).
        인자: 없음
        반환값: 지운 출력 수
        작성 날짜: 2026/11/10
        """
        now = utc_now()
        count = self._remove("state = 'ready' AND expires_at <= ?", (now.isoformat(),), "expired")
        old = (now - timedelta(days=TOMBSTONE_DAYS)).isoformat()
        with self._lock, transaction(self._connection):
            self._connection.execute("DELETE FROM runtime_tombstones WHERE removed_at < ?", (old,))
        return count

    def _remove(self, where: str, params: tuple[str, ...], reason: str) -> int:
        """
        함수 이름: _remove()
        기능: 조건에 맞는 ready 행을 tombstone으로 바꾸고 blob을 지운다.
        인자: where/params -> 조건, reason -> tombstone 사유
        반환값: 지운 개수
        작성 날짜: 2026/11/10
        """
        return remove_where(self._connection, self._lock, self.blobs, (where, params), reason)

    def close(self) -> None:
        """
        함수 이름: close()
        기능: DB 연결을 닫는다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._connection.close()
