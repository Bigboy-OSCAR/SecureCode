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

