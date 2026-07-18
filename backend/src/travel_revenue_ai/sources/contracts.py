"""Контракты результатов сбора данных из внешних источников."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from travel_revenue_ai.models.signal import Signal


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Метаданные одного запуска адаптера источника.

    Конфигурация подключения намеренно не включается в метаданные, чтобы
    исключить случайное попадание секретов в логи и результаты выполнения.
    """

    adapter_name: str
    agency_id: UUID
    source_id: UUID | None
    collected_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceResult:
    """Результат одного запуска адаптера.

    Адаптеры возвращают только сырые ORM-сигналы со статусом ``new``.
    Сохранение, нормализация, scoring и filtering находятся за границей
    source-layer и не запускаются этим контрактом.
    """

    metadata: SourceMetadata
    signals: list[Signal] = field(default_factory=list)
    error: str | None = None

    @property
    def is_successful(self) -> bool:
        """Показывает, завершился ли сбор без ошибки адаптера."""
        return self.error is None