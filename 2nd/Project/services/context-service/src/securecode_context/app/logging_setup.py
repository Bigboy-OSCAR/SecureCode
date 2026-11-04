"""로그 설정: 모든 handler에 redaction 필터를 걸어 키·내부 토큰·홈 경로가 기록되지 않게 한다."""

import logging
import sys

from securecode_context.common.redaction import RedactingFilter, Redactor

LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


def configure_logging(level_name: str, redactor: Redactor) -> logging.Handler:
    """
    함수 이름: configure_logging()
    기능: root logger에 redaction 필터가 걸린 stderr handler 하나를 둔다. uvicorn logger도 root로 전파한다.
    인자: level_name -> debug/info/warn/error
        redactor -> 비밀값이 등록된 Redactor
    반환값: 설치한 handler
    작성 날짜: 2026/11/04
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter(redactor))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(LEVELS.get(level_name, logging.INFO))

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    return handler
