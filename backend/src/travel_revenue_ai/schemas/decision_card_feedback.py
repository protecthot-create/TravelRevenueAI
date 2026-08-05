"""DTO для MVP feedback persisted DecisionCard."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class DecisionCardFeedbackState(str, Enum):
    """Разрешённые значения feedback_state для MVP CS5."""

    accepted = "accepted"
    dismissed = "dismissed"
    completed = "completed"


class DecisionCardFeedbackRequest(BaseModel):
    """Публичный DTO запроса feedback без доменной логики."""

    model_config = ConfigDict(extra="forbid")

    feedback_state: DecisionCardFeedbackState


class DecisionCardFeedbackResponse(BaseModel):
    """Минимальный DTO ответа после сохранения feedback."""

    decision_card_id: uuid.UUID
    status: str
    feedback_state: DecisionCardFeedbackState
    updated_at: datetime