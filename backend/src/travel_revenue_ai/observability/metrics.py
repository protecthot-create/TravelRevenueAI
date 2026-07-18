"""In-memory метрики обработки сигналов без внешнего backend-а."""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock

METRIC_NAMES = (
    "signals_received",
    "signals_enriched",
    "signals_scored",
    "signals_filtered",
    "decision_cards_created",
    "morning_briefs_generated",
    "enrichment_duration_ms",
    "pipeline_duration_ms",
    "enrichment_errors",
)


class MetricsService:
    """Хранит потокобезопасные счётчики и накопленные длительности в памяти процесса."""

    def __init__(self) -> None:
        """Инициализирует все поддерживаемые метрики нулевыми значениями."""
        self._lock = Lock()
        self._metrics: dict[str, int] = {metric_name: 0 for metric_name in METRIC_NAMES}

    def increment(self, metric_name: str, value: int = 1) -> None:
        """Увеличивает счётчик на неотрицательное целое значение."""
        if metric_name not in self._metrics:
            raise ValueError(f"Неподдерживаемая метрика: {metric_name}")
        if value < 0:
            raise ValueError("Значение метрики не может быть отрицательным")

        with self._lock:
            self._metrics[metric_name] += value

    def record_duration_ms(self, metric_name: str, duration_ms: int) -> None:
        """Добавляет измеренную длительность в миллисекундах к метрике."""
        if metric_name not in {"enrichment_duration_ms", "pipeline_duration_ms"}:
            raise ValueError(f"Метрика не поддерживает длительность: {metric_name}")
        if duration_ms < 0:
            raise ValueError("Длительность не может быть отрицательной")

        self.increment(metric_name, duration_ms)

    def snapshot(self) -> Mapping[str, int]:
        """Возвращает неизменяемую копию текущих значений метрик."""
        with self._lock:
            return self._metrics.copy()

    def reset(self) -> None:
        """Сбрасывает все метрики экземпляра для изолированного тестового сценария."""
        with self._lock:
            for metric_name in self._metrics:
                self._metrics[metric_name] = 0