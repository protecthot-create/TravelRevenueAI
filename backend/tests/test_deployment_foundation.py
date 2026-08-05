"""Проверки deployment foundation без изменения прикладной логики."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from travel_revenue_ai.config import Settings
from travel_revenue_ai.health import is_ready, readiness_checks


def test_production_rejects_sqlite_database() -> None:
    """Production-конфигурация не допускает SQLite."""
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(
            environment="production",
            secret_encryption_key="test-key",
            cors_origins=["https://travel.example.test"],
            database_url="sqlite:///./travel_revenue_ai.db",
        )


def test_production_requires_encryption_key() -> None:
    """Production-конфигурация требует ключ шифрования credentials."""
    with pytest.raises(ValidationError, match="SECRET_ENCRYPTION_KEY"):
        Settings(
            environment="production",
            cors_origins=["https://travel.example.test"],
            database_url="postgresql+psycopg://user:password@postgres/test",
        )


def test_production_rejects_wildcard_cors() -> None:
    """Production-конфигурация запрещает wildcard для CORS."""
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            secret_encryption_key="test-key",
            cors_origins=["*"],
            database_url="postgresql+psycopg://user:password@postgres/test",
        )


def test_readiness_includes_all_required_infrastructure_checks(monkeypatch) -> None:
    """Readiness возвращает статусы всех обязательных инфраструктурных компонентов."""
    expected_names = {
        "database",
        "migrations",
        "source_manager",
        "scheduler",
        "metrics",
        "feature_flags",
    }

    monkeypatch.setattr(
        "travel_revenue_ai.health.check_database",
        lambda: {"status": "ok", "detail": "ok"},
    )
    monkeypatch.setattr(
        "travel_revenue_ai.health.check_migrations",
        lambda: {"status": "ok", "detail": "ok"},
    )
    monkeypatch.setattr(
        "travel_revenue_ai.health.check_source_manager",
        lambda: {"status": "ok", "detail": "ok"},
    )
    monkeypatch.setattr(
        "travel_revenue_ai.health.check_scheduler",
        lambda: {"status": "ok", "detail": "ok"},
    )
    monkeypatch.setattr(
        "travel_revenue_ai.health.check_metrics",
        lambda _: {"status": "ok", "detail": "ok"},
    )
    monkeypatch.setattr(
        "travel_revenue_ai.health.check_feature_flags",
        lambda: {"status": "ok", "detail": "ok"},
    )

    checks = readiness_checks(lambda: "")

    assert set(checks) == expected_names
    assert is_ready(checks) is True


def test_readiness_is_false_when_migration_is_outdated() -> None:
    """Одна неактуальная миграция делает приложение неготовым к трафику."""
    checks = {
        "database": {"status": "ok", "detail": "ok"},
        "migrations": {"status": "error", "detail": "Миграции не применены."},
    }

    assert is_ready(checks) is False