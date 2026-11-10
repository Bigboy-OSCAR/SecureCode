"""요청 하나의 resolver 묶음과 context block 봉투(4.8, 정책 7절 6항)."""

import hashlib
import json
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.context.models import Candidate, Material, Span, Wire

ENVELOPE = '<securecode-context id="{id}" source="{source}">\n{content}\n</securecode-context>'


def render_envelope(candidate_id: str, source: str, content: str) -> str:
    """
    함수 이름: render_envelope()
    기능: host가 fragment를 넣을 때 쓰는 context block(정책 7절 6항)을 만든다.
    인자: candidate_id -> 후보 ID, source -> 표시 이름, content -> 원문
    반환값: 봉투로 감싼 텍스트
    작성 날짜: 2026/11/10
    """
    safe = source.replace('"', "'").replace("\n", " ")[:256]
    return ENVELOPE.format(id=candidate_id, source=safe, content=content)


class Resolver(Protocol):
    """
    클래스 이름: Resolver
    기능: 종류별 resolver의 공통 모양(해석·읽기).
    작성 날짜: 2026/11/10
    """

    def inspect(self, candidate: Candidate) -> Candidate:
        """
        함수 이름: inspect()
        기능: 후보를 해석한다.
        인자: candidate -> 후보
        반환값: 상태·구간을 채운 후보
        작성 날짜: 2026/11/10
        """
        ...

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 상한 안에서 읽는다.
        인자: candidate -> 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        ...


def pointer_candidate_id(ref: Wire) -> str:
    """
    함수 이름: pointer_candidate_id()
    기능: 같은 포인터 ref에 항상 같은 CandidateId를 준다.
    인자: ref -> PointerContextRef
    반환값: cand_ 접두사 ID
    작성 날짜: 2026/11/10
    """
    canonical = json.dumps(ref, sort_keys=True, separators=(",", ":"))
    return "cand_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


class RequestReader:
    """
    클래스 이름: _Reader
    기능: 요청 하나의 resolver 묶음(MaterialReader). 봉투 비용은 표시 이름까지 넣어 실제로 센다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, resolvers: dict[str, Resolver], counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: 종류별 resolver와 계수기를 저장한다.
        인자: resolvers -> kind별 resolver, counter -> TokenCounter
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._resolvers = resolvers
        self._counter = counter

    def resolver(self, kind: str) -> Resolver:
        """
        함수 이름: resolver()
        기능: 종류의 resolver를 돌려준다. 없으면(색인 미연결) INDEX_NOT_READY다.
        인자: kind -> symbol/source/runtime
        반환값: resolver
        작성 날짜: 2026/11/10
        """
        found = self._resolvers.get(kind)
        if found is None:
            raise ServiceError(ErrorCode.INDEX_NOT_READY, "심볼 색인이 연결되지 않았습니다.")
        return found

    def envelope_tokens(self, candidate: Candidate) -> int:
        """
        함수 이름: envelope_tokens()
        기능: 빈 본문 봉투를 센다.
        인자: candidate -> 후보
        반환값: 토큰 수
        작성 날짜: 2026/11/10
        """
        handle = candidate.handle
        source = handle["relative_path"] if candidate.kind == "symbol" else handle.display
        text = render_envelope(candidate.candidate_id, source, "")
        return self._counter.count(text).token_count

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 종류별 resolver로 읽는다.
        인자: candidate -> 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        return self.resolver(candidate.kind).read(candidate, span, max_tokens)
