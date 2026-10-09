"""Runtime-тесты планового запуска Morning Brief без фоновых задач и БД."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session

import travel_revenue_ai.main as main_module
from travel_revenue_ai.composition import ScheduledCollectionJob, build_scheduler_service
from travel_revenue_ai.config import Settings
from travel_revenue_ai.config import settings as app_settings
from travel_revenue_ai.services.scheduler_service import SchedulerService
from travel_revenue_ai.services.source_collection_service import (
    SourceCollectionResult,
    SourceCollectionService,
)


def make_settings(**overrides: Any) -> Settings:
    """Создаёт настройки, изолированные от переменных окружения."""
    values: dict[str, Any] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)


@dataclass
class FakeSession:
    """Фиксирует жизненный цикл сессии без обращения к базе данных."""

    closed: bool = False
    commit_calls: int = 0
    rollback_calls: int = 0

    def close(self) -> None:
        self.closed = True

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


@dataclass
class FakeSourceCollectionService:
    """Подменяет сбор источников для проверки делегирования и изоляции ошибок."""

    result: SourceCollectionResult | None
    error: Exception | None = None
    call_count: int = 0

    def collect_and_generate_morning_brief(self, **_: Any) -> SourceCollectionResult:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def make_result() -> SourceCollectionResult:
    """Собирает результат сбора с фиктивным Morning Brief."""
    return SourceCollectionResult(
        collected_count=2,
        saved_count=1,
        errors_count=0,
        morning_brief=SimpleNamespace(),  # type: ignore[arg-type]
        persisted_briefs={},
    )


# === Settings tests ===


def test_scheduler_enabled_defaults_to_false() -> None:
    """Без явного флага планировщик не должен запускаться самопроизвольно."""
    assert make_settings().scheduler_enabled is False


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("false", False),
        ("False", False),
        ("0", False),
    ],
)
def test_scheduler_enabled_reads_environment(
    raw_value: str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env-переменная SCHEDULER_ENABLED парсится стандартным pydantic-механизмом."""
    monkeypatch.setenv("SCHEDULER_ENABLED", raw_value)
    assert Settings(_env_file=None).scheduler_enabled is expected


# === Runtime job factory tests ===


def test_scheduled_job_builds_fresh_session_per_invocation() -> None:
    """Каждый плановый прогон получает собственную сессию и закрывает её."""
    session_one, session_two = FakeSession(), FakeSession()
    sessions = iter([session_one, session_two])
    created: list[Session] = []

    def fake_factory() -> Session:
        session = next(sessions)
        created.append(session)
        return session

    collection_services = iter(
        [
            FakeSourceCollectionService(make_result()),
            FakeSourceCollectionService(make_result()),
        ]
    )
    builder_sessions: list[Session] = []

    def fake_builder(session: Session, app_settings: Settings) -> SourceCollectionService:
        builder_sessions.append(session)
        assert app_settings is not None
        return next(collection_services)  # type: ignore[return-value]

    job = ScheduledCollectionJob(
        app_settings=make_settings(),
        session_factory=fake_factory,
        collection_builder=fake_builder,
    )

    job.collect_and_generate_morning_brief()
    job.collect_and_generate_morning_brief()

    assert created == [session_one, session_two]
    assert builder_sessions == [session_one, session_two]
    assert session_one is not session_two
    assert session_one.closed and session_two.closed


def test_scheduled_job_closes_session_without_own_transaction_control() -> None:
    """Обёртка закрывает сессию и не выполняет собственные commit/rollback."""
    session = FakeSession()
    fake_service = FakeSourceCollectionService(make_result())
    job = ScheduledCollectionJob(
        app_settings=make_settings(),
        session_factory=lambda: session,
        collection_builder=lambda _session, _settings: fake_service,  # type: ignore[arg-type,return-value]
    )

    result = job.collect_and_generate_morning_brief()

    assert result is fake_service.result
    assert fake_service.call_count == 1
    assert session.closed is True
    assert session.commit_calls == 0
    assert session.rollback_calls == 0


