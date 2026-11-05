"""환경변수에서 서비스 설정을 읽고 loopback·토큰 정책을 강제한다. 이름은 루트 .env.example과 같다."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

LOOPBACK_HOSTS = ("127.0.0.1", "::1")
MIN_INTERNAL_TOKEN_CHARS = 32
LOG_LEVELS = ("debug", "info", "warn", "error")


class SettingsError(ValueError):
    """
    클래스 이름: SettingsError
    기능: 잘못된 서비스 설정. 메시지에 비밀값을 넣지 않는다.
    작성 날짜: 2026/11/04
    """


@dataclass(frozen=True)
class ServiceSettings:
    """
    클래스 이름: ServiceSettings
    기능: context-service 기동에 필요한 검증된 설정 값을 담는다.
    작성 날짜: 2026/11/04
    """

    host: str
    port: int
    internal_token: str
    data_dir: Path
    provider_id: str
    model_id: str
    api_key: str | None
    provider_base_url: str | None
    token_count_timeout_seconds: float
    log_level: str


def _read_int(environ: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    """
    함수 이름: _read_int()
    기능: 정수 환경변수를 읽고 범위를 검사한다.
    인자: environ -> 환경변수 사전
        name -> 변수 이름
        default -> 값이 없을 때 쓸 기본값
        low -> 허용 최솟값
        high -> 허용 최댓값
    반환값: 검사한 정수
    작성 날짜: 2026/11/04
    """
    raw_value = environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise SettingsError(f"{name} must be an integer") from error
    if not low <= value <= high:
        raise SettingsError(f"{name} must be between {low} and {high}")
    return value


def _provider_url(value: str) -> str | None:
    """
    함수 이름: _provider_url()
    기능: API 키를 보낼 URL은 HTTPS나 명시적인 로컬 HTTP만 허용한다.
    인자: value -> 설정한 provider 기본 URL
    반환값: 검증한 URL 또는 기본값용 None
    작성 날짜: 2026/11/05
    """
    if not value:
        return None
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise SettingsError("invalid SECURECODE_PROVIDER_BASE_URL") from None
    local_http = url.scheme == "http" and url.host in {*LOOPBACK_HOSTS, "localhost"}
    if (
        not url.host
        or url.userinfo
        or url.query
        or url.fragment
        or not (url.scheme == "https" or local_http)
    ):
        raise SettingsError(
            "SECURECODE_PROVIDER_BASE_URL requires HTTPS or loopback HTTP without credentials/query"
        )
    return value


def load_settings(environ: Mapping[str, str]) -> ServiceSettings:
    """
    함수 이름: load_settings()
    기능: 환경변수에서 설정을 만들고 loopback 주소·내부 토큰 길이·데이터 경로를 강제한다.
    인자: environ -> 환경변수 사전(os.environ 또는 시험용 사전)
    반환값: ServiceSettings
    작성 날짜: 2026/11/04
    """
    host = environ.get("SECURECODE_CONTEXT_SERVICE_HOST", "127.0.0.1").strip()
    if host not in LOOPBACK_HOSTS:
        raise SettingsError("context-service must bind to 127.0.0.1 or ::1")

    internal_token = environ.get("SECURECODE_INTERNAL_TOKEN", "")
    if len(internal_token) < MIN_INTERNAL_TOKEN_CHARS:
        raise SettingsError(
            f"SECURECODE_INTERNAL_TOKEN must be at least {MIN_INTERNAL_TOKEN_CHARS} characters"
        )

    if not all("!" <= char <= "~" for char in internal_token):
        raise SettingsError("SECURECODE_INTERNAL_TOKEN requires printable non-space ASCII")

    data_dir_value = environ.get("SECURECODE_DATA_DIR", "").strip()
    if not data_dir_value:
        raise SettingsError("SECURECODE_DATA_DIR is required")
    data_dir = Path(data_dir_value).resolve()

    log_level = environ.get("SECURECODE_LOG_LEVEL", "info").strip().lower() or "info"
    if log_level not in LOG_LEVELS:
        raise SettingsError(f"SECURECODE_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")

    timeout_ms = _read_int(environ, "SECURECODE_TOKEN_COUNT_TIMEOUT_MS", 10000, 100, 120000)
    model_id = environ.get("SECURECODE_MODEL_ID", "").strip() or "claude-sonnet-5-5"
    if len(model_id) > 128:
        raise SettingsError("SECURECODE_MODEL_ID exceeds 128 characters")
    return ServiceSettings(
        host=host,
        port=_read_int(environ, "SECURECODE_CONTEXT_SERVICE_PORT", 8788, 1, 65535),
        internal_token=internal_token,
        data_dir=data_dir,
        provider_id=environ.get("SECURECODE_PROVIDER_ID", "anthropic").strip() or "anthropic",
        model_id=model_id,
        api_key=environ.get("ANTHROPIC_API_KEY", "").strip() or None,
        provider_base_url=_provider_url(environ.get("SECURECODE_PROVIDER_BASE_URL", "").strip()),
        token_count_timeout_seconds=timeout_ms / 1000,
        log_level=log_level,
    )
