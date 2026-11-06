"""공통 정적 참조 그래프와 R0 원문 후보를 구성한다."""

from collections import Counter, defaultdict, deque
from typing import NotRequired, TypedDict
from urllib.parse import quote

from ..parser.model import Declaration, Reference

MAX_CANDIDATE_BYTES = 1024 * 1024
MAX_FILE_FRAGMENT_BYTES = 16 * 1024 * 1024
MAX_WORKSPACE_TEXT_BYTES = 128 * 1024 * 1024


class IndexCapacityError(ValueError):
    """
    클래스 이름: IndexCapacityError
    기능: 전체 작업 공간의 원문·후보 텍스트가 빌드 상한을 초과했음을 표시한다.
    작성 날짜: 2026/11/05
    """


def _fragment_header(uri: str, start: int, end: int) -> str:
    """
    함수 이름: _fragment_header()
    기능: 원문 생성과 크기 계산에 같은 위치 헤더를 사용한다.
    인자: uri -> 심볼 주소, start/end -> 1부터 시작하는 줄 범위
    반환값: 줄바꿈으로 끝나는 원문 위치 헤더
    작성 날짜: 2026/11/05
    """
    return f"### {uri} lines {start}-{end}\n"


class SourceNode(TypedDict):
    """
    클래스 이름: SourceNode
    기능: 언어에 관계없이 원문과 정확한 위치·해시·정적 참조를 한 형식으로 저장한다.
    작성 날짜: 2026/11/05
    """

    id: str
    path: str
    name: str
    language: str
    kind: str
    start: int
    end: int
    start_byte: int
    end_byte: int
    content_sha256: str
    source: str
    imports: str
    refs: list[str]
    deps: list[str]
    unresolved_reference: list[str]


class RawCandidate(TypedDict):
    """
    클래스 이름: RawCandidate
    기능: R0의 TF-IDF 검색기가 읽는 원문 후보와 포함된 심볼을 보관한다.
    작성 날짜: 2026/11/05
    """

    id: str
    level: int
    text: str
    source_uris: list[str]
    path: str
    kind: str
    truncated: NotRequired[bool]


