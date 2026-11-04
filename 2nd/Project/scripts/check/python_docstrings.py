"""CODING_CONVENTIONS.md 5절 docstring 검사. 함수·클래스마다 정해진 필드와 작성 날짜가 있는지 본다."""

import ast
import io
import json
import sys
from pathlib import Path

WORK_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = WORK_ROOT / "services" / "context-service"
FUNCTION_FIELDS = ("함수 이름:", "기능:", "인자:", "반환값:", "작성 날짜:")
CLASS_FIELDS = ("클래스 이름:", "기능:", "작성 날짜:")
EXIT_PASS, EXIT_FAIL, EXIT_KNOWN = 0, 1, 3


def load_baseline_paths() -> list[str]:
    """
    함수 이름: load_baseline_paths()
    기능: structure-baseline.json에서 python-docstring 규칙의 예외 경로를 읽는다.
    인자: 없음
    반환값: 작업 루트 기준 경로 목록(끝이 /이면 디렉토리 접두사)
    작성 날짜: 2026/11/04
    """
    baseline = json.loads(
        (WORK_ROOT / "scripts" / "check" / "structure-baseline.json").read_text(encoding="utf-8")
    )
    return [entry["path"] for entry in baseline["entries"] if entry["rule"] == "python-docstring"]


def is_baselined(relative_path: str, baseline_paths: list[str]) -> bool:
    """
    함수 이름: is_baselined()
    기능: 파일이 baseline 예외 목록에 있는지 확인한다.
    인자: relative_path -> 작업 루트 기준 POSIX 경로
        baseline_paths -> 예외 경로 목록
    반환값: 예외이면 True
    작성 날짜: 2026/11/04
    """
    return any(
        relative_path.startswith(path) if path.endswith("/") else relative_path == path
        for path in baseline_paths
    )


def find_missing_fields(source: str) -> list[str]:
    """
    함수 이름: find_missing_fields()
    기능: 소스의 모든 함수·클래스 docstring에서 빠진 필드를 찾는다.
    인자: source -> Python 소스 문자열
    반환값: "줄:이름: 빠진 필드" 형식의 문제 목록
    작성 날짜: 2026/11/04
    """
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            required = FUNCTION_FIELDS
        elif isinstance(node, ast.ClassDef):
            required = CLASS_FIELDS
        else:
            continue
        docstring = ast.get_docstring(node) or ""
        missing = [field for field in required if field not in docstring]
        if missing:
            problems.append(f"{node.lineno}:{node.name}: missing {', '.join(missing)}")
    return problems


def main() -> int:
    """
    함수 이름: main()
    기능: context-service의 src·tests와 scripts의 Python 파일을 검사하고 결과를 출력한다.
    인자: 없음
    반환값: 0 통과, 1 새 위반, 3 baseline 위반만 남음
    작성 날짜: 2026/11/04
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # 콘솔 기본 cp949 대신 UTF-8로 출력한다.
    baseline_paths = load_baseline_paths()
    roots = [SERVICE_ROOT / "src", SERVICE_ROOT / "tests", WORK_ROOT / "scripts"]
    paths = sorted(path for root in roots for path in root.rglob("*.py"))
    paths.append(SERVICE_ROOT / "main.py")
    failures = known = 0

    for path in paths:
        relative_path = path.relative_to(WORK_ROOT).as_posix()
        problems = find_missing_fields(path.read_text(encoding="utf-8"))
        if not problems:
            continue
        label = "KNOWN" if is_baselined(relative_path, baseline_paths) else "FAIL"
        known += label == "KNOWN"
        failures += label == "FAIL"
        sys.stdout.write(f"{label} {relative_path}: {len(problems)} item(s), first {problems[0]}\n")

    sys.stdout.write(f"python docstrings: {failures} failing file(s), {known} baseline file(s)\n")
    if failures:
        return EXIT_FAIL
    return EXIT_KNOWN if known else EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
