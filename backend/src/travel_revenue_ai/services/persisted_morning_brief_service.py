"""Атомарный use case сохранения исторического MorningBrief."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from travel_revenue_ai.mappers.persisted_morning_brief_mapper import (
    MappedCard,
    map_brief,
    map_runtime_card,
)
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.repositories.morning_brief_repository import MorningBriefRepository
from travel_revenue_ai.schemas.persisted_morning_brief import (
    MorningBriefExecutionContext,
    PersistedMorningBriefRequest,
    PersistedMorningBriefResult,
)
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    BusinessDateConflictError,
    DuplicateSignalIdsError,
    IdempotencyConflictError,
    InvalidPersistedMorningBriefRequest,
    PersistenceError,
    PipelineExecutionError,
    SignalAgencyOwnershipError,
    SignalNotFoundError,
)
from travel_revenue_ai.services.pipeline_service import PipelineService


class PersistedMorningBriefService:
    """Единственный владелец транзакции aggregate MorningBrief."""

    def __init__(
        self,
        *,
        session: Session,
        pipeline_service: PipelineService,
        repository: MorningBriefRepository | None = None,
        execution_context_factory: Callable[[], MorningBriefExecutionContext] | None = None,
    ) -> None:
        self.session = session
        self.pipeline_service = pipeline_service
        self.repository = repository or MorningBriefRepository(session)
        self.execution_context_factory = (
            execution_context_factory or self._default_execution_context
        )

    def generate(self, request: PersistedMorningBriefRequest) -> PersistedMorningBriefResult:
        """Создаёт aggregate или возвращает идемпотентный historical replay."""
        self._validate_request(request)

        try:
            existing = self.repository.find_brief_by_idempotency_key(
                agency_id=request.agency_id,
                idempotency_key=request.idempotency_key,
            )
            if existing is not None:
                return self._replay_or_raise(existing, request)

            date_conflict = self.repository.find_brief_by_business_date(
                agency_id=request.agency_id,
                brief_date=request.brief_date,
            )
            if date_conflict is not None:
                raise BusinessDateConflictError(
                    "Для агентства уже существует бриф на эту дату"
                )

            persisted_signals = self._load_and_validate_signals(request)
            money_effects = {
                signal.signal_id: copy.deepcopy(signal.raw_data).get("money_effect", 0)
                for signal in persisted_signals
            }
            runtime_signals = [
                self._make_detached_runtime_signal(signal) for signal in persisted_signals
            ]

            context = self.execution_context_factory()
            try:
                pipeline_result = self.pipeline_service.run(runtime_signals)
            except Exception as error:
                raise PipelineExecutionError(
                    "Pipeline не смог сформировать утренний бриф"
                ) from error

            completed_context = MorningBriefExecutionContext(
                execution_id=context.execution_id,
                started_at=context.started_at,
                completed_at=datetime.now(timezone.utc),
                engine_version=context.engine_version,
                scoring_version=context.scoring_version,
                filtering_version=context.filtering_version,
                feature_flags=copy.deepcopy(context.feature_flags),
            )
            mapped_cards = self._map_cards(
                runtime_brief=pipeline_result.morning_brief,
                agency_id=request.agency_id,
                money_effects=money_effects,
            )
            self.repository.add_decision_cards(
                [mapped_card.orm_card for mapped_card in mapped_cards]
            )
            self.repository.flush()

            persisted_brief = map_brief(
                pipeline_result.morning_brief,
                request=request,
                context=completed_context,
                mapped_cards=mapped_cards,
            )
            self.repository.add_morning_brief(persisted_brief)
            self.repository.flush()
            self.session.commit()
            return self._result_from_brief(persisted_brief, replayed=False)
        except (
            InvalidPersistedMorningBriefRequest,
            DuplicateSignalIdsError,
            SignalNotFoundError,
            SignalAgencyOwnershipError,
            IdempotencyConflictError,
            BusinessDateConflictError,
            PipelineExecutionError,
        ):
            self.session.rollback()
            raise
        except IntegrityError as error:
            self.session.rollback()
            return self._resolve_integrity_race(request, error)
        except Exception as error:
            self.session.rollback()
            raise PersistenceError(
                "Не удалось атомарно сохранить MorningBrief aggregate"
            ) from error

    def _validate_request(self, request: PersistedMorningBriefRequest) -> None:
        """Проверяет команду до любых обращений к pipeline."""
        if not request.signal_ids:
            raise InvalidPersistedMorningBriefRequest(
                "Для persisted брифа нужен хотя бы один сигнал"
            )
        if len(set(request.signal_ids)) != len(request.signal_ids):
            raise DuplicateSignalIdsError(
                "Во входном запросе повторяются идентификаторы сигналов"
            )
        if not request.idempotency_key.strip():
            raise InvalidPersistedMorningBriefRequest(
                "idempotency_key не может быть пустым"
            )

    def _load_and_validate_signals(
        self,
        request: PersistedMorningBriefRequest,
    ) -> list[Signal]:
        """Отделяет ошибки отсутствия и ownership, сохраняя входной порядок."""
        all_found = self.repository.load_signals_by_ids(request.signal_ids)
        found_ids = {signal.signal_id for signal in all_found}
        missing_ids = [
            signal_id for signal_id in request.signal_ids if signal_id not in found_ids
        ]
        if missing_ids:
            raise SignalNotFoundError(missing_ids)

        foreign_ids = [
            signal.signal_id
            for signal in all_found
            if signal.agency_id != request.agency_id
        ]
        if foreign_ids:
            raise SignalAgencyOwnershipError(
                f"Сигналы не принадлежат агентству: {', '.join(map(str, foreign_ids))}"
            )

        agency_signals = self.repository.load_signals(
            agency_id=request.agency_id,
            signal_ids=request.signal_ids,
        )
        if len(agency_signals) != len(request.signal_ids):
            raise SignalAgencyOwnershipError(
                "Не удалось загрузить все сигналы агентства после проверки ownership"
            )
        return agency_signals

    def _map_cards(
        self,
        *,
        runtime_brief: object,
        agency_id: uuid.UUID,
        money_effects: dict[uuid.UUID, object],
    ) -> list[MappedCard]:
        """Сохраняет явный section-aware порядок runtime-карточек."""
        mapped_cards: list[MappedCard] = []
        for section in ("opportunities", "risks", "market_insights"):
            cards = getattr(runtime_brief, section)
            for ordinal, runtime_card in enumerate(cards):
                if runtime_card.signal_id not in money_effects:
                    raise PersistenceError(
                        "Runtime-карточка ссылается на сигнал вне approved input"
                    )
                mapped_cards.append(
                    MappedCard(
                        runtime_card=runtime_card,
                        orm_card=map_runtime_card(
                            runtime_card,
                            agency_id=agency_id,
                            money_effect_raw=money_effects[runtime_card.signal_id],
                        ),
                        section=section,
                        ordinal=ordinal,
                    )
                )
        return mapped_cards

    def _replay_or_raise(
        self,
        existing: MorningBrief,
        request: PersistedMorningBriefRequest,
    ) -> PersistedMorningBriefResult:
        """Возвращает replay только при идентичной semantic-команде."""
        saved_fingerprint = (existing.feature_flags_snapshot or {}).get(
            "request_fingerprint"
        )
        if saved_fingerprint != request.fingerprint():
            raise IdempotencyConflictError(
                "idempotency_key уже использован для другого semantic-запроса"
            )
        return self._result_from_brief(existing, replayed=True)

    def _resolve_integrity_race(
        self,
        request: PersistedMorningBriefRequest,
        error: IntegrityError,
    ) -> PersistedMorningBriefResult:
        """Разрешает гонку только через финальные DB unique constraints."""
        existing = self.repository.find_brief_by_idempotency_key(
            agency_id=request.agency_id,
            idempotency_key=request.idempotency_key,
        )
        if existing is not None:
            return self._replay_or_raise(existing, request)

        date_conflict = self.repository.find_brief_by_business_date(
            agency_id=request.agency_id,
            brief_date=request.brief_date,
        )
        if date_conflict is not None:
            raise BusinessDateConflictError(
                "Для агентства уже существует бриф на эту дату"
            ) from error
        raise PersistenceError(
            "Нарушение ограничения БД при сохранении MorningBrief aggregate"
        ) from error

    @staticmethod
    def _make_detached_runtime_signal(persisted_signal: Signal) -> Signal:
        """Создаёт unattached runtime-копию, чтобы enrichment не dirty-ил ORM."""
        return Signal(
            signal_id=persisted_signal.signal_id,
            agency_id=persisted_signal.agency_id,
            source_id=persisted_signal.source_id,
            signal_type=persisted_signal.signal_type,
            raw_data=copy.deepcopy(persisted_signal.raw_data),
            status=persisted_signal.status,
        )

    @staticmethod
    def _default_execution_context() -> MorningBriefExecutionContext:
        """Создаёт минимальный execution context без внешнего wiring."""
        return MorningBriefExecutionContext(
            execution_id=str(uuid.uuid4()),
            started_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _result_from_brief(
        brief: MorningBrief,
        *,
        replayed: bool,
    ) -> PersistedMorningBriefResult:
        """Преобразует исторический ORM-brief в компактный результат use case."""
        return PersistedMorningBriefResult(
            brief_id=brief.brief_id,
            agency_id=brief.agency_id,
            brief_date=brief.date,
            opportunity_card_ids=tuple(
                uuid.UUID(card_id) for card_id in brief.top_opportunity_card_ids
            ),
            risk_card_ids=tuple(uuid.UUID(card_id) for card_id in brief.top_risk_card_ids),
            market_insight_card_ids=tuple(
                uuid.UUID(card_id) for card_id in brief.market_insight_card_ids
            ),
            main_decision_card_id=brief.main_decision_card_id,
            replayed=replayed,
        )