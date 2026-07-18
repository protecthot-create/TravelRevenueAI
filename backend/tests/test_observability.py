"""Тесты observability и feature flags Sprint 6.7."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import pytest

from travel_revenue_ai.config import Settings
from travel_revenue_ai.intelligence.signal_enrichment_service import SignalEnrichmentService
from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.observability.feature_flags import FeatureFlagService
from travel_revenue_ai.observability.metrics import MetricsService
from travel_revenue_ai.services.morning_brief_service import MorningBriefService
from travel_revenue_ai.services.pipeline_service import PipelineService


def make_raw_data() -> dict[str, object]:
    """Создаёт минимальный валидный raw payload без секретов."""
    return {
        "text": "Coral Travel: скидка 25% на Турцию. Срочно, акция до 20 июля.",
        "title": "Раннее бронирование Турция",
        "money_effect": 85_000,
        "deadline_hours": 48,
        "probability": 0.72,
        "controllability": 1.0,
        "risk": False,
        "repeatable": True,
        "context_match": True,
        "season": "peak",
        "summary": "Спрос растёт",
    }


def make_signal() -> Signal:
    """Создаёт сигнал для полного pipeline."""
    return Signal(
        agency_id=UUID("11111111-1111-1111-1111-111111111111"),
        source_id=UUID("22222222-2222-2222-2222-222222222222"),
        signal_type=SignalTypeEnum.opportunity,
        status=SignalStatusEnum.normalized,
        raw_data=make_raw_data(),
    )


def test_feature_flags_read_settings_and_return_snapshot() -> None:
    """FeatureFlagService использует переданный Settings без изменения глобальной конфигурации."""
    flags = FeatureFlagService(
        Settings(
            intelligence_enabled=False,
            intelligence_priority_enabled=False,
            duplicate_detection_enabled=True,
            entity_extraction_enabled=False,
        )
    )

    assert flags.is_enabled("intelligence_enabled") is False
    assert flags.snapshot() == {
        "intelligence_enabled": False,
        "intelligence_priority_enabled": False,
        "duplicate_detection_enabled": True,
        "entity_extraction_enabled": False,
    }


def test_metrics_accumulate_duration_and_return_isolated_snapshot() -> None:
    """Метрики накапливаются, а внешняя мутация snapshot не меняет сервис."""
    metrics = MetricsService()
    metrics.increment("signals_received", 2)
    metrics.record_duration_ms("pipeline_duration_ms", 17)

    snapshot = dict(metrics.snapshot())
    snapshot["signals_received"] = 100

    assert metrics.snapshot()["signals_received"] == 2
    assert metrics.snapshot()["pipeline_duration_ms"] == 17
    assert metrics.snapshot()["enrichment_errors"] == 0


def test_metrics_reject_unknown_or_negative_values() -> None:
    """Некорректные имена и значения метрик не принимаются."""
    metrics = MetricsService()

    with pytest.raises(ValueError, match="Неподдерживаемая"):
        metrics.increment("unknown_metric")
    with pytest.raises(ValueError, match="не может быть отрицательным"):
        metrics.increment("signals_received", -1)


def test_disabled_intelligence_does_not_change_pipeline_business_output() -> None:
    """Выключенный Intelligence не влияет на итог Morning Brief."""
    enabled_pipeline = PipelineService(
        morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18))
    )
    disabled_flags = FeatureFlagService(Settings(intelligence_enabled=False))
    disabled_pipeline = PipelineService(
        signal_enrichment_service=SignalEnrichmentService(
            feature_flag_service=disabled_flags,
        ),
        morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18)),
    )

    enabled_signal = make_signal()
    disabled_signal = make_signal()
    enabled_result = enabled_pipeline.generate_morning_brief([enabled_signal])
    disabled_result = disabled_pipeline.generate_morning_brief([disabled_signal])

    assert enabled_result.summary is not None
    assert disabled_result.summary is not None
    assert enabled_result.summary.full_text == disabled_result.summary.full_text
    assert "intelligence" in enabled_signal.raw_data["metadata"]
    assert "metadata" not in disabled_signal.raw_data


def test_pipeline_accumulates_required_metrics() -> None:
    """Pipeline записывает все счётчики стадий и длительность."""
    metrics = MetricsService()
    pipeline = PipelineService(
        metrics_service=metrics,
        morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18)),
    )

    pipeline.generate_morning_brief([make_signal()])
    snapshot = metrics.snapshot()

    assert snapshot["signals_received"] == 1
    assert snapshot["signals_enriched"] == 1
    assert snapshot["signals_scored"] == 1
    assert snapshot["signals_filtered"] == 0
    assert snapshot["decision_cards_created"] == 0
    assert snapshot["morning_briefs_generated"] == 1
    assert snapshot["pipeline_duration_ms"] >= 0


def test_enrichment_logs_safe_aggregate_counts(caplog: pytest.LogCaptureFixture) -> None:
    """Лог enrichment содержит только агрегированные числа, но не текст сообщения."""
    service = SignalEnrichmentService()

    with caplog.at_level(logging.INFO):
        service.enrich(make_raw_data(), reference_date=date(2026, 7, 18))

    messages = [record.getMessage() for record in caplog.records]
    assert any("signal_enriched entities_found=" in message for message in messages)
    assert all("Coral Travel" not in message for message in messages)


def test_enrichment_error_increments_metric_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ошибка этапа фиксируется метрикой и безопасным structured log."""
    class FailingEntityExtractor:
        """Имитирует ошибку внешней зависимости enrichment."""

        def extract(self, text: str, *, reference_date: date | None = None) -> object:
            raise TypeError("некорректный справочник")

    metrics = MetricsService()
    service = SignalEnrichmentService(
        entity_extractor=FailingEntityExtractor(),  # type: ignore[arg-type]
        metrics_service=metrics,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(TypeError):
        service.enrich(make_raw_data())

    assert metrics.snapshot()["enrichment_errors"] == 1
    assert any(
        record.getMessage() == "signal_enrichment_failed" for record in caplog.records
    )