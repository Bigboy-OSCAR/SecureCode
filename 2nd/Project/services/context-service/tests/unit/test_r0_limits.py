"""R0 생성 시 원문 헤더·반복 범위·묶음 확장에 실제 UTF-8 크기 제한이 적용되는지 확인한다."""

from pathlib import Path

import pytest

from securecode_context.symbols import graph
from securecode_context.symbols.index import build_index


def test_oversized_primary_skips_whole_file(tmp_path: Path) -> None:
    """
    함수 이름: test_oversized_primary_skips_whole_file()
    기능: 입력 상한에 맞는 파일도 위치 헤더를 붙인 후보가 넘치면 파일 단위로 제외한다.
    인자: tmp_path -> 임시 워크스페이스
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    prefix = b'FIRST = 1\nLARGE = "'
    payload = b"x" * (graph.MAX_CANDIDATE_BYTES - len(prefix) - 1)
    (tmp_path / "large.py").write_bytes(prefix + payload + b'"')
    (tmp_path / "ok.js").write_text("const okay = 1;", encoding="utf-8")
    result = build_index(tmp_path)
    assert result["diagnostics"] == [{"relative_path": "large.py", "reason_code": "too_large"}]
    assert [node["name"] for node in result["nodes"].values()] == ["okay"]
    assert len(result["raw"]) == 1


def test_repeated_span_exceeds_file_expansion_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_repeated_span_exceeds_file_expansion_budget()
    기능: 다중 대입에 의해 같은 원문이 반복되는 비용을 원문 복사 전에 제한한다.
    인자: tmp_path -> 임시 워크스페이스, monkeypatch -> 테스트용 상한
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    (tmp_path / "many.py").write_text("a,b,c,d,e,f = '한글',1,2,3,4,5", encoding="utf-8")
    monkeypatch.setattr(graph, "MAX_FILE_FRAGMENT_BYTES", 210)
    result = build_index(tmp_path)
    assert result["diagnostics"] == [{"relative_path": "many.py", "reason_code": "too_large"}]
    assert result["nodes"] == {}
    assert result["raw"] == []


def test_separate_workspace_limits_before_bundle_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_separate_workspace_limits_before_bundle_materialization()
    기능: 전체 원문 합과 중복된 묶음·단일 후보 텍스트 합을 각각 실제 바이트로 제한한다.
    인자: tmp_path -> 임시 워크스페이스, monkeypatch -> 테스트용 상한
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    (tmp_path / "library.py").write_text('LIMIT = "한글"', encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "from library import LIMIT\ndef run(): return LIMIT", encoding="utf-8"
    )
    baseline = build_index(tmp_path)
    single_bytes = sum(
        len(candidate["text"].encode())
        for candidate in baseline["raw"]
        if len(candidate["source_uris"]) == 1
    )
    monkeypatch.setattr(graph, "MAX_WORKSPACE_TEXT_BYTES", single_bytes - 1)
    with pytest.raises(graph.IndexCapacityError, match="source fragment"):
        build_index(tmp_path)
    monkeypatch.setattr(graph, "MAX_WORKSPACE_TEXT_BYTES", single_bytes)
    with pytest.raises(graph.IndexCapacityError, match="candidate text"):
        build_index(tmp_path)
    monkeypatch.setattr(
        graph, "MAX_WORKSPACE_TEXT_BYTES", sum(len(c["text"].encode()) for c in baseline["raw"])
    )
    assert build_index(tmp_path) == baseline
