"""Проверки инфраструктуры источников Sprint 6.0."""

from types import SimpleNamespace

import pytest

from travel_revenue_ai.models.data_source import SyncStatusEnum
from travel_revenue_ai.services.source_health_service import (
    SourceHealthService,
    SourceHealthStatusEnum,
)
from travel_revenue_ai.sources.connection_manager import ConnectionManager
from travel_revenue_ai.sources.default_providers import register_default_providers
from travel_revenue_ai.sources.mock_email_provider import MockEmailProvider
from travel_revenue_ai.sources.mock_telegram_provider import MockTelegramProvider
from travel_revenue_ai.sources.provider_registry import ProviderRegistry


def test_connection_manager_creates_connection_from_registered_factory() -> None:
    """ConnectionManager передаёт копии credentials и settings в фабрику."""
    manager = ConnectionManager()
    received_config: dict[str, object] = {}

    def factory(config: dict[str, object]) -> object:
        received_config.update(config)
        return object()

    manager.register(connection_type="imap", factory=factory)

    connection = manager.create(
        connection_type="IMAP",
        credentials={"username": "test@example.com"},
        settings={"folder": "INBOX"},
    )

    assert connection is not None
    assert received_config == {
        "credentials": {"username": "test@example.com"},
        "settings": {"folder": "INBOX"},
    }


def test_connection_manager_rejects_unknown_connection_type() -> None:
    """Незарегистрированный транспорт не создаётся неявно."""
    with pytest.raises(LookupError):
        ConnectionManager().create(connection_type="imap")


def test_default_provider_registry_preserves_mock_providers() -> None:
    """Существующие mock providers доступны через единый Registry."""
    registry = ProviderRegistry()
    register_default_providers(registry)

    email_provider = registry.create(source_type="email", provider_name="mock")
    telegram_provider = registry.create(source_type="telegram", provider_name="mock")

    assert isinstance(email_provider, MockEmailProvider)
    assert isinstance(telegram_provider, MockTelegramProvider)
    assert len(email_provider.fetch_messages()) > 0
    assert len(telegram_provider.fetch_messages()) > 0


@pytest.mark.parametrize(
    ("source", "expected_status"),
    [
        (None, SourceHealthStatusEnum.not_configured),
        (
            SimpleNamespace(
                enabled=False,
                sync_status=SyncStatusEnum.never_synced,
                credentials={},
            ),
            SourceHealthStatusEnum.disabled,
        ),
        (
            SimpleNamespace(
                enabled=True,
                sync_status=SyncStatusEnum.error,
                credentials={"token": "configured"},
            ),
            SourceHealthStatusEnum.error,
        ),
        (
            SimpleNamespace(
                enabled=True,
                sync_status=SyncStatusEnum.never_synced,
                credentials={},
            ),
            SourceHealthStatusEnum.not_configured,
        ),
        (
            SimpleNamespace(
                enabled=True,
                sync_status=SyncStatusEnum.success,
                credentials={"token": "configured"},
            ),
            SourceHealthStatusEnum.ok,
        ),
    ],
)
def test_source_health_service_returns_expected_status(
    source: object | None,
    expected_status: SourceHealthStatusEnum,
) -> None:
    """Health-сервис не открывает подключения и вычисляет статус по данным."""
    assert SourceHealthService().get_status(source) == expected_status