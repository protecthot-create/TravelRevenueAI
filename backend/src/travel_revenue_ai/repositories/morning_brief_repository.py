"""Repository для атомарного persisted aggregate MorningBrief."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.models.signal import Signal


class MorningBriefRepository:
    """Доступ к aggregate без управления транзакциями."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_brief_by_id(self, brief_id: uuid.UUID) -> MorningBrief | None:
        """Загружает persisted бриф по идентификатору."""
        statement = select(MorningBrief).where(MorningBrief.brief_id == brief_id)
        return self.session.scalar(statement)

    def list_briefs_by_agency(
        self,
        agency_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[MorningBrief]:
        """Загружает страницу historical briefs агентства, начиная с новых."""
        statement = (
            select(MorningBrief)
            .where(MorningBrief.agency_id == agency_id)
            .order_by(MorningBrief.created_at.desc(), MorningBrief.brief_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement))

    def find_brief_by_idempotency_key(
        self,
        *,
        agency_id: uuid.UUID,
        idempotency_key: str,
    ) -> MorningBrief | None:
        """Находит historical brief по unique idempotency key."""
        statement = select(MorningBrief).where(
            MorningBrief.agency_id == agency_id,
            MorningBrief.idempotency_key == idempotency_key,
        )
        return self.session.scalar(statement)

    def find_brief_by_business_date(
        self,
        *,
        agency_id: uuid.UUID,
        brief_date: date,
    ) -> MorningBrief | None:
        """Находит historical brief по unique business date."""
        statement = select(MorningBrief).where(
            MorningBrief.agency_id == agency_id,
            MorningBrief.date == brief_date,
        )
        return self.session.scalar(statement)

    def load_signals(
        self,
        *,
        agency_id: uuid.UUID,
        signal_ids: Sequence[uuid.UUID],
    ) -> list[Signal]:
        """Загружает сигналы агентства в точном порядке входного запроса."""
        if not signal_ids:
            return []
        statement = select(Signal).where(
            Signal.agency_id == agency_id,
            Signal.signal_id.in_(signal_ids),
        )
        signals_by_id = {
            signal.signal_id: signal
            for signal in self.session.scalars(statement)
        }
        return [
            signals_by_id[signal_id]
            for signal_id in signal_ids
            if signal_id in signals_by_id
        ]

    def load_signals_by_ids(self, signal_ids: Sequence[uuid.UUID]) -> list[Signal]:
        """Загружает сигналы без фильтра владельца для явной проверки ownership."""
        if not signal_ids:
            return []
        statement = select(Signal).where(Signal.signal_id.in_(signal_ids))
        signals_by_id = {
            signal.signal_id: signal
            for signal in self.session.scalars(statement)
        }
        return [
            signals_by_id[signal_id]
            for signal_id in signal_ids
            if signal_id in signals_by_id
        ]

    def load_decision_cards_by_ids_ordered(
        self,
        card_ids: Sequence[uuid.UUID],
    ) -> list[DecisionCard]:
        """Загружает карточки в точном порядке входного списка идентификаторов."""
        if not card_ids:
            return []
        statement = select(DecisionCard).where(DecisionCard.decision_card_id.in_(card_ids))
        cards_by_id = {
            card.decision_card_id: card
            for card in self.session.scalars(statement)
        }
        return [
            cards_by_id[card_id]
            for card_id in card_ids
            if card_id in cards_by_id
        ]

    def get_decision_card_by_id(
        self,
        decision_card_id: uuid.UUID,
    ) -> DecisionCard | None:
        """Загружает persisted карточку по идентификатору."""
        statement = select(DecisionCard).where(
            DecisionCard.decision_card_id == decision_card_id
        )
        return self.session.scalar(statement)

    def add_decision_cards(self, cards: Sequence[DecisionCard]) -> None:
        """Добавляет ORM-карточки в текущую транзакцию."""
        self.session.add_all(cards)

    def add_morning_brief(self, brief: MorningBrief) -> None:
        """Добавляет ORM-бриф в текущую транзакцию."""
        self.session.add(brief)

    def flush(self) -> None:
        """Выполняет flush текущей транзакции без commit."""
        self.session.flush()
