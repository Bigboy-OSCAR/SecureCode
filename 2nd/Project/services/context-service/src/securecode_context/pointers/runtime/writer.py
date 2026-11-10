"""Runtime 스트리밍 저장 포트(4.4 hook용). open → write* → commit(descriptor) 또는 abort(취소·실패 정리).

commit 전에는 목록·조회에 보이지 않는다. 세션 용량 검사와 ready 전환은 DB 쓰기 잠금 안에서 한 번에 한다.
"""

import codecs
from collections.abc import Callable
from types import TracebackType
from typing import Self

from securecode_context.pointers.models.runtime import NotStorable, RuntimeDescriptor
from securecode_context.pointers.runtime.blob import BlobWriter


class RuntimeWriter:
    """
    클래스 이름: RuntimeWriter
    기능: 도구 출력 하나를 청크로 저장한다. 예외로 with 블록을 나가면 자동 abort한다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        pointer_id: str,
        blob: BlobWriter,
        finish: Callable[[RuntimeWriter], RuntimeDescriptor],
        discard: Callable[[RuntimeWriter], None],
    ) -> None:
        """
        함수 이름: __init__()
        기능: 예약된 포인터 ID, 임시 blob, 저장소의 완료·폐기 동작을 보관한다.
        인자: pointer_id -> 예약 ID, blob -> 임시 blob, finish/discard -> 저장소 콜백
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.pointer_id = pointer_id
        self.blob = blob
        self._finish = finish
        self._discard = discard
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._done = False

    def write(self, data: bytes) -> None:
        """
        함수 이름: write()
        기능: UTF-8 텍스트인지 확인하며 다음 청크를 쓴다. 상한 초과·디스크 오류면 정리 후 예외다.
        인자: data -> 다음 바이트
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        try:
            self._decoder.decode(data, final=False)
            self.blob.write(data)
        except UnicodeDecodeError as error:
            self.abort()
            raise NotStorable("UTF-8 텍스트만 저장합니다", "invalid_utf8") from error
        except Exception:
            self.abort()
            raise

    def commit(self) -> RuntimeDescriptor:
        """
        함수 이름: commit()
        기능: 마지막 문자를 확인하고 blob을 확정한 뒤 세션 용량 안이면 ready로 바꾼다.
        인자: 없음
        반환값: RuntimeDescriptor
        작성 날짜: 2026/11/10
        """
        try:
            self._decoder.decode(b"", final=True)
        except UnicodeDecodeError as error:
            self.abort()
            raise NotStorable("UTF-8 텍스트만 저장합니다", "invalid_utf8") from error
        self._done = True
        return self._finish(self)

    def abort(self) -> None:
        """
        함수 이름: abort()
        기능: 임시 파일과 예약 행을 지운다. 여러 번 불러도 된다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if not self._done:
            self._done = True
            self.blob.abort()
            self._discard(self)

    def __enter__(self) -> Self:
        """
        함수 이름: __enter__()
        기능: with 문에서 쓴다.
        인자: 없음
        반환값: 자기 자신
        작성 날짜: 2026/11/10
        """
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """
        함수 이름: __exit__()
        기능: commit하지 않고 나가면(예외·취소 포함) abort한다.
        인자: kind/error/trace -> 예외 정보
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.abort()
