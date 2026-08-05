"""Минимальные проверки feature flag Revenue Intelligence."""

from travel_revenue_ai.config import Settings


def test_revenue_intelligence_is_disabled_by_default(monkeypatch) -> None:
    """Feature flag выключен, если переменная окружения не задана."""
    monkeypatch.delenv("REVENUE_INTELLIGENCE_ENABLED", raising=False)

    assert Settings(_env_file=None).revenue_intelligence_enabled is False


def test_revenue_intelligence_accepts_explicit_false(monkeypatch) -> None:
    """Feature flag читает явное выключение из окружения."""
    monkeypatch.setenv("REVENUE_INTELLIGENCE_ENABLED", "false")

    assert Settings(_env_file=None).revenue_intelligence_enabled is False


def test_revenue_intelligence_accepts_explicit_true(monkeypatch) -> None:
    """Feature flag читает явное включение из окружения."""
    monkeypatch.setenv("REVENUE_INTELLIGENCE_ENABLED", "true")

    assert Settings(_env_file=None).revenue_intelligence_enabled is True