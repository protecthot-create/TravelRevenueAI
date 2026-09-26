"""End-to-end integration-тесты onboarding → tenant context CS12.

Доказывает полный production flow без подмены provisioning: Clerk Principal
→ POST /api/v1/onboarding → AppUser/ExternalIdentity/Agency/membership
→ IdentityResolutionService → TenantAuthorizationService → protected API.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from travel_revenue_ai.database import get_db
from travel_revenue_ai.main import app
from travel_revenue_ai.models import (
    Agency,
    AgencyMembership,
    AppUser,
    Base,
    ExternalIdentity,
)
from travel_revenue_ai.security.clerk_auth import get_current_principal
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.identity_resolution_errors import (
    IdentityResolutionNotFoundError,
)
from travel_revenue_ai.services.identity_resolution_service import (
    IdentityResolutionService,
)
from travel_revenue_ai.services.tenant_authorization_service import (
    TenantAuthorizationService,
)

ISSUER = "https://clerk.example.test"
SUBJECT = "user_cs12_e2e"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД для end-to-end сценария onboarding."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _principal() -> Principal:
    """Возвращает подтверждённый Principal тестового пользователя."""
    return Principal(subject_id=SUBJECT, issuer=ISSUER)


def _row_counts(db: Session) -> dict[str, int]:
    """Возвращает количество строк во всех provisioning-таблицах."""
    return {
        "app_users": db.query(AppUser).count(),
        "external_identities": db.query(ExternalIdentity).count(),
        "agencies": db.query(Agency).count(),
        "agency_memberships": db.query(AgencyMembership).count(),
    }


def _empty_counts() -> dict[str, int]:
    """Возвращает ожидаемое пустое состояние всех provisioning-таблиц."""
    return {
        "app_users": 0,
        "external_identities": 0,
        "agencies": 0,
        "agency_memberships": 0,
    }


def _api_request(
    db: Session,
    principal: Principal,
    method: str,
    path: str,
) -> object:
    """Выполняет запрос к production app с test-сессией и Principal."""

    def override_get_db() -> Iterator[Session]:
        yield db

    def override_get_current_principal() -> Principal:
        return principal

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_principal] = override_get_current_principal
    client = TestClient(app, raise_server_exceptions=False)
    try:
        return client.request(method, path)
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_principal, None)


def test_onboarding_enables_identity_resolution_and_tenant_authorization(
    db: Session,
) -> None:
    """Onboarding создаёт tenant, который разрешается production-сервисами."""
    principal = _principal()
    assert _row_counts(db) == _empty_counts()

    response = _api_request(db, principal, "POST", "/api/v1/onboarding")

    assert response.status_code == 201
    body = response.json()
    assert body["replayed"] is False
    assert body["role"] == "owner"
    assert _row_counts(db) == {
        "app_users": 1,
        "external_identities": 1,
        "agencies": 1,
        "agency_memberships": 1,
    }

    app_user = IdentityResolutionService(session=db).resolve(principal)
    assert str(app_user.app_user_id) == body["app_user_id"]

    context = TenantAuthorizationService(session=db).authorize(principal)
    assert context.app_user_id == app_user.app_user_id
    assert str(context.agency_id) == body["agency_id"]
    assert context.role == "owner"


def test_protected_signals_api_allows_onboarded_principal(db: Session) -> None:
    """После onboarding protected API проходит полный production tenant flow."""
    principal = _principal()
    onboarding = _api_request(db, principal, "POST", "/api/v1/onboarding")
    assert onboarding.status_code == 201

    response = _api_request(db, principal, "GET", "/api/v1/signals")

    assert response.status_code == 200
    assert response.json() == []


def test_protected_api_does_not_auto_provision(db: Session) -> None:
    """Protected API отклоняет unprovisioned principal без создания записей."""
    principal = _principal()

    response = _api_request(db, principal, "GET", "/api/v1/signals")

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _row_counts(db) == _empty_counts()


def test_unprovisioned_identity_resolution_fails_before_onboarding(
    db: Session,
) -> None:
    """До onboarding identity resolution отклоняет Principal как неизвестного."""
    principal = _principal()

    with pytest.raises(IdentityResolutionNotFoundError):
        IdentityResolutionService(session=db).resolve(principal)

    onboarding = _api_request(db, principal, "POST", "/api/v1/onboarding")
    assert onboarding.status_code == 201

    app_user = IdentityResolutionService(session=db).resolve(principal)
    assert app_user.is_active is True


def test_replay_keeps_tenant_context_stable(db: Session) -> None:
    """Replay onboarding сохраняет tenant и не создаёт дубликаты."""
    principal = _principal()
    first_body = _api_request(db, principal, "POST", "/api/v1/onboarding").json()
    counts_after_first = _row_counts(db)

    second = _api_request(db, principal, "POST", "/api/v1/onboarding")

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["replayed"] is True
    assert second_body["app_user_id"] == first_body["app_user_id"]
    assert second_body["agency_id"] == first_body["agency_id"]
    assert _row_counts(db) == counts_after_first

    context = TenantAuthorizationService(session=db).authorize(principal)
    assert context.role == "owner"
    assert str(context.agency_id) == first_body["agency_id"]
