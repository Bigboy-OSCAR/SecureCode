"""메모리 기반 세션별 Runtime Pointer 저장소."""

import time
import uuid
from dataclasses import dataclass
from threading import RLock

from securecode_context.pointers.limits import (
    DEFAULT_TTL_SECONDS,
    MAX_READ_BYTES,
    check_read_limit,
    check_ttl,
    utf8_prefix,
)


@dataclass(frozen=True)
class RuntimeItem:
    """클래스 이름: RuntimeItem
    기능: 한 세션에서 생성한 원문과 수명 정보를 담는다.
    작성 날짜: 2026/11/05
    """

    content: str
    workspace_id: str
    session_id: str
    created_at: float
    expires_at: float


class RuntimeStore:
    """클래스 이름: RuntimeStore
    기능: 작업 공간·세션 권한을 확인한 뒤 런타임 결과를 읽고 정리한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, default_ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        """함수 이름: __init__()
        기능: 빈 저장소와 세션 작업을 보호하는 잠금을 만든다.
        인자: default_ttl_seconds -> 기본 수명(초)
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        check_ttl(default_ttl_seconds)
        self.items: dict[str, RuntimeItem] = {}
        self.default_ttl_seconds = default_ttl_seconds
        self._lock = RLock()
        self._sweep_at = 0.0

    def put(
        self,
        content: str,
        workspace_id: str,
        session_id: str,
        ttl_seconds: int | None = None,
    ) -> str:
        """함수 이름: put()
        기능: 현재 세션에 새 원문을 저장한다.
        인자: content -> 원문, workspace_id/session_id -> 범위, ttl_seconds -> 수명
        반환값: 새 런타임 ID
        작성 날짜: 2026/11/05
        """
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        check_ttl(ttl)
        pointer_id = str(uuid.uuid4())
        with self._lock:
            now = time.time()
            if now >= self._sweep_at:
                self._remove_expired(now)
                self._sweep_at = now + 60
            self.items[pointer_id] = RuntimeItem(content, workspace_id, session_id, now, now + ttl)
        return pointer_id

    def read(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
        max_bytes: int = MAX_READ_BYTES,
    ) -> str:
        """함수 이름: read()
        기능: 범위와 만료를 확인한 뒤 UTF-8 경계까지 반환한다.
        인자: pointer_id -> ID, workspace_id/session_id -> 범위, max_bytes -> 바이트 상한
        반환값: 원문의 앞부분
        작성 날짜: 2026/11/05
        """
        check_read_limit(max_bytes)
        with self._lock:
            item = self.items.get(pointer_id)
            if item is None:
                raise KeyError("runtime pointer not found")
            if item.workspace_id != workspace_id or item.session_id != session_id:
                raise PermissionError("pointer scope mismatch")
            if time.time() >= item.expires_at:
                del self.items[pointer_id]
                raise TimeoutError("runtime pointer expired")
            return utf8_prefix(item.content[:max_bytes].encode()[:max_bytes])[0]

    def list(self, workspace_id: str, session_id: str) -> list[str]:
        """함수 이름: list()
        기능: 만료 항목을 정리하고 현재 세션의 ID를 가져온다.
        인자: workspace_id/session_id -> 범위
        반환값: ID 목록
        작성 날짜: 2026/11/05
        """
        with self._lock:
            self._remove_expired(time.time())
            return [
                pid
                for pid, item in self.items.items()
                if item.workspace_id == workspace_id and item.session_id == session_id
            ]

    def delete(self, pointer_id: str, workspace_id: str, session_id: str) -> bool:
        """함수 이름: delete()
        기능: 범위가 일치하는 항목만 삭제한다.
        인자: pointer_id -> ID, workspace_id/session_id -> 범위
        반환값: 삭제 성공 여부
        작성 날짜: 2026/11/05
        """
        with self._lock:
            item = self.items.get(pointer_id)
            if item is None or item.workspace_id != workspace_id or item.session_id != session_id:
                return False
            del self.items[pointer_id]
            return True

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        """함수 이름: clear_session()
        기능: 하나의 임계 영역에서 세션 항목을 정리한다.
        인자: workspace_id/session_id -> 범위
        반환값: 삭제한 항목 수
        작성 날짜: 2026/11/05
        """
        with self._lock:
            pointer_ids = self.list(workspace_id, session_id)
            for pointer_id in pointer_ids:
                del self.items[pointer_id]
            return len(pointer_ids)

    def _remove_expired(self, now: float) -> None:
        """함수 이름: _remove_expired()
        기능: 잠금을 보유한 호출자가 만료된 원문을 정리한다.
        인자: now -> 현재 시각
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        for pointer_id in [pid for pid, item in self.items.items() if now >= item.expires_at]:
            del self.items[pointer_id]
