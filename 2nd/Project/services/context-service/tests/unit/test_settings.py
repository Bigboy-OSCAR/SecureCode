"""설정 검증: loopback 바인딩·내부 토큰 길이·데이터 경로 강제."""

import pytest

from securecode_context.app.settings import SettingsError, load_settings

VALID_ENV = {
    "SECURECODE_INTERNAL_TOKEN": "x" * 32,
    "SECURECODE_DATA_DIR": ".securecode-test",
}


def test_defaults_bind_to_loopback() -> None:
    """
    함수 이름: test_defaults_bind_to_loopback()
    기능: 기본값이 127.0.0.1:8788이고 키가 없으면 None인지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    settings = load_settings(VALID_ENV)
    assert (settings.host, settings.port, settings.api_key) == ("127.0.0.1", 8788, None)
    assert settings.data_dir.is_absolute()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"SECURECODE_CONTEXT_SERVICE_HOST": "0.0.0.0"}, "127.0.0.1"),
        ({"SECURECODE_INTERNAL_TOKEN": "short"}, "at least 32"),
        ({"SECURECODE_DATA_DIR": ""}, "SECURECODE_DATA_DIR"),
        ({"SECURECODE_CONTEXT_SERVICE_PORT": "70000"}, "between"),
        ({"SECURECODE_LOG_LEVEL": "trace"}, "SECURECODE_LOG_LEVEL"),
    ],
)
def test_rejects_unsafe_settings(override: dict[str, str], message: str) -> None:
    """
    함수 이름: test_rejects_unsafe_settings()
    기능: 외부 바인딩·짧은 토큰·누락 경로·잘못된 포트/레벨을 거절하는지 확인한다.
    인자: override -> 바꿀 환경변수
        message -> 오류 메시지에 있어야 할 문구
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    with pytest.raises(SettingsError, match=message):
        load_settings({**VALID_ENV, **override})


def test_error_message_never_contains_token() -> None:
    """
    함수 이름: test_error_message_never_contains_token()
    기능: 토큰 길이 오류 메시지에 토큰 값이 들어가지 않는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    with pytest.raises(SettingsError) as error_info:
        load_settings({**VALID_ENV, "SECURECODE_INTERNAL_TOKEN": "leak-me"})
    assert "leak-me" not in str(error_info.value)
