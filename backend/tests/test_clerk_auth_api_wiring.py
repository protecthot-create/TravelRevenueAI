"""Проверки подключения Clerk dependency к production API scope."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from clerk_backend_api.security import AuthStatus, RequestState
from fastapi.testclient import TestClient

from travel_revenue_ai.config import Settings
from travel_revenue_ai.database import get_db
from travel_revenue_ai.main import app
from travel_revenue_ai.security import clerk_auth
from travel_revenue_ai.security.clerk_auth import get_current_principal


ISSUER = "https://clerk.example.test"
VERIFICATION_KEY = "test-verification-key"
EXPECTED_PROTECTED_ROUTE_COUNT = 17
PUBLIC_PATHS = (
    "/health",
    "/health/live",
    "/health/ready",
    "/",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


@pytest.fixture()
def api_client() -> Iterator[TestClient]:
    """Создаёт клиент без запуска production startup validation."""
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def _api_router_contexts() -> list[object]:
    """Возвращает контексты подключённых routers для `/api/v1`."""
    return [
        route.include_context
        for route in app.routes
        if hasattr(route, "include_context")
        and route.include_context.prefix == "/api/v1"
    ]


def test_all_api_v1_routes_require_current_principal() -> None:
    """Каждый production API route подключён к общей auth dependency."""
    contexts = _api_router_contexts()
    route_count = sum(len(context.included_router.routes) for context in contexts)

    assert len(contexts) == 5
    assert route_count == EXPECTED_PROTECTED_ROUTE_COUNT
    assert all(
        any(
            dependency.dependency is get_current_principal
            for dependency in context.dependencies
        )
        for context in contexts
    )


def test_missing_bearer_returns_uniform_401_before_route_logic(
    api_client: TestClient,
) -> None:
    """Запрос к прикладному API без Bearer не доходит до БД или endpoint-кода."""
    response = api_client.get("/api/v1/signals")

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_cookie_only_authentication_returns_401(api_client: TestClient) -> None:
    """Cookie-only Clerk session не считается Bearer-аутентификацией API."""
    response = api_client.get("/api/v1/signals", cookies={"__session": "cookie-token"})

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_bearer_returns_uniform_401(api_client: TestClient) -> None:
    """Неполный или некорректный Bearer header получает единый 401."""
    response = api_client.get("/api/v1/signals", headers={"Authorization": "Bearer"})

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_valid_mocked_clerk_session_reaches_route_logic(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверенная mock-сессия проходит auth и доходит до production route logic."""
    authenticate_request = AsyncMock(
        return_value=RequestState(
            AuthStatus.SIGNED_IN,
            payload={"iss": ISSUER, "sub": "user_123"},
        )
    )
    class FakeClerkClient:
        """Минимальный mock-клиент Clerk для защищённого production router."""

        authenticate_request_async = authenticate_request

    fake_client = FakeClerkClient()
    monkeypatch.setattr(
        clerk_auth,
        "settings",
        Settings(
            clerk_jwt_key=VERIFICATION_KEY,
            clerk_issuer=ISSUER,
            _env_file=None,
        ),
    )
    monkeypatch.setattr(clerk_auth, "get_clerk_client", lambda: fake_client)
    monkeypatch.setattr(
        "travel_revenue_ai.api.v1.signals.SignalService.list_signals",
        lambda self, **kwargs: [],
    )

    def override_get_db() -> Iterator[object]:
        yield object()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = api_client.get(
            "/api/v1/signals",
            headers={"Authorization": "Bearer mocked-session-token"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == []
    assert authenticate_request.await_count == 1


def test_system_and_documentation_endpoints_do_not_require_clerk(
    api_client: TestClient,
) -> None:
    """Системные, мониторинговые и документационные endpoints остаются публичными."""
    responses = [api_client.get(path) for path in PUBLIC_PATHS]

    assert all(response.status_code != 401 for response in responses)
