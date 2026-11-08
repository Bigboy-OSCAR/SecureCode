"""Python 최상위 선언, 로컬 import와 정적 참조 추출."""

import ast
import builtins
import codecs
import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from .model import Declaration, Reference
from .python_layout import PythonLayout


def _assigned_names(target: ast.expr) -> Iterator[str]:
    """
    함수 이름: _assigned_names()
    기능: 단순·구조 분해 대입이 새로 묶는 이름을 추출한다.
    인자: target -> 대입 대상
    반환값: 선언 이름 반복자
    작성 날짜: 2026/11/05
    """
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for item in target.elts:
            yield from _assigned_names(item)
    elif isinstance(target, ast.Starred):
        yield from _assigned_names(target.value)


def _declarations(tree: ast.Module) -> Iterator[tuple[str, str, ast.stmt]]:
    """
    함수 이름: _declarations()
    기능: 최상위 함수·클래스·대입에서 R0에 넣을 선언을 선택한다.
    인자: tree -> 파일 AST
    반환값: 이름, 종류, 선언 노드 반복자
    작성 날짜: 2026/11/05
    """
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef):
            yield statement.name, "function", statement
        elif isinstance(statement, ast.AsyncFunctionDef):
            yield statement.name, "async_function", statement
        elif isinstance(statement, ast.ClassDef):
            yield statement.name, "class", statement
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for name in _assigned_names(target):
                    yield name, "constant", statement


def _bindings(
    imports: list[ast.Import | ast.ImportFrom], package: list[str]
) -> dict[str, set[str]]:
    """
    함수 이름: _bindings()
    기능: 별칭과 상대 단계를 적용해 import가 가리키는 전체 모듈·이름을 기록한다.
    인자: imports -> 모듈 수준 import 목록, package -> 현재 패키지 경로
    반환값: 로컬 이름별 대상 이름 집합
    작성 날짜: 2026/11/05
    """
    bindings: dict[str, set[str]] = {}
    for statement in imports:
        for alias in statement.names:
            if isinstance(statement, ast.Import):
                local = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else local
            else:
                if statement.level > len(package):
                    continue
                prefix = package[: len(package) - statement.level + 1] if statement.level else []
                local = alias.asname or alias.name
                target = ".".join(filter(None, [*prefix, statement.module, alias.name]))
            bindings.setdefault(local, set()).add(target)
    return bindings


def _references(
    node: ast.stmt,
    module: str,
    bindings: dict[str, set[str]],
    file_names: set[str],
    key_prefix: str,
) -> tuple[Reference, ...]:
    """
    함수 이름: _references()
    기능: 이름 및 정적 속성 경로를 수집하고 매개변수나 로컬 변수와 겹치는 연결을 제외한다.
    인자: node -> 선언, module -> 모듈명, bindings -> import 대상, file_names -> 파일 내 선언명,
        key_prefix -> 프로젝트 이름 공간
    반환값: 정적 대상 후보 또는 미해결 참조
    작성 날짜: 2026/11/05
    """
    nodes = list(ast.walk(node))
    member_bases = {n.value for n in nodes if isinstance(n, ast.Attribute)}
    local = {n.arg for n in nodes if isinstance(n, ast.arg)}
    for item in nodes:
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
            local.add(item.id)
        if isinstance(item, ast.alias):
            local.add(item.asname or item.name.split(".")[0])
        if item is not node and isinstance(
            item, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ):
            local.add(item.name)
    references: dict[str, Reference] = {}
    for item in nodes:
        if isinstance(item, ast.Call):
            callee = item.func
            if isinstance(callee, ast.Name) and (
                callee.id in local or callee.id in {"getattr", "__import__", "eval", "exec"}
            ):
                label = f"{callee.id}()"
                references[label] = Reference(label, ())
            elif not isinstance(callee, ast.Name | ast.Attribute):
                references["<dynamic call>"] = Reference("<dynamic call>", ())
        if not isinstance(item, ast.Name | ast.Attribute) or not isinstance(item.ctx, ast.Load):
            continue
        parts: list[str] = []
        base: ast.expr = item
        while isinstance(base, ast.Attribute):
            parts.insert(0, base.attr)
            base = base.value
        if not isinstance(base, ast.Name):
            continue
        name = ".".join([base.id, *parts])
        if base.id in local:
            if parts:
                references[name] = Reference(name, ())
            continue
        if item in member_bases and base.id in bindings:
            continue
        keys = [
            key_prefix + ".".join([prefix, *parts[:size]])
            for prefix in bindings.get(base.id, ())
            for size in range(len(parts) + 1)
        ]
        if base.id in file_names and not parts:
            keys.append(f"{key_prefix}{module}.{base.id}")
        if keys or parts or not hasattr(builtins, base.id):
            references[name] = Reference(name, tuple(sorted(set(keys))))
    return tuple(references[name] for name in sorted(references))


