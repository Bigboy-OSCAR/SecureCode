"""JavaScript 파일 안의 바인딩 이름과 정적으로 명시한 모듈 입출력을 구분한다."""

import posixpath
from collections import defaultdict
from dataclasses import dataclass, field

from tree_sitter import Node

from .syntax import node_text

_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")


def export_keys(path: str, module: str, name: str) -> tuple[str, ...]:
    """
    함수 이름: export_keys()
    기능: 상대 모듈 지정자를 작업 루트 기준 export 키 후보로 변환한다.
    인자: path -> 참조 파일, module -> import 경로, name -> 외부에 공개한 이름
    반환값: 대상 경로별 키. 패키지 의존과 루트 외부 경로는 빈 튜플
    작성 날짜: 2026/11/05
    """
    if not module.startswith(("./", "../")):
        return ()
    target = posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
    if target.startswith("../") or target == "..":
        return ()
    paths = [target]
    if not posixpath.splitext(target)[1]:
        paths += [target + suffix for suffix in _JS_SUFFIXES]
        paths += [posixpath.join(target, "index" + suffix) for suffix in _JS_SUFFIXES]
    return tuple(f"js:export:{file}:{name}" for file in paths)


@dataclass
class ModuleBindings:
    """
    클래스 이름: ModuleBindings
    기능: 파일 안의 이름과 명시적으로 가져오거나 내보낸 이름의 관계를 보관한다.
    작성 날짜: 2026/11/05
    """

    imported: dict[str, tuple[str, str]] = field(default_factory=dict)
    exported: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    statements: list[str] = field(default_factory=list)


def _module_name(string: Node | None) -> str:
    """
    함수 이름: _module_name()
    기능: 보간이나 이스케이프가 없는 모듈 경로 리터럴을 읽는다.
    인자: string -> 모듈 이름의 구문 노드
    반환값: 모듈 경로 또는 빈 문자열
    작성 날짜: 2026/11/05
    """
    if string and string.type == "string" and len(string.named_children) == 1:
        fragment = string.named_children[0]
        if fragment.type == "string_fragment":
            return node_text(fragment)
    return ""


