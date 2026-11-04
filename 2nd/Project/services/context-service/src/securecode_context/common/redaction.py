"""로그 redaction. TS(apps/host/src/logging/redaction.ts)와 같은 규칙을 공용 벡터로 검증한다."""

import logging
import re

MAX_LOG_CHARS = 2000

API_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")
BEARER_PATTERN = re.compile(r"(bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
KEY_VALUE_PATTERN = re.compile(
    r"\b(x-api-key|api[_-]?key|authorization|internal[_-]?token|token|secret|password)"
    r"(\"?\s*[:=]\s*\"?)(?!Bearer\b|\[REDACTED)[^\s\",;]+",
    re.IGNORECASE,
)
WINDOWS_HOME_PATTERN = re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+")
POSIX_HOME_PATTERN = re.compile(r"/(?:Users|home)/[^/\s\"']+")


class Redactor:
    """
    클래스 이름: Redactor
    기능: 로그 문자열에서 키·토큰·등록된 비밀값·사용자 홈 경로를 지우고 길이를 제한한다.
    작성 날짜: 2026/11/04
    """

    def __init__(self, secrets: list[str] | None = None, max_chars: int = MAX_LOG_CHARS) -> None:
        """
        함수 이름: __init__()
        기능: 실행 중 등록할 비밀값 목록과 메시지 최대 길이를 저장한다.
        인자: secrets -> 정확히 일치하면 지울 비밀값 목록(예: 내부 서비스 토큰)
            max_chars -> 메시지 최대 길이(code point)
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        self.secrets = [secret for secret in (secrets or []) if secret]
        self.max_chars = max_chars

    def add_secret(self, secret: str) -> None:
        """
        함수 이름: add_secret()
        기능: 실행 중 알게 된 비밀값을 지울 목록에 추가한다.
        인자: secret -> 등록할 비밀값
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        if secret and secret not in self.secrets:
            self.secrets.append(secret)

    def redact(self, text: str) -> str:
        """
        함수 이름: redact()
        기능: 등록 비밀값 → API 키 → Bearer → key=value → 홈 경로 순서로 지우고 길이를 자른다.
        인자: text -> 로그 메시지
        반환값: 안전하게 바뀐 메시지
        작성 날짜: 2026/11/04
        """
        redacted = text
        for secret in self.secrets:
            redacted = redacted.replace(secret, "[REDACTED:secret]")

        redacted = API_KEY_PATTERN.sub("[REDACTED:api_key]", redacted)
        redacted = BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
        redacted = KEY_VALUE_PATTERN.sub(r"\1\2[REDACTED]", redacted)
        redacted = WINDOWS_HOME_PATTERN.sub("<home>", redacted)
        redacted = POSIX_HOME_PATTERN.sub("<home>", redacted)

        if len(redacted) > self.max_chars:
            overflow = len(redacted) - self.max_chars
            redacted = f"{redacted[: self.max_chars]}...[truncated {overflow} chars]"
        return redacted


class RedactingFilter(logging.Filter):
    """
    클래스 이름: RedactingFilter
    기능: 모든 로그 레코드의 최종 메시지를 Redactor로 바꾼다. debug 레벨도 예외가 없다.
    작성 날짜: 2026/11/04
    """

    def __init__(self, redactor: Redactor) -> None:
        """
        함수 이름: __init__()
        기능: 사용할 Redactor를 저장한다.
        인자: redactor -> 공용 Redactor
        반환값: 없음
        작성 날짜: 2026/11/04
        """
        super().__init__()
        self.redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        """
        함수 이름: filter()
        기능: 인자를 합친 메시지를 redaction한 뒤 레코드에 다시 넣는다.
        인자: record -> 로그 레코드
        반환값: 항상 True(레코드를 버리지 않는다)
        작성 날짜: 2026/11/04
        """
        record.msg = self.redactor.redact(record.getMessage())
        record.args = None
        return True
