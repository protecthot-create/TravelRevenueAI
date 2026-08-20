"""Read-only сервис доступа к persisted MorningBrief aggregate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.repositories.morning_brief_repository import MorningBriefRepository
from travel_revenue_ai.services.morning_brief_read_errors import (
    MorningBriefReadIntegrityError,
    MorningBriefReadNotFoundError,
    MorningBriefReadPersistenceError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class MorningBriefReadResult:
    """Persisted бриф и карточки в порядке, сохранённом в aggregate."""

    brief: MorningBrief
    opportunity_cards: tuple[DecisionCard, ...]
    risk_cards: tuple[DecisionCard, ...]
    market_insight_cards: tuple[DecisionCard, ...]
    main_decision_card: DecisionCard | None


@dataclass(frozen=True)
class MorningBriefHistoryItem:
    """Metadata-only представление записи history для будущего DTO."""

    brief: MorningBrief
    opportunity_count: int
    risk_count: int
    market_insight_count: int
    total_card_count: int


class MorningBriefReadService:
    """Читает persisted MorningBrief без запуска pipeline и управления транзакцией."""

    def __init__(
        self,
        *,
        repository: MorningBriefRepository | None = None,
        session: Session | None = None,
    ) -> None:
        if repository is None:
            if session is None:
                raise ValueError("Нужен repository или session")
            repository = MorningBriefRepository(session)
        self.repository = repository

    def get_brief(
        self,
        brief_id: uuid.UUID,
        agency_id: uuid.UUID | None = None,
    ) -> MorningBriefReadResult:
        """Возвращает persisted бриф и его карточки в исходном порядке."""
        brief = self._load_brief(brief_id)
        if brief is None or (agency_id is not None and brief.agency_id != agency_id):
            raise MorningBriefReadNotFoundError(
                "MorningBrief не найден"
            )

        opportunity_ids = self._parse_ids(
            brief.top_opportunity_card_ids,
            section="top_opportunity_card_ids",
        )
        risk_ids = self._parse_ids(brief.top_risk_card_ids, section="top_risk_card_ids")
        market_ids = self._parse_ids(
            brief.market_insight_card_ids,
            section="market_insight_card_ids",
        )
        main_id = brief.main_decision_card_id
        all_ids = [*opportunity_ids, *risk_ids, *market_ids]
        if main_id is not None and main_id not in all_ids:
            all_ids.append(main_id)

        cards = self._load_cards(all_ids)
        cards_by_id = {card.decision_card_id: card for card in cards}
        missing_ids = [card_id for card_id in all_ids if card_id not in cards_by_id]
        if missing_ids:
            raise MorningBriefReadIntegrityError(
                f"MorningBrief ссылается на отсутствующие DecisionCard: "
                f"{', '.join(map(str, missing_ids))}"
            )

        foreign_cards = [
            card.decision_card_id
            for card in cards
            if card.agency_id != brief.agency_id
        ]
        if foreign_cards:
            raise MorningBriefReadIntegrityError(
                "Persisted DecisionCard принадлежит другому агентству: "
                + ", ".join(map(str, foreign_cards))
            )

        return MorningBriefReadResult(
            brief=brief,
            opportunity_cards=tuple(cards_by_id[card_id] for card_id in opportunity_ids),
            risk_cards=tuple(cards_by_id[card_id] for card_id in risk_ids),
            market_insight_cards=tuple(cards_by_id[card_id] for card_id in market_ids),
            main_decision_card=cards_by_id.get(main_id) if main_id is not None else None,
        )

    def list_history(
        self,
        agency_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[MorningBriefHistoryItem, ...]:
        """Возвращает страницу persisted history без загрузки DecisionCard."""
        if limit <= 0:
            raise ValueError("limit должен быть больше нуля")
        if offset < 0:
            raise ValueError("offset не может быть отрицательным")

        try:
            briefs = self.repository.list_briefs_by_agency(agency_id, limit, offset)
        except Exception as error:
            raise MorningBriefReadPersistenceError(
                "Не удалось прочитать историю MorningBrief"
            ) from error

        return tuple(
            MorningBriefHistoryItem(
                brief=brief,
                opportunity_count=len(brief.top_opportunity_card_ids),
                risk_count=len(brief.top_risk_card_ids),
                market_insight_count=len(brief.market_insight_card_ids),
                total_card_count=(
                    len(brief.top_opportunity_card_ids)
                    + len(brief.top_risk_card_ids)
                    + len(brief.market_insight_card_ids)
                ),
            )
            for brief in briefs
        )

    def _load_brief(self, brief_id: uuid.UUID) -> MorningBrief | None:
        try:
            return self.repository.get_brief_by_id(brief_id)
        except Exception as error:
            raise MorningBriefReadPersistenceError(
                "Не удалось прочитать MorningBrief"
            ) from error

    def _load_cards(self, card_ids: Sequence[uuid.UUID]) -> list[DecisionCard]:
        if not card_ids:
            return []
        try:
            return self.repository.load_decision_cards_by_ids_ordered(card_ids)
        except Exception as error:
            raise MorningBriefReadPersistenceError(
                "Не удалось прочитать DecisionCard"
            ) from error

    @staticmethod
    def _parse_ids(values: object, *, section: str) -> list[uuid.UUID]:
        if not isinstance(values, list):
            raise MorningBriefReadIntegrityError(
                f"{section} имеет некорректный persisted формат"
            )
        try:
            return [uuid.UUID(str(value)) for value in values]
        except (TypeError, ValueError) as error:
            raise MorningBriefReadIntegrityError(
                f"{section} содержит некорректный DecisionCard ID"
            ) from error