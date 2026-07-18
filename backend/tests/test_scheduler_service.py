"""Unit-тесты SchedulerService без фоновых задач и ожидания времени."""

from __future__ import annotations

import pytest

from travel_revenue_ai.config import Settings
from travel_revenue_ai.services.scheduler_service import SchedulerService


class FakeSourceCollectionService:
    """Фиксирует ручные запуски и возвращает заранее заданный результат."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.call_count = 0

    def collect_and_generate_morning_brief(self) -> object:
        """Имитирует полный запуск сбора источников и формирования брифа."""
        self.call_count += 1
        return self.result


class FakeJobScheduler:
    """Сохраняет параметры зарегистрированной задачи без запуска по времени."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def add_job(
        self,
        func: object,
        *,
        trigger: str,
        hour: int,
        minute: int,
        timezone: str,
        id: str,
        replace_existing: bool,
    ) -> str:
        """Фиксирует параметры регистрации задачи."""
        self.calls.append(
            {
                "func": func,
                "trigger": trigger,
                "hour": hour,
                "minute": minute,
                "timezone": timezone,
                "id": id,
                "replace_existing": replace_existing,
            }
        )
        return "registered-job"


def make_settings(*, run_time: str = "08:00", timezone: str = "Europe/Moscow") -> Settings:
    """Создаёт настройки, изолированные от переменных окружения."""
    return Settings(
        _env_file=None,
        morning_brief_run_time=run_time,
        morning_brief_timezone=timezone,
    )


def test_run_once_delegates_to_source_collection_service() -> None:
    """Ручной запуск вызывает сбор источников ровно один раз и возвращает его результат."""
    expected_result = object()
    source_collection_service = FakeSourceCollectionService(expected_result)
    service = SchedulerService(
        source_collection_service=source_collection_service,  # type: ignore[arg-type]
        app_settings=make_settings(),
    )

    result = service.run_once()

    assert result is expected_result
    assert source_collection_service.call_count == 1


def test_register_daily_job_uses_configured_cron_schedule_without_running_task() -> None:
    """Регистрация передаёт cron-параметры scheduler-у, но не выполняет задачу."""
    source_collection_service = FakeSourceCollectionService(object())
    service = SchedulerService(
        source_collection_service=source_collection_service,  # type: ignore[arg-type]
        app_settings=make_settings(run_time="06:45", timezone="Asia/Yekaterinburg"),
    )
    scheduler = FakeJobScheduler()

    job = service.register_daily_job(scheduler)

    assert job == "registered-job"
    assert source_collection_service.call_count == 0
    assert len(scheduler.calls) == 1
    assert scheduler.calls[0] == {
        "func": service.run_once,
        "trigger": "cron",
        "hour": 6,
        "minute": 45,
        "timezone": "Asia/Yekaterinburg",
        "id": "morning_brief_collection",
        "replace_existing": True,
    }


@pytest.mark.parametrize("run_time", ["invalid", "24:00", "08:60", "8", "08:00:30"])
def test_rejects_invalid_daily_run_time(run_time: str) -> None:
    """Некорректное время конфигурации отклоняется до регистрации задачи."""
    with pytest.raises(ValueError, match="Время запуска Morning Brief"):
        SchedulerService(
            source_collection_service=FakeSourceCollectionService(object()),  # type: ignore[arg-type]
            app_settings=make_settings(run_time=run_time),
        )


def test_rejects_empty_timezone() -> None:
    """Пустой timezone не допускается в конфигурации ежедневной задачи."""
    with pytest.raises(ValueError, match="Часовой пояс Morning Brief"):
        SchedulerService(
            source_collection_service=FakeSourceCollectionService(object()),  # type: ignore[arg-type]
            app_settings=make_settings(timezone="   "),
        )