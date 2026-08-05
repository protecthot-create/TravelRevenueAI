"""MVP-сервис сохранения feedback для persisted DecisionCard."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.repositories.morning_brief_repository import MorningBriefRepository
from travel_revenue_ai.schemas.decision_card_feedback import DecisionCardFeedbackState


class DecisionCardFeedbackNotFoundError(Exception):
    """Карточка не найдена."""


@dataclass(frozen=True)
class DecisionCardFeedbackResult:
    """Результат применения feedback к persisted карточке."""

    decision_card_id: uuid.UUID
    status: str
    feedback_state: str
    updated_at: object


class DecisionCardFeedbackService:
    """Владеет транзакцией feedback change set для persisted DecisionCard."""

    _STATUS_BY_FEEDBACK: dict[DecisionCardFeedbackState, str] = {
        DecisionCardFeedbackState.accepted: "active",
        DecisionCardFeedbackState.dismissed: "dismissed",
        DecisionCardFeedbackState.completed: "done",
    }

    def __init__(
        self,
        session: Session,
        repository: MorningBriefRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or MorningBriefRepository(session)

    def apply_feedback(
        self,
        *,
        decision_card_id: uuid.UUID,
        feedback_state: DecisionCardFeedbackState,
    ) -> DecisionCardFeedbackResult:
        """Обновляет только lifecycle-поля карточки и фиксирует их одной транзакцией."""
        try:
            card = self.repository.get_decision_card_by_id(decision_card_id)
            if card is None:
                raise DecisionCardFeedbackNotFoundError(str(decision_card_id))

            self._apply_lifecycle_feedback(card, feedback_state)
            self.repository.flush()

            result = DecisionCardFeedbackResult(
                decision_card_id=card.decision_card_id,
                status=card.status,
                feedback_state=card.feedback_state,
                updated_at=card.updated_at,
            )
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    def _apply_lifecycle_feedback(
        self,
        card: DecisionCard,
        feedback_state: DecisionCardFeedbackState,
    ) -> None:
        """Применяет MVP mapping без изменения recommendation content."""
        card.feedback_state = feedback_state.value
        card.status = self._STATUS_BY_FEEDBACK[feedback_state]