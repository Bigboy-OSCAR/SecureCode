"""3.6 재현 Windows 공유 위반: 색인 게시(os.replace)와 상태 조회(current.json 읽기)가 겹쳐도 오류가 없어야 한다."""

import threading
from pathlib import Path

from securecode_context.symbols.index import RevisionStore, SymbolIndexService
from support.symbol_projects import LANGUAGE_PROJECTS, write_project


def test_status_during_build_never_fails(tmp_path: Path) -> None:
    """
    함수 이름: test_status_during_build_never_fails()
    기능: 백그라운드 색인 중 상태를 계속 조회해도 예외가 없고 색인이 끝까지 게시되는지 본다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    errors: list[str] = []
    for trial in range(5):
        root = tmp_path / f"project{trial}"
        write_project(root, LANGUAGE_PROJECTS["python"])
        index = SymbolIndexService(RevisionStore(tmp_path / f"data{trial}"))
        build = threading.Thread(target=index.build, args=("ws_00000001", root))
        build.start()
        while build.is_alive():
            try:
                index.status("ws_00000001", root)
            except Exception as error:
                errors.append(type(error).__name__)
        build.join()
        assert index.status("ws_00000001", root)["index_status"] in ("ready", "partial")
    assert errors == []
