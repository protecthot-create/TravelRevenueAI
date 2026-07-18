"""Проверки Sprint 6.2.2: CRUD, health и безопасные connection tests."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.data_source import (
    DataSource,
    DataSourceTypeEnum,
    SyncStatusEnum,
)
from travel_revenue_ai.schemas.data_source import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
)
from travel_revenue_ai.services.data_source_service import DataSourceService
from travel_revenue_ai.services.source_health_service import (
    SourceHealthService,
    SourceHealthStatusEnum,
)
from travel_revenue_ai.sources.provider_registry import ProviderRegistry


@pytest.fixture
def db() -> Session:
    """Создаёт отдельную in-memory БД для каждого теста."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def agency_id(db: Session) -> uuid.UUID:
    """Сохраняет минимальное агентство для внешнего ключа источника."""
    agency = Agency()
    db.add(agency)
    db.commit()
    db.refresh(agency)
    return agency.agency_id


def test_source_crud_hides_credentials(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """CRUD сохраняет credentials, но публичный ответ их не содержит."""
    service = DataSourceService(db)
    source = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="Рабочая почта",
            source_type=DataSourceTypeEnum.email,
            credentials={"host": "imap.example.test", "password": "secret-value"},
            settings={"folder": "INBOX"},
        )
    )

    assert source.credentials["password"] == "secret-value"
    public_response = DataSourceResponse.model_validate(source).model_dump()
    assert "credentials" not in public_response
    assert "secret-value" not in str(public_response)

    updated = service.update_source(
        source,
        DataSourceUpdate(source_name="Основная почта", enabled=False),
    )
    assert updated.source_name == "Основная почта"
    assert updated.sync_status is SyncStatusEnum.disabled
    assert service.get_source(source.source_id) is not None
    assert len(service.list_sources(agency_id=agency_id)) == 1

    service.delete_source(updated)
    assert service.get_source(source.source_id) is None


def test_health_status_for_not_configured_and_disabled_sources(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """Health различает пустую конфигурацию и намеренно выключенный источник."""
    service = DataSourceService(db)
    health_service = SourceHealthService()

    not_configured = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="RSS",
            source_type=DataSourceTypeEnum.rss,
        )
    )
    disabled = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="CRM",
            source_type=DataSourceTypeEnum.crm,
            enabled=False,
        )
    )

    assert health_service.get_status(not_configured) is SourceHealthStatusEnum.not_configured
    assert health_service.get_status(disabled) is SourceHealthStatusEnum.disabled


def test_telegram_mock_connection_test_succeeds(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """Telegram проверяется через mock provider без реального Telegram API."""
    service = DataSourceService(db)
    source = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="Telegram mock",
            source_type=DataSourceTypeEnum.telegram,
            credentials={"token": "must-not-leak"},
        )
    )

    result = service.test_connection(source)

    assert result.sync_status is SyncStatusEnum.success
    assert result.last_error is None
    assert isinstance(result.last_sync, datetime)


def test_invalid_imap_configuration_is_saved_as_safe_error(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """Невалидная IMAP-конфигурация не раскрывает данные и сохраняет ERROR."""
    service = DataSourceService(db)
    source = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="Некорректный IMAP",
            source_type=DataSourceTypeEnum.email,
            credentials={"password": "hidden-password"},
        )
    )

    result = service.test_connection(source)

    assert result.sync_status is SyncStatusEnum.error
    assert result.last_error == "Конфигурация источника недействительна"
    assert "hidden-password" not in result.last_error
    assert isinstance(result.last_sync, datetime)


def test_connection_failure_is_saved_as_safe_error(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """Ошибка провайдера фиксируется без текста исходного исключения."""
    registry = ProviderRegistry()

    def failing_factory(config: dict[str, object]) -> object:
        del config

        class FailingProvider:
            def fetch_messages(self) -> list[object]:
                raise OSError("socket failure with token=private")

        return FailingProvider()

    registry.register(
        source_type="email",
        provider_name="failing",
        factory=failing_factory,
    )
    service = DataSourceService(db, provider_registry=registry)
    source = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="Падающее подключение",
            source_type=DataSourceTypeEnum.email,
            credentials={"password": "private"},
            settings={"provider": "failing"},
        )
    )

    result = service.test_connection(source)

    assert result.sync_status is SyncStatusEnum.error
    assert result.last_error == "Не удалось проверить подключение источника"
    assert "private" not in result.last_error


def test_disabled_source_is_not_checked(
    db: Session,
    agency_id: uuid.UUID,
) -> None:
    """Выключенный источник не запускает провайдера и остаётся DISABLED."""
    service = DataSourceService(db)
    source = service.create_source(
        DataSourceCreate(
            agency_id=agency_id,
            source_name="Отключённая почта",
            source_type=DataSourceTypeEnum.email,
            enabled=False,
            credentials={"password": "private"},
        )
    )

    result = service.test_connection(source)

    assert result.sync_status is SyncStatusEnum.disabled
    assert result.last_error is None
    assert result.last_sync is None