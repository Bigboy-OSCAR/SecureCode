from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SOURCE_URI_RE = re.compile(r"^source://(?P<kind>[a-z]+)/(?P<path>.+)$")


def _load_manifest(work_dir: Path) -> dict[str, Any]:
    return json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))


def compact_catalog(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = []
    for item in manifest["sources"]:
        catalog.append(
            {
                "pointer": item["pointer"],
                "kind": item["kind"],
                "bytes": item["bytes"],
                "tools": item["tools"],
                "hints": item["hints"],
            }
        )
    return catalog


def source_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["pointer"]: item for item in manifest["sources"]}


def resolve_pointer(work_dir: Path, manifest: dict[str, Any], pointer: str) -> Path:
    if not SOURCE_URI_RE.match(pointer):
        raise ValueError(f"invalid source pointer: {pointer}")
    sources_root = (work_dir / "sources").resolve()
    item = source_map(manifest).get(pointer)
    if item is None:
        raise KeyError(f"unknown source pointer: {pointer}")
    path = (sources_root / item["rel_path"]).resolve()
    if sources_root not in [path, *path.parents]:
        raise ValueError(f"source path escapes sources root: {pointer}")
    return path


def read_source(work_dir: Path, manifest: dict[str, Any], pointer: str) -> str:
    return resolve_pointer(work_dir, manifest, pointer).read_text(encoding="utf-8")


def grep_log(
    work_dir: Path,
    manifest: dict[str, Any],
    pointer: str,
    pattern: str,
    before: int = 1,
    after: int = 1,
    max_matches: int = 6,
) -> str:
    path = resolve_pointer(work_dir, manifest, pointer)
    regex = re.compile(pattern)
    lines = path.read_text(encoding="utf-8").splitlines()
    matched = [idx for idx, line in enumerate(lines) if regex.search(line)]
    if not matched:
        return f"No log lines matched pattern: {pattern}"

    selected: list[int] = []
    for idx in matched[:max_matches]:
        selected.extend(range(max(0, idx - before), min(len(lines), idx + after + 1)))
    selected = sorted(set(selected))
    return "\n".join(f"{line_no + 1:06d}: {lines[line_no]}" for line_no in selected)


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def extract_doc_section(work_dir: Path, manifest: dict[str, Any], pointer: str, query: str) -> str:
    text = read_source(work_dir, manifest, pointer)
    sections: list[tuple[str, list[str]]] = []
    current_heading = "document"
    current_lines: list[str] = []
    for line in text.splitlines():
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


def extract_json_field(work_dir: Path, manifest: dict[str, Any], pointer: str, path: str) -> str:
    value = json.loads(read_source(work_dir, manifest, pointer))
    selected = _walk_json_path(value, path)
    return json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True)


def run_tool(work_dir: Path, manifest: dict[str, Any], tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "grep_log":
        return grep_log(
            work_dir,
            manifest,
            pointer=str(args["pointer"]),
            pattern=str(args["pattern"]),
            before=int(args.get("before", 1)),
            after=int(args.get("after", 1)),
            max_matches=int(args.get("max_matches", 6)),
        )
    if tool_name == "extract_doc_section":
        return extract_doc_section(work_dir, manifest, pointer=str(args["pointer"]), query=str(args["query"]))
    if tool_name == "extract_json_field":
        return extract_json_field(work_dir, manifest, pointer=str(args["pointer"]), path=str(args["path"]))
    raise ValueError(f"unknown source pointer tool: {tool_name}")
