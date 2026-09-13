"""Focused-тесты read-only Identity Resolution CS10."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from travel_revenue_ai.models import AppUser, Base, ExternalIdentity
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.identity_resolution_errors import (
    IdentityResolutionInactiveUserError,
    IdentityResolutionIntegrityError,
    IdentityResolutionNotFoundError,
)
from travel_revenue_ai.services.identity_resolution_service import IdentityResolutionService

ISSUER = "https://clerk.example.test"
OTHER_ISSUER = "https://other-issuer.example.test"
SUBJECT = "user_123"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД для focused identity-тестов."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_identity(
    db: Session,
    *,
    issuer: str = ISSUER,
    subject: str = SUBJECT,
    is_active: bool = True,
) -> AppUser:
    """Создаёт AppUser и ExternalIdentity без membership."""
    app_user = AppUser(is_active=is_active)
    db.add(app_user)
    db.flush()
    db.add(
        ExternalIdentity(
            app_user_id=app_user.app_user_id,
            external_issuer=issuer,
            external_subject=subject,
        )
    )
    db.commit()
    return app_user


def _principal(*, issuer: str = ISSUER, subject: str = SUBJECT) -> Principal:
    """Создаёт минимальный подтверждённый Principal для теста."""
    return Principal(subject_id=subject, issuer=issuer)


def test_repository_lookup_uses_issuer_and_subject_pair(db: Session) -> None:
    """Resolver выбирает identity только по совместной паре issuer и subject."""
    expected_user = _create_identity(db, issuer=ISSUER, subject=SUBJECT)
    _create_identity(db, issuer=OTHER_ISSUER, subject=SUBJECT)

    resolved_user = IdentityResolutionService(session=db).resolve(_principal())

    assert resolved_user.app_user_id == expected_user.app_user_id


def test_lookup_does_not_match_subject_without_matching_issuer(db: Session) -> None:
    """Совпадение subject при другом issuer не разрешает identity."""
    _create_identity(db, issuer=ISSUER, subject=SUBJECT)

    with pytest.raises(IdentityResolutionNotFoundError):
        IdentityResolutionService(session=db).resolve(
            _principal(issuer=OTHER_ISSUER, subject=SUBJECT)
        )


def test_existing_identity_returns_correct_app_user(db: Session) -> None:
    """Существующая ExternalIdentity возвращает связанный AppUser."""
    expected_user = _create_identity(db, subject=SUBJECT)
    _create_identity(db, subject="another_subject")

    resolved_user = IdentityResolutionService(session=db).resolve(
        _principal(subject=SUBJECT)
    )

    assert resolved_user is not None
    assert resolved_user.app_user_id == expected_user.app_user_id
    assert resolved_user.is_active is True


def test_missing_external_identity_raises_not_found_error(db: Session) -> None:
    """Отсутствующая ExternalIdentity явно возвращает domain-level not found."""
    with pytest.raises(IdentityResolutionNotFoundError):
        IdentityResolutionService(session=db).resolve(_principal())


def test_inactive_app_user_raises_inactive_user_error(db: Session) -> None:
    """Неактивный AppUser отклоняется resolver-контрактом без HTTP middleware."""
    _create_identity(db, is_active=False)

    with pytest.raises(IdentityResolutionInactiveUserError):
        IdentityResolutionService(session=db).resolve(_principal())


def test_resolver_does_not_mutate_principal(db: Session) -> None:
    """Разрешение identity не меняет immutable Principal."""
    _create_identity(db)
    principal = _principal()
    original_principal = Principal(
        subject_id=principal.subject_id,
        issuer=principal.issuer,
        token_type=principal.token_type,
    )

    IdentityResolutionService(session=db).resolve(principal)

    assert principal == original_principal
    assert principal.subject_id == SUBJECT
    assert principal.issuer == ISSUER
    assert principal.token_type == "session_token"


def test_resolution_does_not_require_membership_authorization() -> None:
    """Resolver вызывает только identity lookup и lookup AppUser, без membership-проверки."""
    app_user_id = uuid4()
    app_user = AppUser(app_user_id=app_user_id, is_active=True)
    external_identity = ExternalIdentity(
        external_identity_id=uuid4(),
        app_user_id=app_user_id,
        external_issuer=ISSUER,
        external_subject=SUBJECT,
    )
    calls: list[object] = []

    class RepositorySpy:
        """Фиксирует минимальный persistence-контракт resolver без membership API."""

        def find_external_identity(self, principal: Principal) -> ExternalIdentity:
            calls.append(("find_external_identity", principal))
            return external_identity

        def get_app_user_by_id(self, requested_app_user_id: object) -> AppUser:
            calls.append(("get_app_user_by_id", requested_app_user_id))
            return app_user

    resolved_user = IdentityResolutionService(repository=RepositorySpy()).resolve(
        _principal()
    )

    assert resolved_user is app_user
    assert calls == [
        ("find_external_identity", _principal()),
        ("get_app_user_by_id", app_user_id),
    ]


def test_missing_app_user_is_reported_as_integrity_error(db: Session) -> None:
    """Повреждённая ссылка identity на AppUser не маскируется как authorization."""

    db.add(
        ExternalIdentity(
            app_user_id=uuid4(),
            external_issuer=ISSUER,
            external_subject=SUBJECT,
        )
    )
    db.commit()

    with pytest.raises(IdentityResolutionIntegrityError):
        IdentityResolutionService(session=db).resolve(_principal())