def _esm_import(statement: Node, bindings: ModuleBindings) -> None:
    """
    함수 이름: _esm_import()
    기능: 명시적 ESM default/named/namespace import의 로컬 바인딩을 기록한다.
    인자: statement -> import 선언, bindings -> 현재 파일의 바인딩
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    module = _module_name(statement.child_by_field_name("source"))
    for clause in statement.named_children:
        if clause.type != "import_clause":
            continue
        for part in clause.named_children:
            if part.type == "identifier":
                bindings.imported[node_text(part)] = (module, "default")
            elif part.type == "namespace_import":
                bindings.imported[node_text(part.named_children[-1])] = (module, "*")
            elif part.type == "named_imports":
                for spec in part.named_children:
                    name = spec.child_by_field_name("name")
                    if name:
                        alias = spec.child_by_field_name("alias") or name
                        bindings.imported[node_text(alias)] = (module, node_text(name))


def required_module(call: Node) -> str | None:
    """
    함수 이름: required_module()
    기능: require 호출을 식별하고 유일한 리터럴 인자에서 모듈 경로를 얻는다.
    인자: call -> 호출 구문 노드
    반환값: 모듈 경로, 동적 인자이면 빈 문자열, require 호출이 아니면 None
    작성 날짜: 2026/11/05
    """
    callee = call.child_by_field_name("function")
    args = call.child_by_field_name("arguments")
    if not callee or callee.type != "identifier" or node_text(callee) != "require" or not args:
        return None
    arguments = [part for part in args.named_children if part.type != "comment"]
    return _module_name(arguments[0]) if len(arguments) == 1 else ""


def _cjs_import(node: Node, bindings: ModuleBindings) -> bool:
    """
    함수 이름: _cjs_import()
    기능: 단순 변수나 구조 분해 변수에 할당된 리터럴 require를 수집한다.
    인자: node -> 변수 선언자, bindings -> 현재 파일의 바인딩
    반환값: require 선언이면 True
    작성 날짜: 2026/11/05
    """
    binding = node.child_by_field_name("name")
    call = node.child_by_field_name("value")
    if binding is None or call is None or call.type != "call_expression":
        return False
    module = required_module(call)
    if module is None:
        return False
    if binding.type == "identifier":
        bindings.imported[node_text(binding)] = (module, "require:*")
    elif binding.type == "object_pattern":
        for prop in binding.named_children:
            if prop.type == "shorthand_property_identifier_pattern":
                bindings.imported[node_text(prop)] = (module, node_text(prop))
            elif prop.type == "pair_pattern":
                key = prop.child_by_field_name("key")
                value = prop.child_by_field_name("value")
                if (
                    key
                    and value
                    and value.type == "identifier"
                    and key.type == "property_identifier"
                ):
                    bindings.imported[node_text(value)] = (module, node_text(key))
    return True


def assigned_export(statement: Node) -> tuple[str, Node] | None:
    """
    함수 이름: assigned_export()
    기능: CommonJS의 module.exports와 exports.name 단순 대입을 구별한다.
    인자: statement -> 최상위 문장
    반환값: 공개 이름과 우변 또는 해당하지 않으면 None
    작성 날짜: 2026/11/05
    """
    if statement.type != "expression_statement" or not statement.named_children:
        return None
    assignment = statement.named_children[0]
    left = assignment.child_by_field_name("left")
    right = assignment.child_by_field_name("right")
    if assignment.type != "assignment_expression" or left is None or right is None:
        return None
    owner = left.child_by_field_name("object")
    prop = left.child_by_field_name("property")
    if owner is None or prop is None or prop.type != "property_identifier":
        return None
    name = node_text(prop)
    if node_text(owner) == "module" and name == "exports":
        return "default", right
    if node_text(owner) in {"module.exports", "exports"}:
        return name, right
    return None


def collect_bindings(root: Node, loader_available: bool) -> ModuleBindings:
    """
    함수 이름: collect_bindings()
    기능: import와 별도 export 문을 먼저 읽어 선언 순서에 독립적으로 바인딩한다.
    인자: root -> JavaScript 구문 트리, loader_available -> 전역 require 사용 가능 여부
    반환값: 파일의 바인딩 정보
    작성 날짜: 2026/11/05
    """
    bindings = ModuleBindings()
    statements = root.named_children
    for statement in statements:
        if statement.type == "import_statement":
            _esm_import(statement, bindings)
    loader_available = loader_available and "require" not in bindings.imported
    for statement in statements:
        if statement.type == "import_statement":
            bindings.statements.append(node_text(statement))
        elif loader_available and statement.type in {"lexical_declaration", "variable_declaration"}:
            for decl in statement.named_children:
                if _cjs_import(decl, bindings):
                    bindings.statements.append(node_text(decl))
        elif statement.type == "export_statement" and not statement.child_by_field_name("source"):
            for clause in statement.named_children:
                if clause.type != "export_clause":
                    continue
                for spec in clause.named_children:
                    name = spec.child_by_field_name("name")
                    if name:
                        alias = spec.child_by_field_name("alias") or name
                        bindings.exported[node_text(name)].add(node_text(alias))
            value = statement.child_by_field_name("value")
            if value and value.type == "identifier":
                bindings.exported[node_text(value)].add("default")
        elif assigned := assigned_export(statement):
            public, value = assigned
            if value.type == "identifier":
                bindings.exported[node_text(value)].add(public)
            elif value.type == "object" and public == "default":
                for prop in value.named_children:
                    if prop.type == "shorthand_property_identifier":
                        bindings.exported[node_text(prop)].add(node_text(prop))
                    elif prop.type == "pair":
                        key = prop.child_by_field_name("key")
                        item = prop.child_by_field_name("value")
                        if key and item and item.type == "identifier":
                            bindings.exported[node_text(item)].add(node_text(key))
    return bindings