def test_scheduled_job_closes_session_and_reraises_on_failure() -> None:
    """Ошибка сбора пробрасывается дальше, сессия всё равно закрывается."""
    session = FakeSession()
    fake_service = FakeSourceCollectionService(
        result=None,
        error=RuntimeError("pipeline failure"),
    )
    job = ScheduledCollectionJob(
        app_settings=make_settings(),
        session_factory=lambda: session,
        collection_builder=lambda _session, _settings: fake_service,  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(RuntimeError, match="pipeline failure"):
        job.collect_and_generate_morning_brief()

    assert session.closed is True
    assert session.commit_calls == 0
    assert session.rollback_calls == 0


def test_scheduled_job_logs_start_completion_and_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Журнал фиксирует старт, итог с существующими полями и класс ошибки."""
    success_session = FakeSession()
    success_service = FakeSourceCollectionService(make_result())
    job = ScheduledCollectionJob(
        app_settings=make_settings(),
        session_factory=lambda: success_session,
        collection_builder=lambda _session, _settings: success_service,  # type: ignore[arg-type,return-value]
    )

    with caplog.at_level(logging.INFO, logger="travel_revenue_ai.composition"):
        job.collect_and_generate_morning_brief()

    success_messages = [record.getMessage() for record in caplog.records]
    assert any("начат" in message for message in success_messages)
    completion = next(message for message in success_messages if "завершён" in message)
    assert "collected=2" in completion
    assert "saved=1" in completion
    assert "errors=0" in completion
    assert "persisted_agencies=0" in completion

    caplog.clear()
    failure_session = FakeSession()
    failure_error = RuntimeError("SUPER_SECRET_SHOULD_NOT_APPEAR")
    failure_service = FakeSourceCollectionService(
        result=None,
        error=failure_error,
    )
    failing_job = ScheduledCollectionJob(
        app_settings=make_settings(),
        session_factory=lambda: failure_session,
        collection_builder=lambda _session, _settings: failure_service,  # type: ignore[arg-type,return-value]
    )

    with (
        caplog.at_level(logging.ERROR, logger="travel_revenue_ai.composition"),
        pytest.raises(RuntimeError) as exc_info,
    ):
        failing_job.collect_and_generate_morning_brief()

    assert exc_info.value is failure_error
    assert failure_session.closed is True
    assert any("завершился ошибкой" in record.getMessage() for record in caplog.records)
    assert any(getattr(record, "error_type", None) == "RuntimeError" for record in caplog.records)
    assert "SUPER_SECRET_SHOULD_NOT_APPEAR" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert all(record.exc_text is None for record in caplog.records)


def test_build_scheduler_service_reuses_existing_scheduler_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Фабрика возвращает существующий SchedulerService с per-run сессией."""
    session = FakeSession()
    fake_service = FakeSourceCollectionService(make_result())
    captured: dict[str, Session] = {}

    def fake_builder(session_arg: Session, app_settings: Settings) -> SourceCollectionService:
        captured["session"] = session_arg
        return fake_service  # type: ignore[return-value]

    monkeypatch.setattr(
        "travel_revenue_ai.composition.build_source_collection_service",
        fake_builder,
    )

    scheduler_service = build_scheduler_service(
        app_settings=make_settings(),
        session_factory=lambda: session,
    )

    assert isinstance(scheduler_service, SchedulerService)
    assert isinstance(scheduler_service.source_collection_service, ScheduledCollectionJob)
    assert scheduler_service.daily_schedule.hour == 8
    assert scheduler_service.daily_schedule.minute == 0

    result = scheduler_service.run_once()

    assert result is fake_service.result
    assert fake_service.call_count == 1
    assert captured["session"] is session
    assert session.closed is True


# === Lifespan wiring tests ===


@dataclass
class FakeAsyncIOScheduler:
    """Подменяет APScheduler для проверки wiring без фоновых задач."""

    start_calls: int = 0
    shutdown_calls: int = 0
    registered_jobs: list[dict[str, Any]] = field(default_factory=list)
    start_error: Exception | None = None

    @property
    def running(self) -> bool:
        """Имитирует состояние планировщика APScheduler 3.x."""
        return self.start_calls > 0 and self.shutdown_calls == 0

    def add_job(self, func: Any, **kwargs: Any) -> str:
        self.registered_jobs.append({"func": func, **kwargs})
        return "registered-job"

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def shutdown(self, *, wait: bool = True) -> None:
        self.shutdown_calls += 1
        assert wait is False


@dataclass
class FakeSchedulerService:
    """Фиксирует регистрацию ежедневной задачи без реального сбора."""

    register_calls: int = 0
    registered_scheduler: FakeAsyncIOScheduler | None = None

    @property
    def daily_schedule(self) -> SimpleNamespace:
        return SimpleNamespace(hour=8, minute=0, timezone="Europe/Moscow")

    def register_daily_job(self, scheduler: FakeAsyncIOScheduler) -> str:
        self.register_calls += 1
        self.registered_scheduler = scheduler
        return "registered-job"


def patch_startup_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Убирает реальные readiness-проверки БД из lifespan."""
    monkeypatch.setattr(main_module, "readiness_checks", lambda *_args: {})
    monkeypatch.setattr(main_module, "is_ready", lambda _checks: True)


def drive_lifespan() -> None:
    """Запускает lifespan приложения до полного входа и выхода."""

    async def run() -> None:
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(run())


def test_lifespan_disabled_does_not_create_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без флага планировщик не создаётся и ничего не регистрируется."""
    patch_startup_checks(monkeypatch)
    monkeypatch.setattr(app_settings, "scheduler_enabled", False)

    created: list[FakeAsyncIOScheduler] = []

    def fake_factory() -> FakeAsyncIOScheduler:
        instance = FakeAsyncIOScheduler()
        created.append(instance)
        return instance

    monkeypatch.setattr(main_module, "build_scheduler_service", FakeSchedulerService)
    monkeypatch.setattr(main_module, "AsyncIOScheduler", fake_factory)

    drive_lifespan()

    assert created == []


def test_lifespan_enabled_registers_and_starts_scheduler_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """С флагом регистрируется ежедневная задача, start/shutdown по одному разу."""
    patch_startup_checks(monkeypatch)
    monkeypatch.setattr(app_settings, "scheduler_enabled", True)

    # Реальный SchedulerService с фейковым сбором: проверяем полную цепочку
    # lifespan -> register_daily_job -> AsyncIOScheduler.add_job без БД.
    real_service = SchedulerService(
        source_collection_service=FakeSourceCollectionService(make_result()),
        app_settings=make_settings(
            morning_brief_run_time="08:00",
            morning_brief_timezone="Europe/Moscow",
        ),
    )
    monkeypatch.setattr(main_module, "build_scheduler_service", lambda: real_service)

    created: list[FakeAsyncIOScheduler] = []

    def fake_factory() -> FakeAsyncIOScheduler:
        instance = FakeAsyncIOScheduler()
        created.append(instance)
        return instance

    monkeypatch.setattr(main_module, "AsyncIOScheduler", fake_factory)

    async def run_with_assertions() -> None:
        async with main_module.lifespan(main_module.app):
            assert created[0].start_calls == 1
            assert created[0].shutdown_calls == 0

    asyncio.run(run_with_assertions())

    assert len(created) == 1
    scheduler = created[0]
    assert scheduler.start_calls == 1
    assert scheduler.shutdown_calls == 1
    assert len(scheduler.registered_jobs) == 1
    job = scheduler.registered_jobs[0]
    assert job["func"] == real_service.run_once
    assert job["trigger"] == "cron"
    assert job["hour"] == 8
    assert job["minute"] == 0
    assert job["timezone"] == "Europe/Moscow"
    assert job["id"] == "morning_brief_collection"
    assert job["replace_existing"] is True


def test_lifespan_enabled_fails_startup_and_shuts_down_partial_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ошибка старта планировщика не позволяет приложению работать молча."""
    patch_startup_checks(monkeypatch)
    monkeypatch.setattr(app_settings, "scheduler_enabled", True)

    fake_service = FakeSchedulerService()
    monkeypatch.setattr(main_module, "build_scheduler_service", lambda: fake_service)

    created: list[FakeAsyncIOScheduler] = []

    def fake_factory() -> FakeAsyncIOScheduler:
        instance = FakeAsyncIOScheduler()
        instance.start_error = RuntimeError("apscheduler start failed")
        created.append(instance)
        return instance

    monkeypatch.setattr(main_module, "AsyncIOScheduler", fake_factory)

    with pytest.raises(RuntimeError, match="apscheduler start failed"):
        drive_lifespan()

    scheduler = created[0]
    assert fake_service.register_calls == 1
    assert scheduler.start_calls == 1
    assert scheduler.shutdown_calls == 1
