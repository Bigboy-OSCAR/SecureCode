"""Source adapter: 등록부(4.5)와 부분 읽기·검색(4.6)을 한 수명으로 묶는다. 3.6/4.8/4.9가 이 객체를 받는다."""

from dataclasses import dataclass, field

from securecode_context.common.tokens.counter import TokenCounter
from securecode_context.pointers.source.readers import SourceReader
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.pointers.source.search import SourceSearcher


@dataclass
class SourceAdapter:
    """
    클래스 이름: SourceAdapter
    기능: 같은 등록부를 공유하는 reader·searcher. 줄/제목 색인 캐시는 reader 안에서 유지된다.
    작성 날짜: 2026/11/10
    """

    registry: SourceRegistry
    counter: TokenCounter
    reader: SourceReader = field(init=False)
    searcher: SourceSearcher = field(init=False)

    def __post_init__(self) -> None:
        """
        함수 이름: __post_init__()
        기능: 등록부와 TokenCounter로 reader·searcher를 만든다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.reader = SourceReader(self.registry, self.counter)
        self.searcher = SourceSearcher(self.registry, self.counter)

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 등록부 DB 연결을 닫는다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.registry.close()
