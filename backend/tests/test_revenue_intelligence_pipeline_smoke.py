"""Smoke-тесты безопасного подключения Revenue Intelligence к Pipeline."""

from __future__ import annotations

from uuid import uuid4

from travel_revenue_ai.composition import build_pipeline_service
from travel_revenue_ai.config import Settings
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceResult
from travel_revenue_ai.services.pipeline_service import PipelineService


def _signal() -> Signal:
    """Создаёт минимальный сигнал, проходящий прежний Pipeline."""
    return Signal(
        signal_id=uuid4(),
        agency_id=uuid4(),
        source_id=uuid4(),
        signal_type="market",
        raw_data={
            "title": "Тестовый сигнал",
            "potential_value": 50_000,
            "probability": 0.8,
            "deadline_hours": 24,
            "action": "Проверить тестовое предложение",
        },
    )


class _RecordingEngine:
    """Фиксирует изолированный вызов Engine."""

    def __init__(self) -> None:
        self.calls = 0

    def process(self, input_data: object) -> RevenueIntelligenceResult:
        """Возвращает пустой доменный результат."""
        self.calls += 1
        return RevenueIntelligenceResult()


class _FailingEngine:
    """Имитирует сбой дополнительного Engine."""

    def process(self, input_data: object) -> RevenueIntelligenceResult:
        """Прерывает только дополнительную ветку обработки."""
        raise RuntimeError("engine unavailable")


def test_pipeline_flag_false_keeps_engine_disabled() -> None:
    """При выключенном flag Pipeline сохраняет прежнее поведение."""
    pipeline = build_pipeline_service(
        Settings(revenue_intelligence_enabled=False, _env_file=None)
    )

    result = pipeline.run([_signal()])

    assert pipeline.revenue_intelligence_engine is None
    assert result.revenue_intelligence_results is None
    assert result.morning_brief is not None


def test_pipeline_flag_true_calls_injected_engine() -> None:
    """При включённом flag Pipeline запускает внедрённый Engine."""
    engine = _RecordingEngine()
    pipeline = PipelineService(revenue_intelligence_engine=engine)  # type: ignore[arg-type]

    result = pipeline.run([_signal()])

    assert engine.calls == 1
    assert result.revenue_intelligence_results is not None
    assert len(result.revenue_intelligence_results) == 1
    assert result.morning_brief is not None


def test_pipeline_survives_engine_error() -> None:
    """Ошибка Engine не нарушает формирование прежнего Morning Brief."""
    pipeline = PipelineService(
        revenue_intelligence_engine=_FailingEngine()  # type: ignore[arg-type]
    )

    result = pipeline.run([_signal()])

    assert result.revenue_intelligence_results == []
    assert result.morning_brief is not None