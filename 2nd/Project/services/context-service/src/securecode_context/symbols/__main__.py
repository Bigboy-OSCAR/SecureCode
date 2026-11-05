"""로컬 R0 원문 인덱스를 생성하는 명령행 진입점."""

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from .graph import IndexCapacityError
from .index import build_index


def main() -> None:
    """
    함수 이름: main()
    기능: 프로젝트에서 R0 후보를 생성해 완성된 JSON만 출력 경로에 게시한다.
    인자: 없음(명령행에서 루트와 JSON 출력 경로를 받음)
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    parser = argparse.ArgumentParser(
        description="Build an R0 index for Python, C, C++, Java and JavaScript."
    )
    parser.add_argument("root", type=Path, help="workspace directory")
    parser.add_argument(
        "--out", type=Path, required=True, help="write the local R0 index to this JSON file"
    )
    args = parser.parse_args()
    output: Path = args.out
    if output.suffix.lower() != ".json":
        parser.error("--out must be a .json file")
    temp_path: Path | None = None
    try:
        index = build_index(args.root, output=output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".r0-",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            json.dump(index, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temp_path, output)
    except IndexCapacityError as error:
        parser.exit(1, f"R0 index build failed: {error}. Select a smaller project directory.\n")
    except OSError as error:
        parser.exit(1, f"R0 index build failed: {error}\n")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    sys.stdout.write(
        f"{len(index['nodes'])} symbols, {len(index['raw'])} R0 candidates, "
        f"{len(index['diagnostics'])} file diagnostics -> {output}\n"
    )


if __name__ == "__main__":
    main()
