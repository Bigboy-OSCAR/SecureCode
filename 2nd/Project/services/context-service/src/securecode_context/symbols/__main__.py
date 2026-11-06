"""로컬 R0 원문 인덱스를 JSON 파일 또는 작업 공간 revision 저장소에 생성하는 명령행 진입점."""

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from securecode_context.common.errors import ServiceError

from .graph import IndexCapacityError
from .index import RevisionStore, SymbolIndexService, build_index


def _write_json_file(root: Path, output: Path) -> str:
    """
    함수 이름: _write_json_file()
    기능: 프로젝트에서 R0 후보를 생성해 완성된 JSON만 출력 경로에 게시한다.
    인자: root -> 프로젝트 디렉터리, output -> .json 출력 경로
    반환값: 사용자에게 보여줄 요약 한 줄
    작성 날짜: 2026/11/05
    """
    temp_path: Path | None = None
    try:
        index = build_index(root, output=output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, prefix=".r0-", delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            json.dump(index, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temp_path, output)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return (
        f"{len(index['nodes'])} symbols, {len(index['raw'])} R0 candidates, "
        f"{len(index['diagnostics'])} file diagnostics -> {output}"
    )


def _publish_revision(root: Path, store_dir: Path, workspace_id: str) -> str:
    """
    함수 이름: _publish_revision()
    기능: 작업 공간 revision을 새로 만들어 원자적으로 전환하고 상태 응답을 출력한다.
    인자: root -> 프로젝트 디렉터리, store_dir -> 작업 공간 데이터 루트, workspace_id -> ID
    반환값: IndexStatusResponse JSON 문자열(원문 미포함)
    작성 날짜: 2026/11/05
    """
    service = SymbolIndexService(RevisionStore(store_dir))
    status = service.build(workspace_id, root.absolute())
    return json.dumps(status, ensure_ascii=False, indent=2)


def main() -> None:
    """
    함수 이름: main()
    기능: --out 이면 로컬 JSON을, --store 이면 작업 공간 revision을 생성한다.
    인자: 없음(명령행에서 루트와 출력 방식을 받음)
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    parser = argparse.ArgumentParser(
        description="Build an R0 index for Python, C, C++, Java and JavaScript."
    )
    parser.add_argument("root", type=Path, help="workspace directory")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="write the local R0 index to this JSON file")
    target.add_argument("--store", type=Path, help="publish a revision under this data directory")
    parser.add_argument("--workspace-id", help="ws_ identifier, required with --store")
    args = parser.parse_args()
    if args.out is not None and args.out.suffix.lower() != ".json":
        parser.error("--out must be a .json file")
    if args.store is not None and not args.workspace_id:
        parser.error("--workspace-id is required with --store")
    try:
        if args.out is not None:
            message = _write_json_file(args.root, args.out)
        else:
            message = _publish_revision(args.root, args.store, args.workspace_id)
    except IndexCapacityError as error:
        parser.exit(1, f"R0 index build failed: {error}. Select a smaller project directory.\n")
    except ServiceError as error:
        parser.exit(1, f"R0 index build failed: {error.code}: {error.message}\n")
    except OSError as error:
        parser.exit(1, f"R0 index build failed: {error}\n")
    sys.stdout.write(message + "\n")


if __name__ == "__main__":
    main()
