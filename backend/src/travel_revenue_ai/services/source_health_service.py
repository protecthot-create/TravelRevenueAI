"""Сервис вычисления состояния готовности внешнего источника."""

import enum
from typing import Protocol

from travel_revenue_ai.models.data_source import DataSource, SyncStatusEnum


class SourceHealthStatusEnum(str, enum.Enum):
    """Публичные статусы готовности источника."""

    ok = "OK"
    error = "ERROR"
    disabled = "DISABLED"
    not_configured = "NOT_CONFIGURED"


class SourceHealthService:
    """Определяет состояние источника без создания внешних подключений."""

    def get_status(self, source: DataSource | None) -> SourceHealthStatusEnum:
        """Возвращает статус на основе ORM-конфигурации и последней синхронизации."""
        if source is None:
            return SourceHealthStatusEnum.not_configured
        if not source.enabled:
            return SourceHealthStatusEnum.disabled
        if source.sync_status is SyncStatusEnum.error:
            return SourceHealthStatusEnum.error
        if not source.credentials:
            return SourceHealthStatusEnum.not_configured
        return SourceHealthStatusEnum.ok