"""Focused-тесты атомарного tenant provisioning core CS12."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from travel_revenue_ai.models import (
    Agency,
    AgencyMembership,
    AppUser,
    Base,
    ExternalIdentity,
)
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.tenant_provisioning_errors import (
    TenantProvisioningInactiveUserError,
    TenantProvisioningPersistenceError,
    TenantProvisioningStateError,
)
from travel_revenue_ai.services.tenant_provisioning_service import (
    TenantProvisioningService,
)

ISSUER = "https://clerk.example.test"
SUBJECT = "user_cs12_provisioning"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД для unit-тестов provisioning."""
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


def _service(db: Session) -> TenantProvisioningService:
    """Собирает provisioning service над тестовой сессией."""
    return TenantProvisioningService(session=db)


def _row_counts(db: Session) -> dict[str, int]:
    """Возвращает количество строк во всех четырёх provisioning-таблицах."""
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


def test_first_provisioning_creates_full_owner_tenant(db: Session) -> None:
    """Первичный provisioning атомарно создаёт все четыре записи."""
    service = _service(db)

    result = service.provision(_principal())

    assert result.replayed is False
    assert result.role == "owner"
    assert _row_counts(db) == {
        "app_users": 1,
        "external_identities": 1,
        "agencies": 1,
        "agency_memberships": 1,
    }

    identity = db.query(ExternalIdentity).one()
    assert identity.external_issuer == ISSUER
    assert identity.external_subject == SUBJECT
    assert identity.app_user_id == result.app_user_id

    membership = db.query(AgencyMembership).one()
    assert membership.role == "owner"
    assert membership.status == "active"
    assert membership.app_user_id == result.app_user_id
    assert membership.agency_id == result.agency_id

    user = db.get(AppUser, result.app_user_id)
    assert user is not None
    assert user.is_active is True


def test_repeated_provisioning_replays_existing_tenant(db: Session) -> None:
    """Повторный вызов того же Principal возвращает существующий tenant."""
    service = _service(db)
    first = service.provision(_principal())
    counts_after_first = _row_counts(db)

    second = service.provision(_principal())

    assert second.replayed is True
    assert second.app_user_id == first.app_user_id
    assert second.agency_id == first.agency_id
    assert second.role == first.role
    assert _row_counts(db) == counts_after_first


def test_failed_late_write_rolls_back_entire_chain(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ошибка поздней записи откатывает всю цепочку без orphan записей."""
    service = _service(db)

    def broken_add_membership(membership: AgencyMembership) -> None:
        del membership
        raise RuntimeError("simulated late write failure")

    monkeypatch.setattr(service.repository, "add_membership", broken_add_membership)

    with pytest.raises(TenantProvisioningPersistenceError) as exc_info:
        service.provision(_principal())

    assert exc_info.value.__cause__ is not None
    assert _row_counts(db) == _empty_counts()


def test_integrity_race_resolves_to_winner_tenant(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IntegrityError от unique constraint разрешается replay состояния победителя."""
    service = _service(db)
    winner = service.provision(_principal())
    counts_after_winner = _row_counts(db)

    real_find = service.identity_repository.find_external_identity
    calls = {"count": 0}

    def miss_on_first_check(principal: Principal) -> ExternalIdentity | None:
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return real_find(principal)

    monkeypatch.setattr(
        service.identity_repository,
        "find_external_identity",
        miss_on_first_check,
    )

    raced = service.provision(_principal())

    assert raced.replayed is True
    assert raced.app_user_id == winner.app_user_id
    assert raced.agency_id == winner.agency_id
    assert _row_counts(db) == counts_after_winner


def test_identity_without_membership_raises_state_error(db: Session) -> None:
    """Identity без active membership не чинится автоматически."""
    user = AppUser()
    db.add(user)
    db.flush()
    db.add(
        ExternalIdentity(
            app_user_id=user.app_user_id,
            external_issuer=ISSUER,
            external_subject=SUBJECT,
        )
    )
    db.commit()
    counts_before = _row_counts(db)

    service = _service(db)

    with pytest.raises(TenantProvisioningStateError):
        service.provision(_principal())

    assert _row_counts(db) == counts_before


def test_replay_of_inactive_user_raises_typed_error(db: Session) -> None:
    """Неактивный AppUser не получает tenant replay."""
    user = AppUser(is_active=False)
    db.add(user)
    db.flush()
    db.add(
        ExternalIdentity(
            app_user_id=user.app_user_id,
            external_issuer=ISSUER,
            external_subject=SUBJECT,
        )
    )
    db.commit()
    counts_before = _row_counts(db)

    service = _service(db)

    with pytest.raises(TenantProvisioningInactiveUserError):
        service.provision(_principal())

    assert _row_counts(db) == counts_before
