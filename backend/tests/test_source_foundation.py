"""Проверки инфраструктуры источников Sprint 6.0."""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from travel_revenue_ai.database import get_db
from travel_revenue_ai.main import app
from travel_revenue_ai.models.data_source import DataSourceTypeEnum, SyncStatusEnum
from travel_revenue_ai.security.secrets import SecretService
from travel_revenue_ai.services.source_health_service import (
    SourceHealthService,
    SourceHealthStatusEnum,
)
from travel_revenue_ai.sources.connection_manager import ConnectionManager
from travel_revenue_ai.sources.default_providers import register_default_providers
from travel_revenue_ai.sources.manager import SourceManager
from travel_revenue_ai.sources.mock_email_provider import MockEmailProvider
from travel_revenue_ai.sources.mock_telegram_provider import MockTelegramProvider
from travel_revenue_ai.sources.provider_registry import ProviderRegistry
from travel_revenue_ai.sources.runtime_factory import DataSourceRuntimeFactory


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


def test_runtime_factory_registers_only_enabled_supported_sources() -> None:
    """Runtime factory создаёт адаптеры лишь для enabled email/telegram источников."""
    factory = DataSourceRuntimeFactory(
        provider_registry=_build_default_provider_registry(),
        secret_service=SecretService(None),
    )
    manager = SourceManager()
    agency_id = "00000000-0000-0000-0000-000000000001"

    registered_count = factory.register_enabled_sources(
        source_manager=manager,
        data_sources=[
            SimpleNamespace(
                enabled=True,
                source_type=DataSourceTypeEnum.email,
                agency_id=agency_id,
                source_id="00000000-0000-0000-0000-000000000011",
                settings={"provider": "mock", "folder": "INBOX"},
                credentials={"username": "sales@example.com"},
            ),
            SimpleNamespace(
                enabled=False,
                source_type=DataSourceTypeEnum.telegram,
                agency_id=agency_id,
                source_id="00000000-0000-0000-0000-000000000012",
                settings={"provider": "mock"},
                credentials={},
            ),
            SimpleNamespace(
                enabled=True,
                source_type="unknown",
                agency_id=agency_id,
                source_id="00000000-0000-0000-0000-000000000013",
                settings={"provider": "mock"},
                credentials={},
            ),
        ],
    )

    assert registered_count == 1
    assert manager.adapter_names == ("email:00000000-0000-0000-0000-000000000011",)


def test_runtime_factory_passes_decrypted_credentials_and_settings_to_provider() -> None:
    """Factory передаёт provider-конфигурацию, не мутируя ORM JSON-поля."""
    received_config: dict[str, object] = {}
    registry = ProviderRegistry()

    def factory_callback(config: dict[str, object]) -> object:
        received_config.update(config)
        return MockEmailProvider()

    registry.register(
        source_type=DataSourceTypeEnum.email.value,
        provider_name="capture",
        factory=factory_callback,
    )
    runtime_factory = DataSourceRuntimeFactory(
        provider_registry=registry,
        secret_service=SecretService(None),
    )
    data_source = SimpleNamespace(
        enabled=True,
        source_type=DataSourceTypeEnum.email,
        agency_id="00000000-0000-0000-0000-000000000001",
        source_id="00000000-0000-0000-0000-000000000011",
        settings={"provider": "capture", "folder": "INBOX"},
        credentials={"password": "secret"},
    )

    adapter = runtime_factory.build_adapter(data_source)

    assert adapter is not None
    assert received_config == {
        "provider": "capture",
        "folder": "INBOX",
        "settings": {"provider": "capture", "folder": "INBOX"},
        "credentials": {"password": "secret"},
    }
    assert data_source.settings == {"provider": "capture", "folder": "INBOX"}
    assert data_source.credentials == {"password": "secret"}


def test_collect_sources_endpoint_returns_safe_runtime_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual endpoint передаёт параметры в composition root и не раскрывает internals."""
    from travel_revenue_ai.api.v1 import sources

    agency_id = "00000000-0000-0000-0000-000000000001"
    captured: dict[str, object] = {}

    class FakeCollectionService:
        def collect_and_generate_morning_brief(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                collected_count=5,
                saved_count=3,
                errors_count=1,
                persisted_briefs={agency_id: object()},
            )

    monkeypatch.setattr(
        sources,
        "build_source_collection_service",
        lambda session: FakeCollectionService(),
    )

    def override_get_db() -> object:
        yield object()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/sources/collect?brief_date=2026-08-01&run_id=cs6-manual-test"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "collected_count": 5,
        "saved_count": 3,
        "errors_count": 1,
        "persisted_brief_agency_ids": [agency_id],
    }
    assert captured == {
        "brief_date": date(2026, 8, 1),
        "trigger_type": "manual",
        "run_id": "cs6-manual-test",
    }


def _build_default_provider_registry() -> ProviderRegistry:
    """Создаёт registry со штатными mock providers для unit-тестов."""
    registry = ProviderRegistry()
    register_default_providers(registry)
    return registry


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