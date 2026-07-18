"""Счётчики observability для email ingestion."""

from __future__ import annotations

from threading import Lock
from typing import Final

EMAIL_METRIC_NAMES: Final = (
    "emails_received",
    "emails_processed",
    "emails_skipped",
    "emails_failed",
    "signals_created",
)


class EmailIngestionMetrics:
    """Хранит потокобезопасные счётчики email ingestion.

    Сервис не содержит логики классификации, фильтрации или Pipeline и может быть
    передан в адаптер извне для интеграции с будущим telemetry backend.
    """

    def __init__(self) -> None:
        """Инициализирует все обязательные счётчики нулевыми значениями."""
        self._counters = {metric_name: 0 for metric_name in EMAIL_METRIC_NAMES}
        self._lock = Lock()

    def increment(self, metric_name: str) -> None:
        """Увеличивает один обязательный счётчик."""
        if metric_name not in self._counters:
            raise ValueError(f"Неизвестная email-метрика: {metric_name}")

        with self._lock:
            self._counters[metric_name] += 1

    def snapshot(self) -> dict[str, int]:
        """Возвращает неизменяемый для вызывающего кода снимок счётчиков."""
        with self._lock:
            return dict(self._counters)