class SourceGraph:
    """
    클래스 이름: SourceGraph
    기능: 파일별 선언을 모으고 모든 파일을 읽은 뒤 유일한 참조 대상만 연결한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self) -> None:
        """
        함수 이름: __init__()
        기능: 빌드마다 새 그래프를 만든다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.nodes: dict[str, SourceNode] = {}
        self.keys: defaultdict[str, set[str]] = defaultdict(set)
        self.references: dict[str, tuple[Reference, ...]] = {}
        self._fragment_bytes = 0

    def add_file(
        self,
        path: str,
        language: str,
        source: bytes,
        file_hash: str,
        declarations: list[Declaration],
    ) -> bool:
        """
        함수 이름: add_file()
        기능: 선언 바이트 범위를 잘라 원문을 보존하고 오버로드·동명 선언을 서로 구별한다.
        인자: path -> 상대 경로, language -> 언어, source -> 바이트, file_hash -> 해시, declarations -> 선언
        반환값: 등록 성공 여부. 파일 단위 상한 초과 시 선언 전체를 제외한다.
        작성 날짜: 2026/11/05
        """
        counts = Counter(decl.name for decl in declarations)
        occurrences: Counter[str] = Counter()
        identifiers: list[str] = []
        file_bytes = 0
        prefix = f"memory://symbol/{quote(path)}::"
        for decl in declarations:
            uri = prefix + quote(decl.name, safe=".:")
            if counts[decl.name] > 1:
                uri += f"@{decl.start_byte}"
                occurrences[uri] += 1
                if occurrences[uri] > 1:
                    uri += f"-{occurrences[uri]}"
            header = _fragment_header(uri, decl.start_line, decl.end_line)
            size = (
                len(header.encode())
                + len(decl.imports.encode())
                + 1
                + decl.end_byte
                - decl.start_byte
            )
            file_bytes += size
            if size > MAX_CANDIDATE_BYTES or file_bytes > MAX_FILE_FRAGMENT_BYTES:
                return False
            identifiers.append(uri)

        if self._fragment_bytes + file_bytes > MAX_WORKSPACE_TEXT_BYTES:
            raise IndexCapacityError("workspace source fragment limit exceeded")
        self._fragment_bytes += file_bytes
        for uri, decl in zip(identifiers, declarations, strict=True):
            self.nodes[uri] = SourceNode(
                id=uri,
                path=path,
                name=decl.name,
                language=language,
                kind=decl.kind,
                start=decl.start_line,
                end=decl.end_line,
                start_byte=decl.start_byte,
                end_byte=decl.end_byte,
                content_sha256=file_hash,
                imports=decl.imports,
                source=source[decl.start_byte : decl.end_byte].decode("utf-8"),
                refs=sorted({r.name for r in decl.references}),
                deps=[],
                unresolved_reference=[],
            )
            self.references[uri] = decl.references
            for key in decl.keys:
                self.keys[key].add(uri)
        return True

    def link(self) -> None:
        """
        함수 이름: link()
        기능: 파일 전체의 이름이 정해진 뒤 후보 하나로 확인되는 참조만 연결한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        resolved: dict[str, set[str]] = {}
        ambiguous: dict[str, list[tuple[str, set[str]]]] = {}
        for uri, references in self.references.items():
            resolved[uri] = set()
            ambiguous[uri] = []
            for ref in references:
                matches = {target for key in ref.keys for target in self.keys.get(key, ())}
                if len(matches) == 1:
                    resolved[uri].update(matches)
                else:
                    ambiguous[uri].append((ref.name, matches))
        for uri, pending in ambiguous.items():
            unresolved: set[str] = set()
            for name, matches in pending:
                target = self._same_function(matches, resolved)
                if target is None:
                    unresolved.add(name)
                else:
                    resolved[uri].add(target)
            self.nodes[uri]["deps"] = sorted(resolved[uri] - {uri})
            self.nodes[uri]["unresolved_reference"] = sorted(unresolved)

    def _same_function(self, matches: set[str], resolved: dict[str, set[str]]) -> str | None:
        """
        함수 이름: _same_function()
        기능: C/C++ 후보가 헤더 원형과 그 원형이 유일하게 가리키는 구현뿐이면 구현 하나로 확정한다.
            구현 파일이 자기 헤더를 포함하고 같은 함수를 부를 때만 해당하며 그 외 모호성은 유지한다.
        인자: matches -> 같은 참조의 후보 집합, resolved -> 1차로 확정된 참조
        반환값: 확정된 구현 심볼 ID, 아니면 None
        작성 날짜: 2026/11/05
        """
        if len(matches) != 2:
            return None
        nodes = [self.nodes[target] for target in sorted(matches)]
        if any(
            node["language"] not in {"c", "cpp"} or node["kind"] != "function" for node in nodes
        ):
            return None
        for prototype, implementation in ((nodes[0], nodes[1]), (nodes[1], nodes[0])):
            if resolved.get(prototype["id"]) == {implementation["id"]}:
                return implementation["id"]
        return None


def raw_candidates(nodes: dict[str, SourceNode]) -> list[RawCandidate]:
    """
    함수 이름: raw_candidates()
    기능: 최대 세 번 참조를 따라 모은 원문과 단일 원문을 기존 R0 후보 형식으로 구성한다.
    인자: nodes -> 연결된 그래프
    반환값: TF-IDF 입력 목록. 후보당 64심볼 또는 1 MiB 상한에 걸리면 truncated를 표시한다.
    작성 날짜: 2026/11/05
    """
    fragments = {
        uri: _fragment_header(uri, node["start"], node["end"])
        + node["imports"]
        + "\n"
        + node["source"]
        for uri, node in nodes.items()
    }
    sizes = {uri: len(fragment.encode()) for uri, fragment in fragments.items()}
    candidates: list[RawCandidate] = []
    workspace_bytes = 0
    for uri, node in nodes.items():
        members = [uri]
        visited = {uri}
        pending = deque([(uri, 0)])
        total = sizes[uri]
        truncated = False
        while pending:
            member, depth = pending.popleft()
            if depth == 3:
                continue
            for dep in nodes[member]["deps"]:
                if dep in visited:
                    continue
                visited.add(dep)
                if len(members) == 64 or total + 2 + sizes[dep] > MAX_CANDIDATE_BYTES:
                    truncated = True
                    continue
                members.append(dep)
                pending.append((dep, depth + 1))
                total += 2 + sizes[dep]
        workspace_bytes += total
        if len(members) > 1:
            workspace_bytes += sizes[uri]
        if workspace_bytes > MAX_WORKSPACE_TEXT_BYTES:
            raise IndexCapacityError("workspace R0 candidate text limit exceeded")
        bundle = RawCandidate(
            id=uri,
            level=0,
            text="\n\n".join(fragments[member] for member in members),
            source_uris=members,
            path=node["path"],
            kind=node["kind"],
        )
        if truncated:
            bundle["truncated"] = True
        candidates.append(bundle)
        if len(members) > 1:
            candidates.append(
                RawCandidate(
                    id=f"atomic:{uri}",
                    level=0,
                    text=fragments[uri],
                    source_uris=[uri],
                    path=node["path"],
                    kind="raw_atomic",
                )
            )
    return candidates
