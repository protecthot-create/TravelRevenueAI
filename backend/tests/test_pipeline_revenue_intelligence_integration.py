"""Интеграционные тесты Revenue Intelligence в существующем Pipeline."""

from __future__ import annotations

from uuid import UUID, uuid4

from travel_revenue_ai.composition import build_pipeline_service
from travel_revenue_ai.config import Settings
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.revenue_intelligence.contracts import (
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.services.pipeline_service import PipelineService


def _signal() -> Signal:
    """Создаёт минимальный сигнал для полного существующего Pipeline."""
    return Signal(
        signal_id=uuid4(),
        agency_id=uuid4(),
        source_id=uuid4(),
        signal_type="market",
        raw_data={
            "title": "Раннее бронирование Турция",
            "potential_value": 50_000,
            "probability": 0.8,
            "deadline_hours": 24,
            "action": "Отправить предложение клиентам",
        },
    )


class _RecordingEngine:
    """Тестовая зависимость, сохраняющая входные данные Engine."""

    def __init__(self) -> None:
        self.received_signal_ids: list[UUID] = []

    def process(self, input_data: RevenueIntelligenceInput) -> RevenueIntelligenceResult:
        """Фиксирует вход и возвращает изолированный пустой результат."""
        self.received_signal_ids.append(input_data.signal_id)
        return RevenueIntelligenceResult()


class _FailingEngine:
    """Тестовая зависимость, имитирующая недоступность Engine."""

    def process(self, input_data: RevenueIntelligenceInput) -> RevenueIntelligenceResult:
        """Имитирует ошибку дополнительной ветки."""
        raise RuntimeError("revenue intelligence unavailable")


def test_flag_false_does_not_attach_revenue_intelligence_engine() -> None:
    """При flag=false Pipeline работает без дополнительной ветки."""
    pipeline = build_pipeline_service(
        Settings(revenue_intelligence_enabled=False, _env_file=None)
    )

    result = pipeline.run([_signal()])

    assert pipeline.revenue_intelligence_engine is None
    assert result.revenue_intelligence_results is None
    assert result.morning_brief is not None


def test_flag_true_runs_real_revenue_intelligence_engine() -> None:
    """При flag=true composition root подключает реальный Engine."""
    pipeline = build_pipeline_service(
        Settings(revenue_intelligence_enabled=True, _env_file=None)
    )

    result = pipeline.run([_signal()])

    assert pipeline.revenue_intelligence_engine is not None
    assert result.revenue_intelligence_results is not None
    assert len(result.revenue_intelligence_results) == 1
    assert result.morning_brief is not None


def test_engine_error_keeps_existing_pipeline_result_available() -> None:
    """Сбой Engine не прерывает создание прежнего Morning Brief."""
    pipeline = PipelineService(
        revenue_intelligence_engine=_FailingEngine()  # type: ignore[arg-type]
    )

    result = pipeline.run([_signal()])

    assert result.revenue_intelligence_results == []
    assert result.morning_brief is not None


def test_empty_signals_return_empty_revenue_intelligence_result() -> None:
    """Пустой вход не создаёт ложных результатов Intelligence."""
    pipeline = build_pipeline_service(
        Settings(revenue_intelligence_enabled=True, _env_file=None)
    )

    result = pipeline.run([])

    assert result.revenue_intelligence_results == []
    assert result.morning_brief is not None


def test_dependency_injection_uses_provided_engine_and_preserves_input() -> None:
    """Pipeline использует внедрённый Engine вместо реализации по умолчанию."""
    engine = _RecordingEngine()
    signal = _signal()
    pipeline = PipelineService(
        revenue_intelligence_engine=engine  # type: ignore[arg-type]
    )

    result = pipeline.run([signal])

    assert engine.received_signal_ids == [signal.signal_id]
    assert result.revenue_intelligence_results == [RevenueIntelligenceResult()]


def test_generate_morning_brief_keeps_backward_compatible_return_type() -> None:
    """Прежний публичный метод не раскрывает новый PipelineResult."""
    pipeline = build_pipeline_service(
        Settings(revenue_intelligence_enabled=True, _env_file=None)
    )

    morning_brief = pipeline.generate_morning_brief([_signal()])

    assert not hasattr(morning_brief, "revenue_intelligence_results")
    assert isinstance(morning_brief.brief_id, UUID)
