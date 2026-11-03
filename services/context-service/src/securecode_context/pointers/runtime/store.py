import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeItem:
    content: str
    workspace_id: str
    session_id: str
    created_at: float
    expires_at: float


class RuntimeStore:
    def __init__(self, default_ttl_seconds: int = 60 * 60 * 24):
        self.items: dict[str, RuntimeItem] = {}
        self.default_ttl_seconds = default_ttl_seconds

    def put(
        self,
        content: str,
        workspace_id: str,
        session_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> str:
        pointer_id = str(uuid.uuid4())
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        self.items[pointer_id] = RuntimeItem(
            content=content,
            workspace_id=workspace_id,
            session_id=session_id,
            created_at=now,
            expires_at=now + ttl,
        )

        return pointer_id

    def read(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
        max_bytes: int = 32 * 1024,
    ) -> str:
        item = self._get_valid_item(pointer_id, workspace_id, session_id)
        encoded = item.content.encode("utf-8")

        if len(encoded) <= max_bytes:
            return item.content

        return encoded[:max_bytes].decode("utf-8", errors="ignore")

    def list(self, workspace_id: str, session_id: str) -> list[str]:
        self._remove_expired()
        return [
            pointer_id
            for pointer_id, item in self.items.items()
            if item.workspace_id == workspace_id
            and item.session_id == session_id
        ]

    def delete(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
    ) -> bool:
        item = self.items.get(pointer_id)

        if item is None:
            return False

        if item.workspace_id != workspace_id:
            return False

        if item.session_id != session_id:
            return False

        del self.items[pointer_id]
        return True

    def clear_session(self, workspace_id: str, session_id: str) -> int:
        pointer_ids = self.list(workspace_id, session_id)

        for pointer_id in pointer_ids:
            del self.items[pointer_id]

        return len(pointer_ids)

    def _get_valid_item(
        self,
        pointer_id: str,
        workspace_id: str,
        session_id: str,
    ) -> RuntimeItem:
        item = self.items.get(pointer_id)

        if item is None:
            raise KeyError("runtime pointer not found")

        if item.workspace_id != workspace_id:
            raise PermissionError("workspace scope mismatch")

        if item.session_id != session_id:
            raise PermissionError("session scope mismatch")

        if time.time() > item.expires_at:
            del self.items[pointer_id]
            raise TimeoutError("runtime pointer expired")

        return item

    def _remove_expired(self) -> None:
        now = time.time()
        expired_ids = [
            pointer_id
            for pointer_id, item in self.items.items()
            if now > item.expires_at
        ]

        for pointer_id in expired_ids:
            del self.items[pointer_id]
