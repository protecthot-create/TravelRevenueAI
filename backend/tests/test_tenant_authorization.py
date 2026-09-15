"""Focused-тесты tenant authorization и межагентской изоляции CS11."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

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
from travel_revenue_ai.security.tenant_context import TenantContext
from travel_revenue_ai.services.tenant_authorization_errors import (
    TenantAccessDeniedError,
    TenantSelectionRequiredError,
)
from travel_revenue_ai.services.tenant_authorization_service import (
    TenantAuthorizationService,
)

ISSUER = "https://clerk.example.test"
SUBJECT = "user_cs11"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД для unit-тестов authorization."""
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


def _create_user(db: Session, *, is_active: bool = True) -> AppUser:
    """Создаёт AppUser и связанную Clerk identity."""
    user = AppUser(is_active=is_active)
    db.add(user)
    db.flush()
    db.add(
        ExternalIdentity(
            app_user_id=user.app_user_id,
            external_issuer=ISSUER,
            external_subject=SUBJECT,
        )
    )
    db.flush()
    return user


def _add_membership(
    db: Session,
    *,
    app_user_id: UUID,
    agency_id: UUID,
    status: str = "active",
) -> None:
    """Добавляет membership с указанным статусом."""
    db.add(
        AgencyMembership(
            app_user_id=app_user_id,
            agency_id=agency_id,
            role="member",
            status=status,
        )
    )
    db.flush()


def _list_signals_as_principal(
    db: Session,
    *,
    agency_id: UUID | None = None,
) -> object:
    """Выполняет реальный list-запрос с production tenant dependency."""

    def override_get_db() -> Iterator[Session]:
        yield db

    def override_get_current_principal() -> Principal:
        return _principal()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_principal] = override_get_current_principal
    client = TestClient(app, raise_server_exceptions=False)
    try:
        params = {"agency_id": str(agency_id)} if agency_id is not None else None
        return client.get("/api/v1/signals", params=params)
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_principal, None)


def test_single_active_membership_is_selected_implicitly(db: Session) -> None:
    """Единственный active membership разрешается без явного agency_id."""
    user = _create_user(db)
    agency = Agency()
    db.add(agency)
    db.flush()
    _add_membership(db, app_user_id=user.app_user_id, agency_id=agency.agency_id)

    context = TenantAuthorizationService(session=db).authorize(_principal())

    assert context == TenantContext(
        app_user_id=user.app_user_id,
        agency_id=agency.agency_id,
        role="member",
    )


def test_multiple_active_memberships_require_explicit_selection(db: Session) -> None:
    """Несколько active memberships требуют явного выбора tenant."""
    user = _create_user(db)
    agencies = [Agency(), Agency()]
    db.add_all(agencies)
    db.flush()
    for agency in agencies:
        _add_membership(db, app_user_id=user.app_user_id, agency_id=agency.agency_id)

    with pytest.raises(TenantSelectionRequiredError):
        TenantAuthorizationService(session=db).authorize(_principal())

    context = TenantAuthorizationService(session=db).authorize(
        _principal(), agencies[1].agency_id
    )
    assert context.agency_id == agencies[1].agency_id


def test_list_without_agency_id_maps_multiple_memberships_to_400(db: Session) -> None:
    """List без agency_id требует выбора tenant при нескольких memberships."""
    user = _create_user(db)
    agencies = [Agency(), Agency()]
    db.add_all(agencies)
    db.flush()
    for agency in agencies:
        _add_membership(db, app_user_id=user.app_user_id, agency_id=agency.agency_id)

    response = _list_signals_as_principal(db)

    assert response.status_code == 400
    assert response.json() == {"detail": "tenant_selection_required"}


def test_list_with_foreign_agency_id_remains_403(db: Session) -> None:
    """List с чужим agency_id сохраняет authorization-denied HTTP contract."""
    user = _create_user(db)
    own_agency = Agency()
    foreign_agency = Agency()
    db.add_all([own_agency, foreign_agency])
    db.flush()
    _add_membership(db, app_user_id=user.app_user_id, agency_id=own_agency.agency_id)

    response = _list_signals_as_principal(db, agency_id=foreign_agency.agency_id)

    assert response.status_code == 403
    assert response.json() == {"detail": "tenant_access_denied"}


def test_inactive_membership_is_not_authorized(db: Session) -> None:
    """Suspended и revoked memberships не дают доступа к tenant."""
    user = _create_user(db)
    agency = Agency()
    db.add(agency)
    db.flush()
    _add_membership(
        db,
        app_user_id=user.app_user_id,
        agency_id=agency.agency_id,
        status="suspended",
    )

    with pytest.raises(TenantAccessDeniedError):
        TenantAuthorizationService(session=db).authorize(_principal(), agency.agency_id)


def test_foreign_agency_is_denied(db: Session) -> None:
    """Явный выбор агентства без active membership отклоняется."""
    user = _create_user(db)
    own_agency = Agency()
    foreign_agency = Agency()
    db.add_all([own_agency, foreign_agency])
    db.flush()
    _add_membership(db, app_user_id=user.app_user_id, agency_id=own_agency.agency_id)

    with pytest.raises(TenantAccessDeniedError):
        TenantAuthorizationService(session=db).authorize(_principal(), foreign_agency.agency_id)


def test_authorization_does_not_write_or_commit(db: Session) -> None:
    """Разрешение tenant не меняет состояние транзакции и данных."""
    user = _create_user(db)
    agency = Agency()
    db.add(agency)
    db.flush()
    _add_membership(db, app_user_id=user.app_user_id, agency_id=agency.agency_id)
    db.commit()
    before = db.query(AgencyMembership).count()

    context = TenantAuthorizationService(session=db).authorize(_principal(), agency.agency_id)

    assert context.agency_id == agency.agency_id
    assert db.query(AgencyMembership).count() == before
    assert not db.new
    assert not db.dirty
    assert not db.deleted
