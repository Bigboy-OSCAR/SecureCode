"""SymbolService 포트(3.3/3.4 구현). 요청·응답 모양은 contracts/symbols/symbol.schema.json을 따른다."""

from collections.abc import Mapping
from typing import Protocol


class SymbolService(Protocol):
    """
    클래스 이름: SymbolService
    기능: R0 TF-IDF 후보 검색과 예산 안 Symbol Bundle 읽기. LLM 선택·요약·임베딩을 쓰지 않는다.
    작성 날짜: 2026/11/04
    """

    def search(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """
        함수 이름: search()
        기능: SymbolSearchRequest를 받아 SymbolSearchResponse를 돌려준다(무결과는 no_match로 표시).
        인자: request -> 검증된 SymbolSearchRequest
        반환값: SymbolSearchResponse
        작성 날짜: 2026/11/04
        """
        ...

    def read_bundle(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """
        함수 이름: read_bundle()
        기능: SymbolBundleRequest의 후보를 예산 안 원문 fragment로 돌려준다.
        인자: request -> 검증된 SymbolBundleRequest
        반환값: SymbolBundle
        작성 날짜: 2026/11/04
        """
        ...
