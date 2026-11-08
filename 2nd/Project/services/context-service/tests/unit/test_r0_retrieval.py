"""R0 토큰화·TF-IDF 공식·안정 순위와 기존 실험 순위 회귀 시험."""

import json
import math
from pathlib import Path

import pytest

from securecode_context.symbols.index import build_index
from securecode_context.symbols.retrieval import TfidfRetriever, prepare_retrieval, words
from support.symbol_projects import write_project

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "r0_regression.json"


def test_words_keep_camel_and_underscore_parts() -> None:
    """
    함수 이름: test_words_keep_camel_and_underscore_parts()
    기능: camelCase 분리, 밑줄 복합어와 부분, 한 글자 제거, 한글 미토큰화를 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    assert words("loadConfig MAX_ITEMS x 42") == [
        "load",
        "config",
        "max_items",
        "max",
        "items",
        "42",
    ]
    assert words("설정 파일을 읽는 함수는?") == []
    assert words("HTTPServer") == ["httpserver"]


def test_tfidf_formula_and_stable_ties() -> None:
    """
    함수 이름: test_tfidf_formula_and_stable_ties()
    기능: IDF=ln((N+1)/(df+1))+1, TF=1+ln(count), L2 정규화와 동점의 ID 순 정렬을 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    retriever = TfidfRetriever({"b": "alpha alpha beta", "a": "alpha beta", "c": "gamma"})
    assert retriever.idf["alpha"] == pytest.approx(math.log(4 / 3) + 1)
    assert retriever.idf["gamma"] == pytest.approx(math.log(4 / 2) + 1)
    assert retriever.unseen_idf == pytest.approx(math.log(4) + 1)
    alpha = (1 + math.log(2)) * retriever.idf["alpha"]
    beta = retriever.idf["beta"]
    norm = math.sqrt(alpha * alpha + beta * beta)
    assert retriever.vectors["b"]["alpha"] == pytest.approx(alpha / norm)
    ranked = retriever.ranked("beta")
    assert [item_id for _, item_id in ranked][-1] == "c" and ranked[-1][0] == 0
    tied = TfidfRetriever({"z": "same words", "m": "same words"}).ranked("same")
    assert [item_id for _, item_id in tied] == ["m", "z"]
    assert all(0 <= score <= 1 + 1e-12 for score, _ in ranked)


def test_rankings_match_experiment(tmp_path: Path) -> None:
    """
    함수 이름: test_rankings_match_experiment()
    기능: 기존 실험 Retriever가 고정 프로젝트 7개·질문 104개에 낸 상위 10개 순위·점수를
        제품 스캐너+TF-IDF가 그대로 재현하는지 확인한다(fixture는 실험 코드로 한 번 생성).
    인자: tmp_path -> 임시 프로젝트 폴더
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    prepared = {}
    for project, files in fixture["projects"].items():
        root = tmp_path / project
        write_project(root, files)
        index = build_index(root)
        prepared[project] = prepare_retrieval(1, index["nodes"], index["raw"])
    assert len(fixture["queries"]) == 104
    for query in fixture["queries"]:
        ranked = prepared[query["project"]].retriever.ranked(query["question"])[:10]
        assert [item_id for _, item_id in ranked] == [item[0] for item in query["top"]], query[
            "task_id"
        ]
        for (score, _), (_, expected) in zip(ranked, query["top"], strict=True):
            assert score == pytest.approx(expected, abs=1e-12)


def test_candidate_depth_and_boundary(tmp_path: Path) -> None:
    """
    함수 이름: test_candidate_depth_and_boundary()
    기능: 참조 사슬 a→b→c→d→e에서 깊이 3까지만 포함하고 e를 depth_limit 경계로 기록한다.
    인자: tmp_path -> 임시 프로젝트
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    chain = "".join(
        f"def {name}():\n    return {following}()\n\n\n"
        for name, following in zip("abcd", "bcde", strict=True)
    )
    write_project(tmp_path, {"chain.py": chain + "def e():\n    return 1\n"})
    index = build_index(tmp_path)
    prepared = prepare_retrieval(1, index["nodes"], index["raw"])
    info = prepared.infos["memory://symbol/chain.py::a"]
    assert [uri.rsplit("::", 1)[1] for uri in info.members] == ["a", "b", "c", "d"]
    assert info.depth == 3
    assert info.boundary == (("memory://symbol/chain.py::e", "depth_limit"),)
    atomic = prepared.infos["atomic:memory://symbol/chain.py::a"]
    assert (atomic.members, atomic.depth, atomic.boundary) == (info.members[:1], 0, ())
