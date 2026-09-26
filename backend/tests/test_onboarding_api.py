"""Focused HTTP-тесты onboarding API boundary CS12."""

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
from travel_revenue_ai.services.tenant_provisioning_errors import (
    TenantProvisioningInactiveUserError,
    TenantProvisioningPersistenceError,
    TenantProvisioningStateError,
)

ISSUER = "https://clerk.example.test"
SUBJECT = "user_cs12_onboarding"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД для HTTP-тестов onboarding."""
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


def _post_onboarding(
    db: Session,
    *,
    principal: Principal | None,
    authorization: str | None = None,
) -> object:
    """Выполняет POST /api/v1/onboarding с production auth-механизмом."""

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if principal is not None:

        def override_get_current_principal() -> Principal:
            return principal

        app.dependency_overrides[get_current_principal] = override_get_current_principal
    client = TestClient(app, raise_server_exceptions=False)
    try:
        headers = {"Authorization": authorization} if authorization is not None else None
        return client.post("/api/v1/onboarding", headers=headers)
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_principal, None)


class _FailingProvisioningService:
    """Подменяет provisioning service для проверки HTTP error mapping."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def provision(self, principal: Principal) -> object:
        del principal
        raise self._error


def _patch_failing_service(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    """Подменяет composition-фабрику onboarding на failing service."""
    monkeypatch.setattr(
        "travel_revenue_ai.api.v1.onboarding.build_tenant_provisioning_service",
        lambda db: _FailingProvisioningService(error),
    )


def test_first_onboarding_returns_201_with_owner_tenant(db: Session) -> None:
    """Первый onboarding создаёт полный tenant aggregate и возвращает 201."""
    response = _post_onboarding(db, principal=_principal())

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

    identity = db.query(ExternalIdentity).one()
    assert identity.external_issuer == ISSUER
    assert identity.external_subject == SUBJECT
    assert str(identity.app_user_id) == body["app_user_id"]

    membership = db.query(AgencyMembership).one()
    assert str(membership.agency_id) == body["agency_id"]


def test_repeated_onboarding_returns_200_replay(db: Session) -> None:
    """Повторный onboarding того же Principal возвращает replay без новых записей."""
    first_body = _post_onboarding(db, principal=_principal()).json()
    counts_after_first = _row_counts(db)

    second = _post_onboarding(db, principal=_principal())

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["replayed"] is True
    assert second_body["app_user_id"] == first_body["app_user_id"]
    assert second_body["agency_id"] == first_body["agency_id"]
    assert second_body["role"] == "owner"
    assert _row_counts(db) == counts_after_first


def test_missing_authorization_returns_401_without_rows(db: Session) -> None:
    """POST без Bearer получает uniform 401 и не создаёт provisioning rows."""
    response = _post_onboarding(db, principal=None)

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _row_counts(db) == _empty_counts()


def test_invalid_bearer_returns_401_without_rows(db: Session) -> None:
    """Невалидный Bearer получает существующий CS9 401 без создания записей."""
    response = _post_onboarding(db, principal=None, authorization="Bearer")

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _row_counts(db) == _empty_counts()


def test_inactive_user_error_maps_to_403(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inactive user error возвращает 403 со стабильным detail code."""
    _patch_failing_service(monkeypatch, TenantProvisioningInactiveUserError("внутренний"))

    response = _post_onboarding(db, principal=_principal())

    assert response.status_code == 403
    assert response.json() == {"detail": "tenant_provisioning_inactive_user"}


def test_state_conflict_error_maps_to_409(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State conflict возвращает 409 со стабильным detail code."""
    _patch_failing_service(monkeypatch, TenantProvisioningStateError("внутренний"))

    response = _post_onboarding(db, principal=_principal())

    assert response.status_code == 409
    assert response.json() == {"detail": "tenant_provisioning_state_conflict"}


def test_persistence_failure_maps_to_500_without_leak(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence failure возвращает 500 с safe detail без внутренних деталей."""
    _patch_failing_service(
        monkeypatch,
        TenantProvisioningPersistenceError("секретный SQL текст"),
    )

    response = _post_onboarding(db, principal=_principal())

    assert response.status_code == 500
    assert response.json() == {"detail": "tenant_provisioning_failed"}
    assert "секретный SQL текст" not in response.text
