"""Оркестрация сбора сигналов из источников и запуска Morning Brief."""

from __future__ import annotations

from dataclasses import dataclass

from travel_revenue_ai.services.morning_brief_service import MorningBriefResult
from travel_revenue_ai.services.pipeline_service import PipelineService
from travel_revenue_ai.services.signal_service import SignalService
from travel_revenue_ai.sources.email import EmailSourceAdapter
from travel_revenue_ai.sources.manager import SourceManager
from travel_revenue_ai.sources.telegram import TelegramSourceAdapter


@dataclass(frozen=True, slots=True)
class SourceCollectionResult:
    """Итог одного запуска сбора источников и генерации утреннего брифа."""

    collected_count: int
    saved_count: int
    errors_count: int
    morning_brief: MorningBriefResult


class SourceCollectionService:
    """Координирует источник данных, сохранение новых сигналов и pipeline.

    Сервис не содержит логики scoring, filtering, карточек или формирования
    брифа. Он передаёт в ``PipelineService`` только те сигналы, которые были
    успешно сохранены через ``SignalService``.
    """

    def __init__(
        self,
        *,
        source_manager: SourceManager,
        signal_service: SignalService,
        pipeline_service: PipelineService,
        email_source_adapter: EmailSourceAdapter | None = None,
        telegram_source_adapter: TelegramSourceAdapter | None = None,
    ) -> None:
        """Инициализирует зависимости и регистрирует переданные адаптеры."""
        self.source_manager = source_manager
        self.signal_service = signal_service
        self.pipeline_service = pipeline_service

        for adapter in (email_source_adapter, telegram_source_adapter):
            if adapter is not None:
                self.source_manager.register(adapter)

    def collect_and_generate_morning_brief(self) -> SourceCollectionResult:
        """Собирает, сохраняет сигналы и формирует Morning Brief.

        Ошибки адаптеров уже изолированы ``SourceManager``. Ошибка сохранения
        одного сигнала также не должна мешать обработке остальных сигналов.
        Ошибки самого pipeline намеренно не скрываются: готовый бриф без
        успешного запуска конвейера возвращать нельзя.
        """
        source_results = self.source_manager.collect_all()
        collected_count = sum(len(result.signals) for result in source_results)
        errors_count = sum(not result.is_successful for result in source_results)

        saved_signals = []
        for source_result in source_results:
            if not source_result.is_successful:
                continue

            for signal in source_result.signals:
                try:
                    saved_signals.append(
                        self.signal_service.create_signal(
                            agency_id=signal.agency_id,
                            source_id=signal.source_id,
                            signal_type=signal.signal_type,
                            raw_data=signal.raw_data,
                        )
                    )
                except Exception:
                    errors_count += 1

        morning_brief = self.pipeline_service.generate_morning_brief(saved_signals)
        return SourceCollectionResult(
            collected_count=collected_count,
            saved_count=len(saved_signals),
            errors_count=errors_count,
            morning_brief=morning_brief,
        )