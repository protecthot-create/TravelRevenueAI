"""Изолированные focused-тесты Clerk Auth Foundation без PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from clerk_backend_api.security import AuthStatus, RequestState, TokenVerificationErrorReason
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from travel_revenue_ai.config import Settings
from travel_revenue_ai.security import clerk_auth
from travel_revenue_ai.security.clerk_auth import require_principal
from travel_revenue_ai.security.principal import Principal

ISSUER = "https://clerk.example.test"
TOKEN = "test-token"
UNSUPPORTED_TOKEN = "test-unsupported-token"
CONFIG_VALUE = "test-config-value"
VERIFICATION_VALUE = "test-verification-value"


class FakeClerkClient:
    """Минимальный async seam для проверки вызова Clerk SDK."""

    def __init__(self) -> None:
        self.result = RequestState(
            AuthStatus.SIGNED_IN,
            payload={"iss": ISSUER, "sub": "user_123"},
        )
        self.error: Exception | None = None
        self.options: Any = None
        self.call_count = 0

    async def authenticate_request_async(self, request: Any, options: Any) -> RequestState:
        """Запоминает options и возвращает заданное состояние SDK."""
        self.call_count += 1
        self.options = options
        if request.headers.get("Authorization", "").endswith(UNSUPPORTED_TOKEN):
            return RequestState(AuthStatus.SIGNED_OUT)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture()
def test_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, FakeClerkClient]]:
    """Создаёт приложение с единственным защищённым probe endpoint."""
    fake_client = FakeClerkClient()
    monkeypatch.setattr(
        clerk_auth,
        "settings",
        Settings(
            clerk_jwt_key=VERIFICATION_VALUE,
            clerk_secret_key=CONFIG_VALUE,
            clerk_issuer=ISSUER,
            _env_file=None,
        ),
    )
    monkeypatch.setattr(clerk_auth, "get_clerk_client", lambda: fake_client)

    app = FastAPI()

    @app.get("/protected")
    async def protected(principal: Principal = Depends(require_principal)) -> dict[str, str]:
        """Возвращает Principal только для проверки dependency."""
        return {
            "subject_id": principal.subject_id,
            "issuer": principal.issuer,
            "token_type": principal.token_type,
        }

    yield app, fake_client


def _request(
    app: FastAPI,
    authorization: str | None = f"Bearer {TOKEN}",
    *,
    headers: dict[str, str] | None = None,
):
    """Выполняет запрос к изолированному endpoint."""
    request_headers = dict(headers or {})
    if authorization is not None:
        request_headers["Authorization"] = authorization
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.get("/protected", headers=request_headers)


def test_missing_authorization_returns_uniform_401(
    test_app: tuple[FastAPI, FakeClerkClient],
) -> None:
    response = _request(test_app[0], authorization=None)
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert test_app[1].call_count == 0


@pytest.mark.parametrize("authorization", ["Bearer", "Bearer ", "Basic token", "Bearer a b"])
def test_malformed_bearer_returns_401(
    test_app: tuple[FastAPI, FakeClerkClient], authorization: str
) -> None:
    response = _request(test_app[0], authorization=authorization)
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
    assert test_app[1].call_count == 0


def test_cookie_only_authentication_returns_401(
    test_app: tuple[FastAPI, FakeClerkClient],
) -> None:
    response = _request(
        test_app[0], authorization=None, headers={"Cookie": f"__session={TOKEN}"}
    )
    assert response.status_code == 401
    assert test_app[1].call_count == 0


@pytest.mark.parametrize(
    "reason",
    [
        TokenVerificationErrorReason.TOKEN_INVALID_SIGNATURE,
        TokenVerificationErrorReason.TOKEN_EXPIRED,
    ],
)
def test_invalid_signature_and_expired_token_return_401(
    test_app: tuple[FastAPI, FakeClerkClient], reason: TokenVerificationErrorReason
) -> None:
    test_app[1].result = RequestState(AuthStatus.SIGNED_OUT, reason=reason)
    response = _request(test_app[0])
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_wrong_issuer_returns_401(test_app: tuple[FastAPI, FakeClerkClient]) -> None:
    test_app[1].result = RequestState(
        AuthStatus.SIGNED_IN,
        payload={"iss": "https://wrong.test", "sub": "user_123"},
    )
    response = _request(test_app[0])
    assert response.status_code == 401


def test_missing_sub_returns_401(test_app: tuple[FastAPI, FakeClerkClient]) -> None:
    test_app[1].result = RequestState(AuthStatus.SIGNED_IN, payload={"iss": ISSUER})
    response = _request(test_app[0])
    assert response.status_code == 401


def test_missing_payload_returns_401(test_app: tuple[FastAPI, FakeClerkClient]) -> None:
    test_app[1].result = RequestState(AuthStatus.SIGNED_IN)
    response = _request(test_app[0])
    assert response.status_code == 401


def test_valid_session_token_returns_principal(
    test_app: tuple[FastAPI, FakeClerkClient],
) -> None:
    response = _request(test_app[0])
    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "user_123",
        "issuer": ISSUER,
        "token_type": "session_token",
    }


def test_principal_is_frozen_and_minimal() -> None:
    principal = Principal(subject_id="user_123", issuer=ISSUER, token_type="session_token")
    with pytest.raises(AttributeError):
        principal.subject_id = "other"  # type: ignore[misc]
    assert set(principal.__dataclass_fields__) == {"subject_id", "issuer", "token_type"}


def test_wrong_token_type_is_rejected_by_exact_options(
    test_app: tuple[FastAPI, FakeClerkClient],
) -> None:
    response = _request(test_app[0], authorization=f"Bearer {UNSUPPORTED_TOKEN}")
    assert response.status_code == 401
    assert test_app[1].options.accepts_token == ["session_token"]


def test_configured_audience_and_authorized_parties_are_forwarded(
    test_app: tuple[FastAPI, FakeClerkClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        clerk_auth,
        "settings",
        Settings(
            clerk_jwt_key=VERIFICATION_VALUE,
            clerk_issuer=ISSUER,
            clerk_audience="api://travel",
            clerk_authorized_parties=["https://app.example.test"],
            _env_file=None,
        ),
    )
    response = _request(test_app[0])
    assert response.status_code == 200
    assert test_app[1].options.audience == "api://travel"
    assert test_app[1].options.authorized_parties == ["https://app.example.test"]
    assert test_app[1].options.accepts_token == ["session_token"]


def test_jwt_key_has_priority_over_secret_key(
    test_app: tuple[FastAPI, FakeClerkClient],
) -> None:
    response = _request(test_app[0])
    assert response.status_code == 200
    assert test_app[1].options.jwt_key == VERIFICATION_VALUE
    assert test_app[1].options.secret_key is None


def test_missing_verification_key_is_401(
    test_app: tuple[FastAPI, FakeClerkClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clerk_auth, "settings", Settings(clerk_issuer=ISSUER, _env_file=None))
    response = _request(test_app[0])
    assert response.status_code == 401


def test_sdk_error_returns_401_without_secret_or_exception_leak(
    test_app: tuple[FastAPI, FakeClerkClient], caplog: pytest.LogCaptureFixture
) -> None:
    test_app[1].error = RuntimeError(f"config={CONFIG_VALUE} token={TOKEN}")
    with caplog.at_level(logging.WARNING, logger=clerk_auth.logger.name):
        response = _request(test_app[0])
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert CONFIG_VALUE not in caplog.text
    assert TOKEN not in caplog.text
    assert "authentication_failed" in caplog.text
