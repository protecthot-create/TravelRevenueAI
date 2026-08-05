"""Сервис конвейерной обработки сигналов (Pipeline Service).

Координирует последовательный запуск существующих сервисов:
Signal -> SignalEnrichmentService -> RevenueScoringService -> FilteringService ->
DecisionCardService -> MorningBriefService.

При явном внедрении RevenueIntelligenceEngine дополнительно выполняет
изолированный анализ. Его результат не влияет на существующий Morning Brief.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from travel_revenue_ai.intelligence.signal_enrichment_service import SignalEnrichmentService
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.observability.metrics import MetricsService
from travel_revenue_ai.revenue_intelligence.contracts import (
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.revenue_intelligence.engine import RevenueIntelligenceEngine
from travel_revenue_ai.services.decision_card_service import (
    DecisionCard,
    DecisionCardService,
)
from travel_revenue_ai.services.filtering_service import (
    FilterResult,
    FilteringResult,
    FilteringService,
)
from travel_revenue_ai.services.morning_brief_service import (
    MorningBriefResult,
    MorningBriefService,
)
from travel_revenue_ai.services.revenue_scoring_service import (
    RevenueScoringService,
    ScoreResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """Результат запуска Pipeline с необязательным Intelligence-расширением."""

    morning_brief: MorningBriefResult
    revenue_intelligence_results: list[RevenueIntelligenceResult] | None = None


class PipelineService:
    """Сервис полного конвейера генерации Morning Brief."""

    def __init__(
        self,
        signal_enrichment_service: SignalEnrichmentService | None = None,
        revenue_scoring_service: RevenueScoringService | None = None,
        filtering_service: FilteringService | None = None,
        decision_card_service: DecisionCardService | None = None,
        morning_brief_service: MorningBriefService | None = None,
        metrics_service: MetricsService | None = None,
        revenue_intelligence_engine: RevenueIntelligenceEngine | None = None,
    ) -> None:
        """Инициализирует конвейер с зависимостями по умолчанию или внедрёнными извне."""
        self.metrics_service = metrics_service or MetricsService()
        self.signal_enrichment_service = signal_enrichment_service or SignalEnrichmentService(
            metrics_service=self.metrics_service
        )
        self.revenue_scoring_service = revenue_scoring_service or RevenueScoringService()
        self.filtering_service = filtering_service or FilteringService()
        self.decision_card_service = decision_card_service or DecisionCardService()
        self.morning_brief_service = morning_brief_service or MorningBriefService()
        self.revenue_intelligence_engine = revenue_intelligence_engine

    def generate_morning_brief(self, signals: list[Signal]) -> MorningBriefResult:
        """Запускает совместимый Pipeline и возвращает прежний MorningBriefResult."""
        return self.run(signals).morning_brief

    def run(self, signals: list[Signal]) -> PipelineResult:
        """Запускает Pipeline и возвращает необязательный результат Revenue Intelligence."""
        if signals is None:
            raise ValueError("signals не может быть None")

        started_at = perf_counter()
        self.metrics_service.increment("signals_received", len(signals))
        logger.info("pipeline_started signals_received=%s", len(signals))

        try:
            self._enrich_signals(signals)
            self.metrics_service.increment("signals_enriched", len(signals))

            intelligence_results = self._run_revenue_intelligence(signals)

            score_results = self.revenue_scoring_service.score_signals(signals)
            self.metrics_service.increment("signals_scored", len(score_results))

            filtering_result = self.filtering_service.filter_signals(score_results)
            self.metrics_service.increment(
                "signals_filtered",
                len(filtering_result.passed_signals),
            )
            decision_cards = self._generate_decision_cards(
                signals=signals,
                score_results=score_results,
                filtering_result=filtering_result,
            )
            self.metrics_service.increment("decision_cards_created", len(decision_cards))

            morning_brief = self.morning_brief_service.generate_brief(decision_cards)
            self.metrics_service.increment("morning_briefs_generated")
            return PipelineResult(
                morning_brief=morning_brief,
                revenue_intelligence_results=intelligence_results,
            )
        finally:
            duration_ms = int((perf_counter() - started_at) * 1000)
            self.metrics_service.record_duration_ms("pipeline_duration_ms", duration_ms)
            logger.info("pipeline_finished pipeline_duration_ms=%s", duration_ms)

    def _run_revenue_intelligence(
        self,
        signals: list[Signal],
    ) -> list[RevenueIntelligenceResult] | None:
        """Запускает Engine изолированно; его сбой не прерывает существующий Pipeline."""
        if self.revenue_intelligence_engine is None:
            return None

        results: list[RevenueIntelligenceResult] = []
        for signal in signals:
            try:
                results.append(
                    self.revenue_intelligence_engine.process(
                        RevenueIntelligenceInput.from_signal(signal)
                    )
                )
            except Exception:
                logger.exception(
                    "revenue_intelligence_failed signal_id=%s",
                    signal.signal_id,
                )

        return results

    def _enrich_signals(self, signals: list[Signal]) -> None:
        """Добавляет Intelligence Layer, не меняя доменные поля сигналов."""
        raw_signals = [signal.raw_data for signal in signals]
        for index, signal in enumerate(signals):
            known_signals = raw_signals[:index] + raw_signals[index + 1 :]
            signal.raw_data = self.signal_enrichment_service.enrich(
                signal.raw_data,
                known_signals=known_signals,
            )

    def _generate_decision_cards(
        self,
        signals: list[Signal],
        score_results: list[ScoreResult],
        filtering_result: FilteringResult,
    ) -> list[DecisionCard]:
        """Собирает Decision Card только для сигналов, прошедших фильтр."""
        score_results_by_id = {result.signal_id: result for result in score_results}
        signals_by_id = {signal.signal_id: signal for signal in signals}

        card_inputs: list[tuple[FilterResult, ScoreResult, dict[str, object] | None]] = []
        for filter_result in filtering_result.passed_signals:
            score_result = score_results_by_id.get(filter_result.signal_id)
            if score_result is None:
                raise ValueError(
                    f"Не найден результат scoring для сигнала {filter_result.signal_id}"
                )

            signal = signals_by_id.get(filter_result.signal_id)
            signal_data = None
            if signal is not None:
                # Передаём тип сигнала отдельно от raw_data, чтобы category/card_type
                # сохранялись корректно даже если source payload не содержит signal_type.
                signal_data = dict(signal.raw_data)
                signal_data.setdefault("signal_type", signal.signal_type)
            card_inputs.append((filter_result, score_result, signal_data))

        return self.decision_card_service.generate_cards(card_inputs)