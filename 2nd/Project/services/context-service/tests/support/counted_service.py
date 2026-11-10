"""[시험 전용] 실제 context-service 앱을 결정적 시험 계수기로 띄운다(host SDK 통합 시험용).

운영 진입점(`python -m securecode_context.app`)과 같은 설정·앱을 쓰고 TokenCounter만 FixedTokenCounter로
바꾼다. 실행: `PYTHONPATH=src:tests python -m support.counted_service`. 제품 코드가 import하지 않는다.
"""

import json
import os
import sys
from pathlib import Path

import uvicorn

from securecode_context.app.factory import create_app
from securecode_context.app.settings import SettingsError, load_settings
from securecode_context.common.tokens import CountMode
from support.helpers import FixedTokenCounter
from support.source_fixtures import FixedRoots


def main() -> int:
    """
    함수 이름: main()
    기능: 환경변수 설정으로 loopback에 서비스를 띄운다.
    인자: 없음
    반환값: 종료 코드(설정 오류는 2)
    작성 날짜: 2026/11/10
    """
    try:
        settings = load_settings(os.environ)
    except SettingsError as error:
        sys.stderr.write(f"counted service settings error: {error}\n")
        return 2
    counter = FixedTokenCounter()
    if os.environ.get("SECURECODE_TEST_REQUEST_COUNT_MODE") == "exact":
        # 시험 전용: hard-cap 모드의 허용 경로를 확인하려고 요청 계수를 exact로 표시한다.
        counter.request_mode = CountMode.EXACT
    if os.environ.get("SECURECODE_TEST_REQUEST_FRAMING") == "openai_chat":
        # 시험 전용: OpenAI 호환(llama.cpp) 요청 framing을 실제 SDK 본문으로 확인한다.
        counter.request_framing = "openai_chat"
        counter.model_id = os.environ.get("SECURECODE_MODEL_ID", counter.model_id)
    roots_env = os.environ.get("SECURECODE_TEST_WORKSPACE_ROOTS")
    # 시험 전용: {"ws_...": "절대 경로"} JSON으로 Source 등록부의 작업 공간 root를 연결한다.
    roots = (
        FixedRoots({k: Path(v) for k, v in json.loads(roots_env).items()}) if roots_env else None
    )
    app = create_app(settings, token_counter=counter, workspace_roots=roots)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
