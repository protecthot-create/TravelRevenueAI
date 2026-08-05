"""Router для preview и persisted-генерации утреннего брифа.

Preview endpoint сохраняет исходное поведение: принимает transient signals и
возвращает runtime-представление PipelineService. Persisted endpoint является
тонкой HTTP-границей над PersistedMorningBriefService.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from travel_revenue_ai.composition import (
    build_persisted_morning_brief_service,
    build_pipeline_service,
)
from travel_revenue_ai.database import get_db
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.schemas.decision_card_feedback import (
    DecisionCardFeedbackRequest,
    DecisionCardFeedbackResponse,
)
from travel_revenue_ai.schemas.persisted_morning_brief import (
    BriefTriggerType,
    PersistedMorningBriefRequest,
    PersistedMorningBriefResult,
)
from travel_revenue_ai.schemas.signal import SignalCreate
from travel_revenue_ai.services.decision_card_feedback_service import (
    DecisionCardFeedbackNotFoundError,
    DecisionCardFeedbackService,
)
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    BusinessDateConflictError,
    DuplicateSignalIdsError,
    IdempotencyConflictError,
    InvalidPersistedMorningBriefRequest,
    PersistedMorningBriefMappingError,
    PersistenceError,
    PipelineExecutionError,
    SignalAgencyOwnershipError,
    SignalNotFoundError,
)

router = APIRouter(
    prefix="/morning-brief",
    tags=["morning-brief"],
)

decision_cards_router = APIRouter(tags=["decision-cards"])


class PersistedMorningBriefCreateDTO(BaseModel):
    """HTTP-команда для сохранения исторического утреннего брифа."""

    agency_id: UUID
    brief_date: date
    signal_ids: list[UUID] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    trigger_type: BriefTriggerType
    request_id: str | None = None
    scheduler_job_id: str | None = None


class PersistedDecisionCardGroupDTO(BaseModel):
    """Упорядоченный набор карточек одной категории persisted-брифа."""

    category: Literal["opportunities", "risks", "market_insights"]
    decision_card_ids: list[UUID]


class PersistedMorningBriefResponseDTO(BaseModel):
    """Стабильное публичное представление persisted-брифа."""

    brief_id: UUID
    brief_date: date
    decision_card_groups: list[PersistedDecisionCardGroupDTO]
    main_decision_card_id: UUID | None
    replayed: bool


def _to_domain_signal(data: SignalCreate) -> Signal:
    """Преобразует входную API-схему в временный доменный Signal.

    Сигнал не сохраняется в базе данных: endpoint генерирует бриф
    из переданного списка и передаёт его в PipelineService.
    """
    return Signal(
        signal_id=uuid.uuid4(),
        agency_id=data.agency_id,
        source_id=data.source_id,
        signal_type=data.signal_type,
        raw_data=data.raw_data,
    )


def _to_persisted_request(
    payload: PersistedMorningBriefCreateDTO,
) -> PersistedMorningBriefRequest:
    """Преобразует валидный HTTP DTO в application command."""
    return PersistedMorningBriefRequest(
        agency_id=payload.agency_id,
        brief_date=payload.brief_date,
        signal_ids=tuple(payload.signal_ids),
        idempotency_key=payload.idempotency_key,
        trigger_type=payload.trigger_type,
        request_id=payload.request_id,
        scheduler_job_id=payload.scheduler_job_id,
    )


def _to_persisted_response(
    result: PersistedMorningBriefResult,
) -> PersistedMorningBriefResponseDTO:
    """Строит публичный ответ только из стабильного application result."""
    return PersistedMorningBriefResponseDTO(
        brief_id=result.brief_id,
        brief_date=result.brief_date,
        decision_card_groups=[
            PersistedDecisionCardGroupDTO(
                category="opportunities",
                decision_card_ids=list(result.opportunity_card_ids),
            ),
            PersistedDecisionCardGroupDTO(
                category="risks",
                decision_card_ids=list(result.risk_card_ids),
            ),
            PersistedDecisionCardGroupDTO(
                category="market_insights",
                decision_card_ids=list(result.market_insight_card_ids),
            ),
        ],
        main_decision_card_id=result.main_decision_card_id,
        replayed=result.replayed,
    )


def _raise_persisted_http_error(error: Exception) -> None:
    """Преобразует известные application errors в стабильные HTTP-ответы."""
    if isinstance(error, DuplicateSignalIdsError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duplicate_signal_ids")
    if isinstance(error, SignalNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")
    if isinstance(
        error,
        (
            SignalAgencyOwnershipError,
            IdempotencyConflictError,
            BusinessDateConflictError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="persisted_brief_conflict")
    if isinstance(
        error,
        (InvalidPersistedMorningBriefRequest, PersistedMorningBriefMappingError),
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="persisted_brief_contract_rejected",
        )
    if isinstance(error, (PipelineExecutionError, PersistenceError)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="persisted_brief_unavailable",
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="internal_server_error",
    )


def _raise_decision_card_feedback_http_error(error: Exception) -> None:
    """Преобразует ошибки feedback use case в стабильные HTTP-ответы."""
    if isinstance(error, DecisionCardFeedbackNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="decision_card_not_found",
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="internal_server_error",
    )


@router.post(
    "/generate",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Сгенерировать утренний бриф",
    description=(
        "Принимает список Signal, запускает полный конвейер "
        "PipelineService и возвращает готовый MorningBriefResult."
    ),
)
def generate_morning_brief(signals: list[SignalCreate]) -> dict[str, Any]:
    """Генерирует утренний бриф из переданных сигналов."""
    pipeline_service = build_pipeline_service()
    result = pipeline_service.generate_morning_brief(
        [_to_domain_signal(signal) for signal in signals]
    )
    return result.to_display_dict()


@router.post(
    "/persisted",
    response_model=PersistedMorningBriefResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Создать persisted утренний бриф",
)
def create_persisted_morning_brief(
    payload: PersistedMorningBriefCreateDTO,
    db: Session = Depends(get_db),
) -> PersistedMorningBriefResponseDTO:
    """Вызывает persisted use case без копирования бизнес-логики."""
    service = build_persisted_morning_brief_service(db)
    try:
        result = service.generate(_to_persisted_request(payload))
    except Exception as error:
        _raise_persisted_http_error(error)
        raise AssertionError("Недостижимый код")
    return _to_persisted_response(result)


@decision_cards_router.post(
    "/decision-cards/{decision_card_id}/feedback",
    response_model=DecisionCardFeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Сохранить feedback по persisted decision card",
)
def save_decision_card_feedback(
    decision_card_id: UUID,
    payload: DecisionCardFeedbackRequest,
    db: Session = Depends(get_db),
) -> DecisionCardFeedbackResponse:
    """Сохраняет MVP feedback, изменяя только существующие lifecycle-поля."""
    service = DecisionCardFeedbackService(db)
    try:
        result = service.apply_feedback(
            decision_card_id=decision_card_id,
            feedback_state=payload.feedback_state,
        )
    except Exception as error:
        _raise_decision_card_feedback_http_error(error)
        raise AssertionError("Недостижимый код")
    return DecisionCardFeedbackResponse(
        decision_card_id=result.decision_card_id,
        status=result.status,
        feedback_state=result.feedback_state,
        updated_at=result.updated_at,
    )
