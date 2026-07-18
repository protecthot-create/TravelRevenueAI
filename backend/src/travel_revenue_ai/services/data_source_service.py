"""Сервис управления конфигурациями источников и проверкой подключений."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_revenue_ai.config import settings
from travel_revenue_ai.models.data_source import (
    DataSource,
    DataSourceTypeEnum,
    SyncStatusEnum,
)
from travel_revenue_ai.schemas.data_source import DataSourceCreate, DataSourceUpdate
from travel_revenue_ai.security.secrets import SecretService
from travel_revenue_ai.sources.default_providers import register_default_providers
from travel_revenue_ai.sources.provider_registry import ProviderRegistry


class DataSourceService:
    """Выполняет CRUD и ручные проверки без участия ingestion pipeline."""

    def __init__(
        self,
        db: Session,
        *,
        provider_registry: ProviderRegistry | None = None,
        secret_service: SecretService | None = None,
    ) -> None:
        """Сохраняет сессию БД и подготавливает стандартный реестр провайдеров."""
        self._db = db
        self._provider_registry = provider_registry or ProviderRegistry()
        self._secret_service = secret_service or SecretService(
            settings.secret_encryption_key,
            require_encryption=settings.is_production,
        )
        if provider_registry is None:
            register_default_providers(self._provider_registry)

    def list_sources(self, *, agency_id: uuid.UUID | None = None) -> list[DataSource]:
        """Возвращает источники с необязательной фильтрацией по агентству."""
        statement = select(DataSource).order_by(DataSource.created_at.desc())
        if agency_id is not None:
            statement = statement.where(DataSource.agency_id == agency_id)
        return list(self._db.scalars(statement).all())

    def get_source(self, source_id: uuid.UUID) -> DataSource | None:
        """Находит источник по идентификатору."""
        return self._db.get(DataSource, source_id)

    def create_source(self, data: DataSourceCreate) -> DataSource:
        """Создаёт конфигурацию источника и сохраняет её."""
        source = DataSource(
            agency_id=data.agency_id,
            source_name=data.source_name,
            source_type=data.source_type,
            enabled=data.enabled,
            credentials=self._secret_service.encrypt(data.credentials),
            settings=dict(data.settings),
            sync_status=(
                SyncStatusEnum.never_synced if data.enabled else SyncStatusEnum.disabled
            ),
        )
        self._db.add(source)
        self._db.commit()
        self._db.refresh(source)
        return source

    def update_source(self, source: DataSource, data: DataSourceUpdate) -> DataSource:
        """Обновляет разрешённые поля конфигурации источника."""
        changes = data.model_dump(exclude_unset=True)
        for field_name, value in changes.items():
            if field_name == "credentials":
                value = self._secret_service.encrypt(value)
            elif field_name == "settings":
                value = dict(value)
            setattr(source, field_name, value)

        if not source.enabled:
            source.sync_status = SyncStatusEnum.disabled
        elif source.sync_status is SyncStatusEnum.disabled:
            source.sync_status = SyncStatusEnum.never_synced
            source.last_error = None

        self._db.commit()
        self._db.refresh(source)
        return source

    def delete_source(self, source: DataSource) -> None:
        """Удаляет конфигурацию источника."""
        self._db.delete(source)
        self._db.commit()

    def test_connection(self, source: DataSource) -> DataSource:
        """Проверяет подключение и сохраняет результат без раскрытия секретов."""
        checked_at = datetime.now(timezone.utc)

        if not source.enabled:
            source.sync_status = SyncStatusEnum.disabled
            source.last_error = None
            self._save(source)
            return source

        try:
            provider_name = self._get_provider_name(source)
            provider = self._provider_registry.create(
                source_type=source.source_type.value,
                provider_name=provider_name,
                config={
                    "credentials": self._secret_service.decrypt(source.credentials),
                    "settings": dict(source.settings),
                },
            )
            self._run_connection_check(provider)
        except (LookupError, ValueError, RuntimeError, OSError) as error:
            source.sync_status = SyncStatusEnum.error
            source.last_error = self._to_safe_error_message(error)
        else:
            source.sync_status = SyncStatusEnum.success
            source.last_error = None

        source.last_sync = checked_at
        self._save(source)
        return source

    @staticmethod
    def _get_provider_name(source: DataSource) -> str:
        """Определяет разрешённый провайдер из settings или безопасного default."""
        configured_name = source.settings.get("provider")
        if isinstance(configured_name, str) and configured_name.strip():
            return configured_name.strip().lower()

        if source.source_type is DataSourceTypeEnum.email:
            return "imap"
        if source.source_type is DataSourceTypeEnum.telegram:
            return "mock"
        return "placeholder"

    @staticmethod
    def _run_connection_check(provider: object) -> None:
        """Выполняет проверку через существующий read-only контракт провайдера."""
        fetch_messages = getattr(provider, "fetch_messages", None)
        if not callable(fetch_messages):
            raise RuntimeError("Провайдер не поддерживает проверку подключения")
        fetch_messages()

    @staticmethod
    def _to_safe_error_message(error: Exception) -> str:
        """Возвращает контролируемую ошибку без конфигурации и credentials."""
        if isinstance(error, LookupError):
            return "Провайдер для этого источника пока не поддерживает проверку"
        if isinstance(error, ValueError):
            return "Конфигурация источника недействительна"
        return "Не удалось проверить подключение источника"

    def _save(self, source: DataSource) -> None:
        """Фиксирует технический результат проверки."""
        self._db.add(source)
        self._db.commit()
        self._db.refresh(source)