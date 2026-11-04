import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SourceItem:
    path: Path
    workspace_id: str
    fingerprint: str


class SourceStore:
    def __init__(self, root_dir: str):
        self.root = Path(root_dir).resolve()
        self.items: dict[str, SourceItem] = {}

    def register(self, relative_path: str, workspace_id: str) -> str:
        path = (self.root / relative_path).resolve()

        if not path.is_file():
            raise FileNotFoundError("source file not found")

        if self.root not in path.parents:
            raise PermissionError("path escapes workspace root")

        source_id = self._make_source_id(workspace_id, relative_path)
        fingerprint = self._make_fingerprint(path)

        self.items[source_id] = SourceItem(
            path=path,
            workspace_id=workspace_id,
            fingerprint=fingerprint,
        )

        return source_id

    def read(
        self,
        source_id: str,
        workspace_id: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
        max_bytes: int = 32 * 1024,
    ) -> str:
        item = self._get_valid_item(source_id, workspace_id)

        with item.path.open("rb") as file:
            content = file.read(max_bytes)

        text = content.decode("utf-8", errors="ignore")
        lines = text.splitlines()

        if end_line is None:
            end_line = len(lines)

        selected_lines = lines[start_line - 1:end_line]
        return "\n".join(selected_lines)

    def unregister(self, source_id: str, workspace_id: str) -> bool:
        item = self.items.get(source_id)

        if item is None:
            return False

        if item.workspace_id != workspace_id:
            return False

        del self.items[source_id]
        return True

    def _get_valid_item(self, source_id: str, workspace_id: str) -> SourceItem:
        item = self.items.get(source_id)

        if item is None:
            raise KeyError("source pointer not found")

        if item.workspace_id != workspace_id:
            raise PermissionError("workspace scope mismatch")

        current_fingerprint = self._make_fingerprint(item.path)

        if current_fingerprint != item.fingerprint:
            raise ValueError("source file changed")

        return item

    def _make_source_id(self, workspace_id: str, relative_path: str) -> str:
        raw = f"{workspace_id}:{relative_path}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _make_fingerprint(self, path: Path) -> str:
        stat = path.stat()
        raw = f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
        return hashlib.sha256(raw.encode()).hexdigest()
