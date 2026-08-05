"""Инфраструктурные проверки работоспособности и готовности приложения."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from travel_revenue_ai.config import settings
from travel_revenue_ai.database import engine
from travel_revenue_ai.observability.feature_flags import FeatureFlagService
from travel_revenue_ai.services.scheduler_service import SchedulerService
from travel_revenue_ai.sources.manager import SourceManager


def check_database() -> dict[str, str]:
    """Проверяет доступность соединения с текущей базой данных."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        return {"status": "error", "detail": f"Подключение к БД недоступно: {error}"}

    return {"status": "ok", "detail": "Подключение к БД подтверждено."}


def check_migrations() -> dict[str, str]:
    """Проверяет, что текущая ревизия БД совпадает с head Alembic."""
    try:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        expected_revision = script.get_current_head()

        with engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
    except Exception as error:  # Проверка должна вернуть диагностируемый readiness-статус.
        return {"status": "error", "detail": f"Миграции Alembic недоступны: {error}"}

    if current_revision != expected_revision:
        return {
            "status": "error",
            "detail": (
                "Миграции не применены: "
                f"текущая ревизия {current_revision or 'отсутствует'}, "
                f"ожидается {expected_revision or 'отсутствует'}."
            ),
        }

    return {"status": "ok", "detail": "Миграции Alembic актуальны."}


def check_source_manager() -> dict[str, str]:
    """Проверяет, что SourceManager можно инициализировать."""
    try:
        SourceManager()
    except Exception as error:  # Инфраструктурная проверка должна вернуть статус, а не 500.
        return {"status": "error", "detail": f"SourceManager недоступен: {error}"}

    return {"status": "ok", "detail": "SourceManager доступен."}


def check_scheduler() -> dict[str, str]:
    """Проверяет корректность конфигурации планировщика без запуска job."""
    try:
        SchedulerService(
            source_collection_service=object(),  # type: ignore[arg-type]
            app_settings=settings,
        )
    except (TypeError, ValueError) as error:
        return {"status": "error", "detail": f"Scheduler недоступен: {error}"}

    return {"status": "ok", "detail": "Конфигурация scheduler корректна."}


def check_feature_flags() -> dict[str, str]:
    """Проверяет, что feature flags доступны для чтения."""
    try:
        FeatureFlagService(settings).snapshot()
    except (AttributeError, TypeError, ValueError) as error:
        return {"status": "error", "detail": f"Feature flags недоступны: {error}"}

    return {"status": "ok", "detail": "Feature flags доступны."}


def check_metrics(metrics_renderer: Callable[[], str]) -> dict[str, str]:
    """Проверяет, что HTTP-метрики формируются без ошибки."""
    try:
        metrics_renderer()
    except Exception as error:  # Метрики не должны ломать readiness endpoint.
        return {"status": "error", "detail": f"Metrics недоступны: {error}"}

    return {"status": "ok", "detail": "HTTP-метрики доступны."}


def readiness_checks(metrics_renderer: Callable[[], str]) -> dict[str, dict[str, str]]:
    """Выполняет полный набор readiness-проверок."""
    return {
        "database": check_database(),
        "migrations": check_migrations(),
        "source_manager": check_source_manager(),
        "scheduler": check_scheduler(),
        "metrics": check_metrics(metrics_renderer),
        "feature_flags": check_feature_flags(),
    }


def is_ready(checks: dict[str, dict[str, str]]) -> bool:
    """Возвращает True, только если каждая проверка завершилась успешно."""
    return all(result["status"] == "ok" for result in checks.values())