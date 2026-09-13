"""Focused-тесты CS10 identity и agency membership foundation."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from travel_revenue_ai.models import Agency, AgencyMembership, AppUser, Base, ExternalIdentity


@pytest.fixture()
def db() -> Iterator[Session]:
    """Создаёт изолированную SQLite БД с включёнными внешними ключами."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        """Включает SQLite-проверку FK для schema invariant тестов."""
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_user_and_agency(db: Session) -> tuple[AppUser, Agency]:
    """Создаёт независимые fixture-записи для membership-теста."""
    user = AppUser()
    agency = Agency()
    db.add_all([user, agency])
    db.flush()
    return user, agency


def test_app_user_creation_does_not_create_membership_or_owner(db: Session) -> None:
    """Создание app_user не выдаёт agency-доступ и не назначает owner."""
    user = AppUser()
    db.add(user)
    db.commit()

    assert user.app_user_id is not None
    assert user.is_active is True
    assert db.query(AgencyMembership).count() == 0


def test_external_identity_requires_unique_issuer_and_subject(db: Session) -> None:
    """Одна внешняя identity не может быть привязана к двум app_user."""
    first_user, _ = _create_user_and_agency(db)
    second_user = AppUser()
    db.add(second_user)
    db.flush()

    db.add(
        ExternalIdentity(
            app_user_id=first_user.app_user_id,
            external_issuer="https://clerk.example.test",
            external_subject="user_123",
        )
    )
    db.commit()

    db.add(
        ExternalIdentity(
            app_user_id=second_user.app_user_id,
            external_issuer="https://clerk.example.test",
            external_subject="user_123",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_agency_membership_can_be_created_with_composite_primary_key(db: Session) -> None:
    """Membership создаётся по составному ключу agency_id + app_user_id."""
    user, agency = _create_user_and_agency(db)
    membership = AgencyMembership(
        agency_id=agency.agency_id,
        app_user_id=user.app_user_id,
        role="member",
        status="active",
    )
    db.add(membership)
    db.commit()

    primary_key = [column.name for column in AgencyMembership.__table__.primary_key.columns]
    assert primary_key == ["agency_id", "app_user_id"]
    assert db.get(
        AgencyMembership,
        {"agency_id": agency.agency_id, "app_user_id": user.app_user_id},
    ) is not None


def test_agency_membership_composite_key_rejects_duplicate_pair(db: Session) -> None:
    """Вторая membership той же пары agency/user отклоняется БД."""
    user, agency = _create_user_and_agency(db)
    db.add(
        AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=user.app_user_id,
            role="member",
            status="active",
        )
    )
    db.commit()

    db.add(
        AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=user.app_user_id,
            role="owner",
            status="active",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("role", ["member", "owner"])
def test_agency_membership_accepts_cs10_roles(db: Session, role: str) -> None:
    """CS10 принимает только реализованные роли member и owner."""
    user, agency = _create_user_and_agency(db)
    db.add(
        AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=user.app_user_id,
            role=role,
            status="active",
        )
    )
    db.commit()


@pytest.mark.parametrize(
    ("role", "status"),
    [("admin", "active"), ("member", "pending")],
)
def test_agency_membership_rejects_values_outside_cs10_contract(
    db: Session,
    role: str,
    status: str,
) -> None:
    """Database CHECK constraints отклоняют неизвестные значения."""
    user, agency = _create_user_and_agency(db)
    db.add(
        AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=user.app_user_id,
            role=role,
            status=status,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_agency_membership_requires_existing_agency(db: Session) -> None:
    """Membership не может ссылаться на отсутствующее агентство."""
    user = AppUser()
    db.add(user)
    db.flush()
    db.add(
        AgencyMembership(
            agency_id=uuid4(),
            app_user_id=user.app_user_id,
            role="member",
            status="active",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_cs10_metadata_contains_required_constraints_and_indexes() -> None:
    """ORM metadata фиксирует FK, UNIQUE, CHECK и lookup indexes CS10."""
    external_indexes = {
        (index.name, tuple(column.name for column in index.columns))
        for index in ExternalIdentity.__table__.indexes
    }
    membership_indexes = {
        (index.name, tuple(column.name for column in index.columns))
        for index in AgencyMembership.__table__.indexes
    }
    external_uniques = {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in ExternalIdentity.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    membership_checks = {
        constraint.name
        for constraint in AgencyMembership.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    external_foreign_keys = {
        foreign_key.target_fullname for foreign_key in ExternalIdentity.__table__.foreign_keys
    }
    membership_foreign_keys = {
        foreign_key.target_fullname for foreign_key in AgencyMembership.__table__.foreign_keys
    }

    assert external_indexes == {
        ("ix_external_identities_app_user_id", ("app_user_id",)),
    }
    assert membership_indexes == {
        ("ix_agency_memberships_app_user_agency", ("app_user_id", "agency_id")),
    }
    assert external_uniques == {
        (
            "uq_external_identities_issuer_subject",
            ("external_issuer", "external_subject"),
        ),
    }
    assert membership_checks == {
        "ck_agency_memberships_role",
        "ck_agency_memberships_status",
    }
    assert external_foreign_keys == {"app_users.app_user_id"}
    assert membership_foreign_keys == {
        "agencies.agency_id",
        "app_users.app_user_id",
    }


def test_migration_creates_only_cs10_tables() -> None:
    """CS10 migration содержит только три требуемых create_table операции."""
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root
        / "alembic"
        / "versions"
        / "20260722_0003_identity_and_agency_memberships.py"
    )
    tree = ast.parse(migration_path.read_text(encoding="utf-8"))
    created_tables: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "create_table":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            created_tables.append(node.args[0].value)

    assert created_tables == [
        "app_users",
        "external_identities",
        "agency_memberships",
    ]


def test_migration_chain_ends_at_cs10() -> None:
    """Alembic revisions образуют цепочку 0001 → 0002 → 0003."""
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    first = script.get_revision("20260718_0001")
    second = script.get_revision("20260722_0002")
    third = script.get_revision("20260722_0003")

    assert first is not None
    assert second is not None
    assert third is not None
    assert second.down_revision == first.revision
    assert third.down_revision == second.revision
    assert script.get_current_head() == "20260722_0003"



@pytest.mark.parametrize("status", ["active", "suspended", "revoked"])
def test_agency_membership_accepts_cs10_statuses(db: Session, status: str) -> None:
    """CS10 принимает active, suspended и revoked."""
    user, agency = _create_user_and_agency(db)
    db.add(
        AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=user.app_user_id,
            role="member",
            status=status,
        )
    )
    db.commit()
