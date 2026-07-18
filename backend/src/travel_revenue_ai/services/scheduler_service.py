"""Инфраструктура ручного и будущего ежедневного запуска Morning Brief."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from travel_revenue_ai.config import Settings, settings
from travel_revenue_ai.services.source_collection_service import (
    SourceCollectionResult,
    SourceCollectionService,
)


@dataclass(frozen=True, slots=True)
class DailySchedule:
    """Параметры ежедневного запуска, совместимые с cron-триггером APScheduler."""

    hour: int
    minute: int
    timezone: str


class JobScheduler(Protocol):
    """Минимальный контракт планировщика для регистрации ежедневной задачи."""

    def add_job(
        self,
        func: Any,
        *,
        trigger: str,
        hour: int,
        minute: int,
        timezone: str,
        id: str,
        replace_existing: bool,
    ) -> Any:
        """Регистрирует задачу в планировщике."""


class SchedulerService:
    """Запускает сбор источников вручную и готовит ежедневное расписание.

    Сервис не создаёт и не запускает фоновый планировщик. В production-контуре
    ему можно передать экземпляр APScheduler и вызвать ``register_daily_job``.
    """

    def __init__(
        self,
        *,
        source_collection_service: SourceCollectionService,
        app_settings: Settings = settings,
    ) -> None:
        """Инициализирует сервис с настройками времени ежедневного запуска."""
        self.source_collection_service = source_collection_service
        self.daily_schedule = self._parse_daily_schedule(
            run_time=app_settings.morning_brief_run_time,
            timezone=app_settings.morning_brief_timezone,
        )

    def run_once(self) -> SourceCollectionResult:
        """Немедленно запускает сбор источников и генерацию Morning Brief."""
        return self.source_collection_service.collect_and_generate_morning_brief()

    def register_daily_job(self, scheduler: JobScheduler) -> Any:
        """Регистрирует ежедневный запуск в переданном scheduler без его старта."""
        return scheduler.add_job(
            self.run_once,
            trigger="cron",
            hour=self.daily_schedule.hour,
            minute=self.daily_schedule.minute,
            timezone=self.daily_schedule.timezone,
            id="morning_brief_collection",
            replace_existing=True,
        )

    @staticmethod
    def _parse_daily_schedule(*, run_time: str, timezone: str) -> DailySchedule:
        """Преобразует настройку ``HH:MM`` в параметры cron-задачи."""
        try:
            hour_text, minute_text = run_time.split(":", maxsplit=1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (AttributeError, ValueError) as error:
            raise ValueError(
                "Время запуска Morning Brief должно иметь формат HH:MM."
            ) from error

        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Время запуска Morning Brief выходит за допустимый диапазон.")

        if not timezone.strip():
            raise ValueError("Часовой пояс Morning Brief не может быть пустым.")

        return DailySchedule(hour=hour, minute=minute, timezone=timezone)