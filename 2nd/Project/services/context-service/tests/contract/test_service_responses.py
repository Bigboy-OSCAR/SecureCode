"""실제 FastAPI 앱 응답(health·tokens·오류)이 계약 스키마와 맞는지 TestClient로 검사한다."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter

ERROR_REF = "common/api-error.schema.json#/definitions/ErrorResponse"
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(service_settings: ServiceSettings) -> Iterator[TestClient]:
    """
    함수 이름: client()
    기능: 키가 없는 기본 설정(미설정 계수기)으로 앱 client를 만든다.
    인자: service_settings -> 시험 설정
    반환값: TestClient
    작성 날짜: 2026/11/04
    """
    with TestClient(create_app(service_settings)) as test_client:
        yield test_client


@pytest.fixture
def counting_client(service_settings: ServiceSettings) -> Iterator[TestClient]:
    """
    함수 이름: counting_client()
    기능: 고정 계수기를 주입한 앱 client를 만든다.
    인자: service_settings -> 시험 설정
    반환값: TestClient
    작성 날짜: 2026/11/04
    """
    app = create_app(service_settings, token_counter=FixedTokenCounter())
    with TestClient(app) as test_client:
        yield test_client


def test_health_matches_contract(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_health_matches_contract()
    기능: health가 ServiceHealthResponse이고 미구현 기능을 not_implemented로 표시하는지 확인한다.
    인자: client -> 앱 client
        contract_check -> 계약 검사 함수
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    response = client.get("/internal/v1/health", headers=AUTH)
    body = response.json()
    assert response.status_code == 200
    assert contract_check("api/system.schema.json#/definitions/ServiceHealthResponse", body) == []
    statuses = {component["name"]: component["status"] for component in body["components"]}
    assert statuses["token_counter"] == "not_configured"
    assert statuses["symbols"] == "not_implemented"
    assert response.headers["X-Request-Id"].startswith("req_")


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 401, "UNAUTHENTICATED"),
        ({"Authorization": "Bearer wrong-token"}, 401, "UNAUTHENTICATED"),
        ({**AUTH, "Origin": "http://127.0.0.1:5173"}, 403, "ORIGIN_REJECTED"),
    ],
)
def test_internal_auth_rejections(
    client: TestClient,
    contract_check: ContractCheck,
    headers: dict[str, str],
    status: int,
    code: str,
) -> None:
    """
    함수 이름: test_internal_auth_rejections()
    기능: 토큰 누락·불일치와 브라우저 Origin을 계약 오류로 거절하는지 확인한다.
    인자: client -> 앱 client
        contract_check -> 계약 검사 함수
        headers -> 보낼 헤더
        status -> 기대 HTTP 상태
        code -> 기대 오류 코드
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    response = client.get("/internal/v1/health", headers=headers)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert contract_check(ERROR_REF, response.json()) == []
    assert TEST_TOKEN not in response.text


def test_token_count_success(counting_client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_token_count_success()
    기능: tokens.count 응답이 TokenCountResult 계약과 맞는지 확인한다.
    인자: counting_client -> 고정 계수기 client
        contract_check -> 계약 검사 함수
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    response = counting_client.post(
        "/internal/v1/tokens/count", headers=AUTH, json={"text": "사용자 😀"}
    )
    assert response.status_code == 200
    assert (
        contract_check(
            "common/token-count.schema.json#/definitions/TokenCountResult", response.json()
        )
        == []
    )
    assert response.json()["text_bytes"] == len("사용자 😀".encode())


@pytest.mark.parametrize(
    ("raw_body", "status", "code"),
    [
        ('{"text": ""}', 422, "VALIDATION_FAILED"),
        ('{"text": "x", "extra": 1}', 422, "VALIDATION_FAILED"),
        ('{"text": "\\ud800"}', 422, "VALIDATION_FAILED"),
    ],
)
def test_token_count_validation(
    counting_client: TestClient,
    contract_check: ContractCheck,
    raw_body: str,
    status: int,
    code: str,
) -> None:
    """
    함수 이름: test_token_count_validation()
    기능: 빈 본문·추가 필드·외톨이 surrogate가 입력 원문 없이 VALIDATION_FAILED로 거절되는지 확인한다.
    인자: counting_client -> 고정 계수기 client
        contract_check -> 계약 검사 함수
        raw_body -> 보낼 JSON 문자열
        status -> 기대 HTTP 상태
        code -> 기대 오류 코드
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    response = counting_client.post(
        "/internal/v1/tokens/count",
        headers={**AUTH, "Content-Type": "application/json"},
        content=raw_body.encode(),
    )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert contract_check(ERROR_REF, response.json()) == []


def test_unconfigured_counter_and_unknown_route(
    client: TestClient, contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_unconfigured_counter_and_unknown_route()
    기능: 키가 없으면 503 TOKENIZER_UNAVAILABLE, 없는 경로는 404 NOT_FOUND인지 확인한다.
    인자: client -> 앱 client
        contract_check -> 계약 검사 함수
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    counted = client.post("/internal/v1/tokens/count", headers=AUTH, json={"text": "x"})
    assert (counted.status_code, counted.json()["error"]["code"]) == (503, "TOKENIZER_UNAVAILABLE")
    assert contract_check(ERROR_REF, counted.json()) == []

    missing = client.get("/internal/v1/nothing", headers=AUTH)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert contract_check(ERROR_REF, missing.json()) == []
