from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .make_runtime_data import serialize_runtime_value


RUNTIME_URI_RE = re.compile(r"^runtime://(?P<kind>[a-z]+)/(?P<producer>[a-z_]+)/(?P<id>[0-9]{4})(?P<path>/.*)?$")


@dataclass(frozen=True)
class RuntimeObject:
    pointer: str
    producer: str
    kind: str
    tools: list[str]
    hints: list[str]
    value: Any

    @property
    def bytes(self) -> int:
        return len(serialize_runtime_value(self.value).encode("utf-8"))


class RuntimeStore:
    def __init__(self) -> None:
        self._counter = 0
        self._objects: dict[str, RuntimeObject] = {}

    def put(self, producer: str, kind: str, value: Any, tools: list[str], hints: list[str]) -> RuntimeObject:
        self._counter += 1
        pointer = f"runtime://{kind}/{producer}/{self._counter:04d}"
        item = RuntimeObject(pointer=pointer, producer=producer, kind=kind, tools=tools, hints=hints, value=value)
        self._objects[pointer] = item
        return item

    def resolve(self, pointer: str) -> Any:
        match = RUNTIME_URI_RE.match(pointer)
        if not match:
            raise ValueError(f"invalid runtime pointer: {pointer}")
        base_pointer = f"runtime://{match.group('kind')}/{match.group('producer')}/{match.group('id')}"
        item = self._objects.get(base_pointer)
        if item is None:
            raise KeyError(f"unknown runtime pointer: {pointer}")
        value = item.value
        path = match.group("path")
        if not path:
            return value
        for part in [part for part in path.split("/") if part]:
            if isinstance(value, list):
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value[part]
            else:
                raise KeyError(f"cannot descend into {type(value).__name__} at {part}")
        return value

    def catalog(self) -> list[dict[str, Any]]:
        catalog = []
        for item in self._objects.values():
            catalog.append(
                {
                    "pointer": item.pointer,
                    "producer": item.producer,
                    "kind": item.kind,
                    "bytes": item.bytes,
                    "tools": item.tools,
                    "hints": item.hints,
                }
            )
        return catalog


def grep_runtime_log(
    store: RuntimeStore,
    pointer: str,
    pattern: str,
    before: int = 1,
    after: int = 1,
    max_matches: int = 6,
) -> str:
    value = store.resolve(pointer)
    if not isinstance(value, str):
        raise TypeError("grep_runtime_log expects a string runtime object")
    regex = re.compile(pattern)
    lines = value.splitlines()
    matched = [idx for idx, line in enumerate(lines) if regex.search(line)]
    if not matched:
        return f"No runtime log lines matched pattern: {pattern}"

    selected: list[int] = []
    for idx in matched[:max_matches]:
        selected.extend(range(max(0, idx - before), min(len(lines), idx + after + 1)))
    selected = sorted(set(selected))
    return "\n".join(f"{line_no + 1:06d}: {lines[line_no]}" for line_no in selected)


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def extract_runtime_doc_section(store: RuntimeStore, pointer: str, query: str) -> str:
    value = store.resolve(pointer)
    if not isinstance(value, str):
        raise TypeError("extract_runtime_doc_section expects a string runtime object")
    sections: list[tuple[str, list[str]]] = []
    current_heading = "document"
    current_lines: list[str] = []
    for line in value.splitlines():
        if line.startswith("## "):
            sections.append((current_heading, current_lines))
            current_heading = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    sections.append((current_heading, current_lines))

    normalized_query = _normalize_heading(query)
    query_terms = set(normalized_query.split())

    def score(heading: str) -> tuple[int, int]:
        normalized_heading = _normalize_heading(heading)
        if normalized_heading == normalized_query:
            return (10_000, len(normalized_heading))
        overlap = len(query_terms & set(normalized_heading.split()))
        contains = int(normalized_query in normalized_heading or normalized_heading in normalized_query)
        return (overlap * 10 + contains * 100, len(normalized_heading))

    heading, lines = max(sections, key=lambda section: score(section[0]))
    return f"Selected section: {heading}\n" + "\n".join(lines).strip()


def _walk_json_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            if "," in part:
                keys = [key.strip() for key in part.split(",") if key.strip()]
                return {key: current[key] for key in keys}
            current = current[part]
        else:
            raise KeyError(f"cannot descend into {type(current).__name__} at {part}")
    return current


def extract_runtime_json_path(store: RuntimeStore, pointer: str, path: str) -> str:
    value = store.resolve(pointer)
    selected = _walk_json_path(value, path)
    return json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True)


def run_runtime_tool(store: RuntimeStore, tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "grep_runtime_log":
        return grep_runtime_log(
            store,
            pointer=str(args["pointer"]),
            pattern=str(args["pattern"]),
            before=int(args.get("before", 1)),
            after=int(args.get("after", 1)),
            max_matches=int(args.get("max_matches", 6)),
        )
    if tool_name == "extract_runtime_doc_section":
        return extract_runtime_doc_section(store, pointer=str(args["pointer"]), query=str(args["query"]))
    if tool_name == "extract_runtime_json_path":
        return extract_runtime_json_path(store, pointer=str(args["pointer"]), path=str(args["path"]))
    raise ValueError(f"unknown runtime pointer tool: {tool_name}")
