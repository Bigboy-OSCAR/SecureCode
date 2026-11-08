"""심볼 색인 시험용 fixture 프로젝트. 저장소 lint 대상이 되지 않도록 시험 중 임시 폴더에 생성한다."""

from pathlib import Path

PYTHON_PROJECT = {
    "pkg/constants.py": "RATE = 3\n",
    "pkg/helpers.py": "from .constants import RATE as R\n\n\ndef scale(x):\n    return x * R\n",
    "pkg/service.py": (
        "from pkg.helpers import scale\n"
        "\n"
        "\n"
        "def traced(fn):\n"
        "    return fn\n"
        "\n"
        "\n"
        "@traced\n"
        "def compute(x):\n"
        "    return scale(x) + getattr(x, 'dynamic')()\n"
    ),
}
C_PROJECT = {
    "limits.h": "static const int MAX_ITEMS = 8;\nstruct box { int size; };\nint clamp(int value);\n",
    "main.c": (
        '#include "limits.h"\n'
        "int clamp(int value) { return value > MAX_ITEMS ? MAX_ITEMS : value; }\n"
        "int run(struct box *item) { return clamp(item->size); }\n"
    ),
}
CPP_PROJECT = {
    "shape.hpp": "namespace geo {\nclass Shape {\npublic:\n    int area() const { return 4; }\n};\n}\n",
    "main.cpp": '#include "shape.hpp"\nint total() {\n    geo::Shape shape;\n    return shape.area();\n}\n',
}
JAVA_PROJECT = {
    "src/com/acme/Limits.java": "package com.acme;\npublic class Limits { public static final int MAX = 5; }\n",
    "src/com/acme/app/Main.java": (
        "package com.acme.app;\n"
        "import com.acme.Limits;\n"
        "public class Main {\n"
        "    int run() { return Limits.MAX; }\n"
        "}\n"
    ),
}
JAVASCRIPT_PROJECT = {
    "lib/math.mjs": "export const BASE = 2;\nexport function double(x) { return x * BASE; }\n",
    "main.js": "import { double as twice } from './lib/math.mjs';\nexport const run = (x) => twice(x);\n",
    "util.cjs": "function size() { return 1; }\nmodule.exports = { size };\n",
    "legacy.cjs": "const util = require('./util.cjs');\nfunction go() { return util.size(); }\n",
}
LANGUAGE_PROJECTS = {
    "python": PYTHON_PROJECT,
    "c": C_PROJECT,
    "cpp": CPP_PROJECT,
    "java": JAVA_PROJECT,
    "javascript": JAVASCRIPT_PROJECT,
}
# 같은 이름 helper가 세 언어에 있고 각 언어 안에서만 연결돼야 한다. 순환 참조도 포함한다.
SHARED_NAME_FILES = {
    "shared/helper.py": "def helper():\n    return 1\n",
    "shared/use.py": "from shared.helper import helper\n\n\ndef use_py():\n    return helper()\n",
    "shared/helper.c": "int helper(void) { return 2; }\nint use_c(void) { return helper(); }\n",
    "shared/helper.mjs": "export function helper() { return 3; }\n",
    "shared/use.mjs": "import { helper } from './helper.mjs';\nexport function useJs() { return helper(); }\n",
    "cycle/a.py": "from cycle.b import pong\n\n\ndef ping():\n    return pong()\n",
    "cycle/b.py": "from cycle.a import ping\n\n\ndef pong():\n    return ping()\n",
}
BROKEN_FILES = {
    "broken/bad.py": "def broken(:\n",
    "broken/bad.c": "int broken( {\n",
    "broken/Bad.java": "class Bad {{{\n",
    "broken/bad.js": "function broken( {\n",
    "broken/types.ts": "export const typed: number = 1;\n",
}
EXCLUDED_FILES = {
    ".git/hooks.py": "def hidden(): return 1\n",
    ".securecode/cache.py": "def cached(): return 1\n",
    "node_modules/pkg/index.js": "export const VENDOR = 1;\n",
    "venv/lib/site.py": "def site(): return 1\n",
    "build/out.c": "int built(void) { return 1; }\n",
    "generated/gen.java": "class Gen {}\n",
}


def write_project(root: Path, files: dict[str, str]) -> None:
    """
    함수 이름: write_project()
    기능: 상대 경로별 원문을 줄바꿈 변환 없이 UTF-8 바이트로 쓴다.
    인자: root -> 프로젝트 루트, files -> 상대 경로와 원문
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode("utf-8"))