def parse_python(path: str, source: bytes, layout: PythonLayout) -> list[Declaration]:
    """
    함수 이름: parse_python()
    기능: 데코레이터와 한글의 바이트 위치를 보존하며 선언을 추출한다.
    인자: path -> 상대 경로, source -> UTF-8 파일 바이트, layout -> 프로젝트 및 src 경계
    반환값: 추출한 선언 목록
    작성 날짜: 2026/11/05
    """
    text = source.decode("utf-8-sig")
    tree = ast.parse(text, filename=path)
    offsets = [len(codecs.BOM_UTF8) if source.startswith(codecs.BOM_UTF8) else 0]
    # AST 열은 UTF-8 바이트 단위다. LF/CRLF/CR만 물리적 줄바꿈으로 처리한다.
    offsets.extend(match.end() for match in re.finditer(rb"\r\n|\r|\n", source))
    location = PurePosixPath(path).relative_to(layout.project)
    in_src = layout.has_src and location.parts[:1] == ("src",)
    if in_src:
        location = location.relative_to("src")
    location = location.with_suffix("")
    key_prefix = f"py:{layout.project.as_posix()}/"
    package = list(location.parent.parts)
    module = ".".join(package if location.name == "__init__" else location.parts)
    # src.pkg is also importable from a checkout root. Match both spellings only in this project.
    module_keys = [key_prefix + module]
    if in_src:
        module_keys.append(key_prefix + "src." + module)
    declarations = list(_declarations(tree))
    names = {name for name, _, _ in declarations}
    imports = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    bindings = _bindings(imports, package)
    import_spans = []
    for statement in imports:
        assert statement.end_lineno is not None and statement.end_col_offset is not None
        begin = offsets[statement.lineno - 1] + statement.col_offset
        end = offsets[statement.end_lineno - 1] + statement.end_col_offset
        import_spans.append(source[begin:end].decode("utf-8"))
    import_text = "\n".join(import_spans)
    refs: dict[ast.stmt, tuple[Reference, ...]] = {}
    result = []
    for name, kind, node in declarations:
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno, *(expr.lineno for expr in decorators)])
        # 괄호로 감싼 데코레이터 식은 @ 다음 줄에서 시작할 수 있다.
        if decorators:
            previous = offsets[start - 1]
            while start > 1 and not source[previous:].lstrip(b" \t").startswith(b"@"):
                start -= 1
                previous = offsets[start - 1]
        assert node.end_lineno is not None and node.end_col_offset is not None
        start_byte = offsets[start - 1] + node.col_offset
        end_byte = offsets[node.end_lineno - 1] + node.end_col_offset
        if node not in refs:
            refs[node] = _references(node, module, bindings, names, key_prefix)
        result.append(
            Declaration(
                name,
                kind,
                start_byte,
                end_byte,
                start,
                node.end_lineno,
                tuple(f"{key}.{name}" for key in module_keys),
                refs[node],
                import_text,
            )
        )
    return result
