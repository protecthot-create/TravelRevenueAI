"""Оркестрация сбора сигналов из источников и запуска Morning Brief."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
import uuid

from travel_revenue_ai.schemas.persisted_morning_brief import (
    BriefTriggerType,
    PersistedMorningBriefRequest,
    PersistedMorningBriefResult,
)
from travel_revenue_ai.services.morning_brief_service import MorningBriefResult
from travel_revenue_ai.services.persisted_morning_brief_service import (
    PersistedMorningBriefService,
)
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
    persisted_briefs: dict[uuid.UUID, PersistedMorningBriefResult] = field(
        default_factory=dict
    )


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
        persisted_morning_brief_service: PersistedMorningBriefService | None = None,
        email_source_adapter: EmailSourceAdapter | None = None,
        telegram_source_adapter: TelegramSourceAdapter | None = None,
    ) -> None:
        """Инициализирует зависимости и регистрирует переданные адаптеры."""
        self.source_manager = source_manager
        self.signal_service = signal_service
        self.pipeline_service = pipeline_service
        self.persisted_morning_brief_service = persisted_morning_brief_service

        for adapter in (email_source_adapter, telegram_source_adapter):
            if adapter is not None:
                self.source_manager.register(adapter)

    def collect_and_generate_morning_brief(
        self,
        *,
        brief_date: date | None = None,
        trigger_type: BriefTriggerType = BriefTriggerType.system,
        run_id: str | None = None,
    ) -> SourceCollectionResult:
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
        persisted_briefs: dict[uuid.UUID, PersistedMorningBriefResult] = {}

        if self.persisted_morning_brief_service is not None:
            business_date = brief_date or morning_brief.date
            signals_by_agency: dict[uuid.UUID, list[object]] = defaultdict(list)
            for signal in saved_signals:
                signals_by_agency[signal.agency_id].append(signal)

            for agency_id, agency_signals in signals_by_agency.items():
                signal_ids = tuple(signal.signal_id for signal in agency_signals)
                idempotency_key = self._build_idempotency_key(
                    agency_id=agency_id,
                    brief_date=business_date,
                    signal_ids=signal_ids,
                    trigger_type=trigger_type,
                    run_id=run_id,
                )
                try:
                    persisted_briefs[agency_id] = (
                        self.persisted_morning_brief_service.generate(
                            PersistedMorningBriefRequest(
                                agency_id=agency_id,
                                brief_date=business_date,
                                signal_ids=signal_ids,
                                idempotency_key=idempotency_key,
                                trigger_type=trigger_type,
                                request_id=run_id,
                            )
                        )
                    )
                except Exception:
                    errors_count += 1

        return SourceCollectionResult(
            collected_count=collected_count,
            saved_count=len(saved_signals),
            errors_count=errors_count,
            morning_brief=morning_brief,
            persisted_briefs=persisted_briefs,
        )

    @staticmethod
    def _build_idempotency_key(
        *,
        agency_id: uuid.UUID,
        brief_date: date,
        signal_ids: tuple[uuid.UUID, ...],
        trigger_type: BriefTriggerType,
        run_id: str | None,
    ) -> str:
        """Строит идемпотентный ключ одного запуска без секретных данных."""
        signal_part = ",".join(str(signal_id) for signal_id in signal_ids)
        run_part = run_id or "automatic"
        return (
            f"source-collection:{trigger_type.value}:{brief_date.isoformat()}:"
            f"{agency_id}:{run_part}:{signal_part}"
        )
