"""언어 파서의 선언과 참조를 공통 색인 입력으로 표현한다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    """
    클래스 이름: Reference
    기능: 참조 표기와 파서가 허용한 정적 대상 키를 보관한다. 빈 키는 동적 참조를 뜻한다.
    작성 날짜: 2026/11/05
    """

    name: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class Declaration:
    """
    클래스 이름: Declaration
    기능: 원본 UTF-8 바이트 범위와 1부터 시작하는 줄 범위, 선언 키와 참조를 보관한다.
    작성 날짜: 2026/11/05
    """

    name: str
    kind: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    keys: tuple[str, ...]
    references: tuple[Reference, ...]
    imports: str = ""
