from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SYMBOL_URI_RE = re.compile(r"^memory://symbol/(?P<path>.+)::(?P<qualname>[A-Za-z_][\w.]*)$")


@dataclass(frozen=True)
class Symbol:
    path: str
    kind: str
    name: str
    qualname: str
    start_line: int
    end_line: int
    uri: str


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.stack: list[str] = []
        self.symbols: list[Symbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._record(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record(node, "async_function")

    def _record(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name")
        qualname = ".".join([*self.stack, name])
        start_line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", start_line))
        uri = f"memory://symbol/{self.rel_path}::{qualname}"
        self.symbols.append(
            Symbol(
                path=self.rel_path,
                kind=kind,
                name=name,
                qualname=qualname,
                start_line=start_line,
                end_line=end_line,
                uri=uri,
            )
        )
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()


def build_index(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files: list[dict[str, Any]] = []
    all_symbols: list[dict[str, Any]] = []

    for path in sorted(root.rglob("*.py")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        rel_path = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        visitor = _SymbolVisitor(rel_path)
        visitor.visit(tree)
        symbols = [asdict(symbol) for symbol in visitor.symbols]
        files.append({"path": rel_path, "symbols": symbols})
        all_symbols.extend(symbols)

    return {
        "version": 1,
        "root": str(root),
        "files": files,
        "symbols": all_symbols,
    }


def compact_outline(index: dict[str, Any]) -> list[dict[str, Any]]:
    outline: list[dict[str, Any]] = []
    for item in index["files"]:
        outline.append(
            {
                "file": item["path"],
                "symbols": [
                    {
                        "kind": symbol["kind"],
                        "qualname": symbol["qualname"],
                        "start": symbol["start_line"],
                        "end": symbol["end_line"],
                        "uri": symbol["uri"],
                    }
                    for symbol in item["symbols"]
                ],
            }
        )
    return outline


def symbol_map(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {symbol["uri"]: symbol for symbol in index["symbols"]}


def symbols_by_file(index: dict[str, Any], rel_path: str) -> list[dict[str, Any]]:
    return [symbol for symbol in index["symbols"] if symbol["path"] == rel_path]


def _parse_module(root: Path, rel_path: str) -> tuple[list[str], ast.Module]:
    path = (root / rel_path).resolve()
    root = root.resolve()
    if root not in [path, *path.parents]:
        raise ValueError(f"path escapes root: {rel_path}")
    source = path.read_text(encoding="utf-8")
    return source.splitlines(), ast.parse(source, filename=rel_path)


def _symbol_nodes(tree: ast.Module) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}

    def visit_body(body: list[ast.stmt], stack: list[str]) -> None:
        for child in body:
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = ".".join([*stack, child.name])
                nodes[qualname] = child
                visit_body(child.body, [*stack, child.name])

    visit_body(tree.body, [])
    return nodes


def _target_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            names.update(_target_names(item))
    return names


def _module_assignments(tree: ast.Module) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for node in tree.body:
        names: set[str] = set()
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_target_names(target))
        elif isinstance(node, ast.AnnAssign):
            names.update(_target_names(node.target))
        if names:
            start_line = int(getattr(node, "lineno", 1))
            end_line = int(getattr(node, "end_lineno", start_line))
            assignments.append({"names": names, "start_line": start_line, "end_line": end_line})
    return assignments


class _ReferenceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.calls: set[str] = set()

    def visit_Name(self, node: ast.Name) -> Any:
        if isinstance(node.ctx, ast.Load):
            self.names.add(node.id)

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Name):
            self.calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.add(node.func.attr)
        self.generic_visit(node)


def _numbered_lines(lines: list[str], start_line: int, end_line: int, numbered: bool) -> str:
    selected = lines[start_line - 1 : end_line]
    if not numbered:
        return "\n".join(selected)
    return "\n".join(f"{line_no:04d}: {line}" for line_no, line in enumerate(selected, start_line))


def _question_mentions_symbol(question: str, symbol: dict[str, Any]) -> bool:
    folded = question.casefold()
    names = {
        symbol["name"],
        symbol["qualname"],
        symbol["qualname"].replace(".", " "),
    }
    return any(name.casefold() in folded for name in names)


def expand_symbol_context(
    root: Path,
    index: dict[str, Any],
    uri: str,
    question: str = "",
    numbered: bool = True,
    dependency_depth: int = 1,
    max_symbols: int = 8,
) -> dict[str, Any]:
    symbols = symbol_map(index)
    if uri not in symbols:
        raise KeyError(f"symbol URI not found in index: {uri}")

    primary = symbols[uri]
    rel_path = primary["path"]
    lines, tree = _parse_module(root, rel_path)
    nodes = _symbol_nodes(tree)
    assignments = _module_assignments(tree)
    file_symbols = symbols_by_file(index, rel_path)
    by_name: dict[str, list[dict[str, Any]]] = {}
    for symbol in file_symbols:
        by_name.setdefault(symbol["name"], []).append(symbol)

    included: dict[str, str] = {uri: "primary symbol"}
    included_assignments: dict[tuple[int, int], dict[str, Any]] = {}

    def add_symbol(symbol: dict[str, Any], reason: str) -> bool:
        if symbol["uri"] in included or len(included) >= max_symbols:
            return False
        included[symbol["uri"]] = reason
        return True

    for symbol in file_symbols:
        if symbol["uri"] != uri and _question_mentions_symbol(question, symbol):
            add_symbol(symbol, "symbol mentioned in question")

    frontier = [uri]
    for _ in range(dependency_depth + 1):
        next_frontier: list[str] = []
        for current_uri in frontier:
            current = symbols[current_uri]
            node = nodes.get(current["qualname"])
            if node is None:
                continue
            visitor = _ReferenceVisitor()
            visitor.visit(node)
            referenced = visitor.names | visitor.calls

            for assignment in assignments:
                matched_names = assignment["names"] & referenced
                if matched_names:
                    key = (assignment["start_line"], assignment["end_line"])
                    included_assignments.setdefault(
                        key,
                        {
                            "path": rel_path,
                            "names": sorted(matched_names),
                            "start_line": assignment["start_line"],
                            "end_line": assignment["end_line"],
                            "reason": "module-level name referenced by selected symbol",
                        },
                    )

            for name in sorted(referenced):
                for candidate in by_name.get(name, []):
                    if add_symbol(candidate, "same-file callee/reference"):
                        next_frontier.append(candidate["uri"])
        if not next_frontier:
            break
        frontier = next_frontier

    fragments: list[dict[str, Any]] = []
    for item in included_assignments.values():
        fragments.append(
            {
                "path": item["path"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
                "header": (
                    f"### {item['reason']}: {item['path']}#"
                    f"L{item['start_line']}-L{item['end_line']} ({', '.join(item['names'])})"
                ),
                "source": _numbered_lines(lines, item["start_line"], item["end_line"], numbered),
            }
        )
    for included_uri, reason in included.items():
        symbol = symbols[included_uri]
        fragments.append(
            {
                "path": symbol["path"],
                "start_line": symbol["start_line"],
                "end_line": symbol["end_line"],
                "uri": included_uri,
                "header": f"### {reason}: {included_uri}",
                "source": read_span(root, symbol["path"], symbol["start_line"], symbol["end_line"], numbered=numbered),
            }
        )

    fragments.sort(key=lambda item: (item["path"], item["start_line"], item["end_line"], item["header"]))
    context = "\n\n".join(f"{fragment['header']}\n```python\n{fragment['source']}\n```" for fragment in fragments)
    return {
        "context": context,
        "primary_uri": uri,
        "bundle_uris": list(included),
        "bundle_assignments": [
            {
                "path": item["path"],
                "names": item["names"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
            }
            for item in included_assignments.values()
        ],
        "bundle_fragment_count": len(fragments),
    }


def resolve_symbol(root: Path, index: dict[str, Any], uri: str, numbered: bool = True) -> str:
    match = SYMBOL_URI_RE.match(uri)
    if not match:
        raise ValueError(f"invalid symbol URI: {uri}")
    symbols = symbol_map(index)
    if uri not in symbols:
        raise KeyError(f"symbol URI not found in index: {uri}")
    symbol = symbols[uri]
    return read_span(root, symbol["path"], symbol["start_line"], symbol["end_line"], numbered=numbered)


def read_span(root: Path, rel_path: str, start_line: int, end_line: int, numbered: bool = True) -> str:
    path = (root / rel_path).resolve()
    root = root.resolve()
    if root not in [path, *path.parents]:
        raise ValueError(f"path escapes root: {rel_path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    selected = lines[start_line - 1 : end_line]
    if not numbered:
        return "\n".join(selected)
    return "\n".join(f"{line_no:04d}: {line}" for line_no, line in enumerate(selected, start_line))


def write_index(root: Path, output: Path) -> dict[str, Any]:
    index = build_index(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or query a Python symbol index.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("root", type=Path)
    build.add_argument("--out", type=Path, default=Path("symbol_index.json"))

    outline = subparsers.add_parser("outline")
    outline.add_argument("index", type=Path)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("root", type=Path)
    resolve.add_argument("index", type=Path)
    resolve.add_argument("uri")
    resolve.add_argument("--plain", action="store_true")

    args = parser.parse_args()
    if args.command == "build":
        index = write_index(args.root, args.out)
        print(f"indexed {len(index['files'])} files / {len(index['symbols'])} symbols -> {args.out}")
    elif args.command == "outline":
        index = json.loads(args.index.read_text(encoding="utf-8"))
        print(json.dumps(compact_outline(index), indent=2, ensure_ascii=False))
    elif args.command == "resolve":
        index = json.loads(args.index.read_text(encoding="utf-8"))
        print(resolve_symbol(args.root, index, args.uri, numbered=not args.plain))


if __name__ == "__main__":
    main()
