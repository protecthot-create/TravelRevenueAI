"""Оркестрация зарегистрированных адаптеров источников."""

from collections.abc import Iterable
from datetime import datetime, timezone

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum
from travel_revenue_ai.sources.base import BaseSourceAdapter
from travel_revenue_ai.sources.contracts import SourceMetadata, SourceResult


class SourceManager:
    """Реестр и безопасный запуск адаптеров источников.

    Менеджер намеренно не зависит от БД, API и сервисов конвейера. Его
    ответственность заканчивается возвратом ``SourceResult`` для каждого
    зарегистрированного адаптера.
    """

    def __init__(self, adapters: Iterable[BaseSourceAdapter] | None = None) -> None:
        """Создаёт пустой реестр или регистрирует переданные адаптеры."""
        self._adapters: dict[str, BaseSourceAdapter] = {}
        for adapter in adapters or ():
            self.register(adapter)

    @property
    def adapter_names(self) -> tuple[str, ...]:
        """Возвращает имена адаптеров в порядке регистрации."""
        return tuple(self._adapters)

    def register(self, adapter: BaseSourceAdapter) -> None:
        """Регистрирует адаптер с уникальным именем."""
        if adapter.adapter_name in self._adapters:
            raise ValueError(f"Адаптер '{adapter.adapter_name}' уже зарегистрирован")
        self._adapters[adapter.adapter_name] = adapter

    def unregister(self, adapter_name: str) -> BaseSourceAdapter:
        """Удаляет адаптер из реестра и возвращает его экземпляр."""
        try:
            return self._adapters.pop(adapter_name)
        except KeyError as error:
            raise KeyError(f"Адаптер '{adapter_name}' не зарегистрирован") from error

    def collect_all(self) -> list[SourceResult]:
        """Запускает каждый адаптер независимо и возвращает все результаты."""
        return [self.collect(adapter_name) for adapter_name in self.adapter_names]

    def collect(self, adapter_name: str) -> SourceResult:
        """Запускает один адаптер и преобразует ошибку в изолированный результат."""
        try:
            adapter = self._adapters[adapter_name]
        except KeyError as error:
            raise KeyError(f"Адаптер '{adapter_name}' не зарегистрирован") from error

        metadata = SourceMetadata(
            adapter_name=adapter.adapter_name,
            agency_id=adapter.agency_id,
            source_id=adapter.source_id,
            collected_at=datetime.now(timezone.utc),
        )

        try:
            signals = adapter.collect_signals()
            self._validate_signals(adapter, signals)
        except Exception as error:
            return SourceResult(metadata=metadata, error=str(error))

        return SourceResult(metadata=metadata, signals=signals)

    @staticmethod
    def _validate_signals(adapter: BaseSourceAdapter, signals: list[Signal]) -> None:
        """Проверяет, что адаптер вернул сигналы в согласованном формате."""
        for signal in signals:
            if not isinstance(signal, Signal):
                raise TypeError("collect_signals должен возвращать список объектов Signal")
            if signal.agency_id != adapter.agency_id:
                raise ValueError("Сигнал содержит agency_id другого агентства")
            if signal.source_id != adapter.source_id:
                raise ValueError("Сигнал содержит source_id, не совпадающий с адаптером")
            if signal.status != SignalStatusEnum.new:
                raise ValueError("Собранный сигнал должен иметь статус new")
            if not signal.raw_data:
                raise ValueError("Собранный сигнал должен содержать непустой raw_data")