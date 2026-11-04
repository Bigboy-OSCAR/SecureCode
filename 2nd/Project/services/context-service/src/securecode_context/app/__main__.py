"""기동 진입점: `python -m securecode_context.app`. 설정 검증 → 로그 → loopback 바인딩만 한다."""

import logging
import os
import sys

import uvicorn

from securecode_context.app.factory import create_app
from securecode_context.app.logging_setup import configure_logging
from securecode_context.app.settings import SettingsError, load_settings
from securecode_context.common.redaction import Redactor


def main() -> int:
    """
    함수 이름: main()
    기능: 환경변수로 설정을 읽어 서비스를 127.0.0.1(또는 ::1)에서 실행한다.
    인자: 없음
    반환값: 프로세스 종료 코드(설정 오류는 2)
    작성 날짜: 2026/11/04
    """
    try:
        settings = load_settings(os.environ)
    except SettingsError as error:
        sys.stderr.write(f"context-service settings error: {error}\n")
        return 2

    secrets = [settings.internal_token] + ([settings.api_key] if settings.api_key else [])
    configure_logging(settings.log_level, Redactor(secrets))
    logging.getLogger("securecode_context").info(
        "starting context-service on %s:%d", settings.host, settings.port
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
