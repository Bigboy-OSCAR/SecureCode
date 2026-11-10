"""원본 revision·내용에 묶인 파생 색인(줄 오프셋, Markdown 제목)의 프로세스 내 LRU 보관."""

from collections import OrderedDict
from collections.abc import Callable
from threading import Lock

# Callers build keys from (index kind, object id, revision, content hash, file identity),
# so a changed object never reuses a stale index.
type MemoKey = tuple[object, ...]


class BoundedMemo[T]:
    """
    클래스 이름: BoundedMemo
    기능: 최근 사용 순으로 최대 capacity개의 파생 색인을 보관한다. 재시작하면 다시 만든다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, capacity: int = 32) -> None:
        """
        함수 이름: __init__()
        기능: 최대 보관 개수를 정한다.
        인자: capacity -> 최대 항목 수
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._capacity = capacity
        self._items: OrderedDict[MemoKey, T] = OrderedDict()
        self._lock = Lock()

    def get_or_build(self, key: MemoKey, build: Callable[[], T]) -> T:
        """
        함수 이름: get_or_build()
        기능: 있으면 돌려주고 없으면 만들어 넣는다.
        인자: key -> 캐시 키, build -> 생성 함수
        반환값: 보관한 값
        작성 날짜: 2026/11/10
        """
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        built = build()
        with self._lock:
            self._items[key] = built
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
        return built
