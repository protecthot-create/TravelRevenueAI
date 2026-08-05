"""Сборка runtime-адаптеров из включённых ORM DataSource."""

from __future__ import annotations

from typing import Any, Iterable

from travel_revenue_ai.models.data_source import DataSource, DataSourceTypeEnum
from travel_revenue_ai.security.secrets import SecretService
from travel_revenue_ai.sources.email import EmailSourceAdapter
from travel_revenue_ai.sources.manager import SourceManager
from travel_revenue_ai.sources.provider_registry import ProviderRegistry
from travel_revenue_ai.sources.telegram import TelegramSourceAdapter


class DataSourceRuntimeFactory:
    """Создаёт и регистрирует адаптеры только для включённых источников.

    Фабрика не изменяет конфигурацию источников и не управляет их health state:
    она лишь преобразует уже сохранённый ``DataSource`` в runtime-зависимости.
    """

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry,
        secret_service: SecretService,
    ) -> None:
        self._provider_registry = provider_registry
        self._secret_service = secret_service

    def register_enabled_sources(
        self,
        *,
        source_manager: SourceManager,
        data_sources: Iterable[DataSource],
    ) -> int:
        """Создаёт и регистрирует адаптеры для поддерживаемых enabled-источников."""
        registered_count = 0
        for data_source in data_sources:
            if not data_source.enabled:
                continue

            adapter = self.build_adapter(data_source)
            if adapter is None:
                continue

            source_manager.register(adapter)
            registered_count += 1

        return registered_count

    def build_adapter(
        self,
        data_source: DataSource,
    ) -> EmailSourceAdapter | TelegramSourceAdapter | None:
        """Создаёт поддерживаемый source adapter или пропускает неизвестный тип."""
        source_type = self._source_type_value(data_source)
        if source_type not in {
            DataSourceTypeEnum.email.value,
            DataSourceTypeEnum.telegram.value,
        }:
            return None

        config = self._build_provider_config(data_source)
        provider_name = self._get_provider_name(config)
        provider = self._provider_registry.create(
            source_type=source_type,
            provider_name=provider_name,
            config=config,
        )

        if source_type == DataSourceTypeEnum.email.value:
            return EmailSourceAdapter(
                agency_id=data_source.agency_id,
                source_id=data_source.source_id,
                provider=provider,
                config=config,
                adapter_name=f"email:{data_source.source_id}",
            )

        return TelegramSourceAdapter(
            agency_id=data_source.agency_id,
            source_id=data_source.source_id,
            provider=provider,
            config=config,
            adapter_name=f"telegram:{data_source.source_id}",
        )

    def _build_provider_config(self, data_source: DataSource) -> dict[str, Any]:
        """Собирает provider config, не мутируя ORM JSON-поля."""
        settings = dict(data_source.settings or {})
        credentials = self._secret_service.decrypt(data_source.credentials or {})

        config: dict[str, Any] = {
            **settings,
            "settings": settings,
            "credentials": credentials,
        }
        return config

    @staticmethod
    def _get_provider_name(config: dict[str, Any]) -> str:
        """Возвращает имя провайдера с безопасным mock-значением по умолчанию."""
        provider_name = config.get("provider", "mock")
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("Поле provider источника должно быть непустой строкой")
        return provider_name.strip()

    @staticmethod
    def _source_type_value(data_source: DataSource) -> str:
        """Нормализует Enum или строковое значение для совместимости с ORM."""
        source_type = data_source.source_type
        return source_type.value if isinstance(source_type, DataSourceTypeEnum) else str(source_type)