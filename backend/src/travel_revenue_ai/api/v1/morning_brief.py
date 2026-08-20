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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from travel_revenue_ai.composition import (
    build_morning_brief_read_service,
    build_persisted_morning_brief_service,
    build_pipeline_service,
)
from travel_revenue_ai.database import get_db
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.schemas.decision_card_feedback import (
    DecisionCardFeedbackRequest,
    DecisionCardFeedbackResponse,
)
from travel_revenue_ai.schemas.morning_brief_read import (
    MorningBriefDecisionCardDTO,
    MorningBriefHistoryItemDTO,
    MorningBriefReadDTO,
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
from travel_revenue_ai.services.morning_brief_read_errors import (
    MorningBriefReadIntegrityError,
    MorningBriefReadNotFoundError,
    MorningBriefReadPersistenceError,
)
from travel_revenue_ai.services.morning_brief_read_service import (
    MorningBriefHistoryItem,
    MorningBriefReadResult,
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
morning_brief_history_router = APIRouter(tags=["morning-brief"])


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


def _to_read_card(card: DecisionCard) -> MorningBriefDecisionCardDTO:
    """Преобразует persisted карточку в разрешённый публичный DTO."""
    return MorningBriefDecisionCardDTO(
        decision_card_id=card.decision_card_id,
        card_type=card.card_type,
        title=card.title,
        summary=card.summary,
        why_it_matters=card.why_it_matters,
        what_to_do=card.what_to_do,
        deadline=card.deadline,
        money_effect_display=card.money_effect_display,
        score=card.score,
        confidence=card.confidence,
        priority=card.priority,
        status=card.status,
        feedback_state=card.feedback_state,
    )


def _to_read_response(result: MorningBriefReadResult) -> MorningBriefReadDTO:
    """Строит публичный DTO брифа, сохраняя порядок карточек сервиса."""
    brief = result.brief
    return MorningBriefReadDTO(
        brief_id=brief.brief_id,
        agency_id=brief.agency_id,
        brief_date=brief.date,
        generated_at=brief.generated_at,
        status=brief.status.value,
        summary_text=brief.summary_text,
        opportunity_cards=[_to_read_card(card) for card in result.opportunity_cards],
        risk_cards=[_to_read_card(card) for card in result.risk_cards],
        market_insight_cards=[_to_read_card(card) for card in result.market_insight_cards],
        main_decision_card=(
            _to_read_card(result.main_decision_card)
            if result.main_decision_card is not None
            else None
        ),
    )


def _to_history_response(item: MorningBriefHistoryItem) -> MorningBriefHistoryItemDTO:
    """Строит публичный metadata-only DTO исторической записи."""
    brief = item.brief
    return MorningBriefHistoryItemDTO(
        brief_id=brief.brief_id,
        brief_date=brief.date,
        generated_at=brief.generated_at,
        status=brief.status.value,
        summary_text=brief.summary_text,
        opportunity_count=item.opportunity_count,
        risk_count=item.risk_count,
        market_insight_count=item.market_insight_count,
        total_card_count=item.total_card_count,
    )


def _raise_morning_brief_read_http_error(error: Exception) -> None:
    """Преобразует typed read errors в стабильные и безопасные HTTP-ответы."""
    if isinstance(error, MorningBriefReadNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="morning_brief_not_found",
        )
    if isinstance(error, MorningBriefReadIntegrityError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="morning_brief_integrity_error",
        )
    if isinstance(error, MorningBriefReadPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="morning_brief_unavailable",
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


@router.get(
    "/{brief_id}",
    response_model=MorningBriefReadDTO,
    status_code=status.HTTP_200_OK,
    summary="Получить persisted утренний бриф",
)
def get_persisted_morning_brief(
    brief_id: UUID,
    agency_id: UUID = Query(description="Идентификатор агентства-владельца"),
    db: Session = Depends(get_db),
) -> MorningBriefReadDTO:
    """Возвращает persisted бриф только владельцу, не изменяя состояние базы."""
    service = build_morning_brief_read_service(db)
    try:
        result = service.get_brief(brief_id=brief_id, agency_id=agency_id)
    except Exception as error:
        _raise_morning_brief_read_http_error(error)
        raise AssertionError("Недостижимый код")
    return _to_read_response(result)


@morning_brief_history_router.get(
    "/agencies/{agency_id}/morning-briefs",
    response_model=list[MorningBriefHistoryItemDTO],
    status_code=status.HTTP_200_OK,
    summary="Получить историю persisted утренних брифов",
)
def list_persisted_morning_brief_history(
    agency_id: UUID,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Максимальное количество брифов в ответе",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Количество брифов, которые нужно пропустить",
    ),
    db: Session = Depends(get_db),
) -> list[MorningBriefHistoryItemDTO]:
    """Возвращает metadata-only историю агентства без загрузки DecisionCard."""
    service = build_morning_brief_read_service(db)
    try:
        items = service.list_history(agency_id=agency_id, limit=limit, offset=offset)
    except Exception as error:
        _raise_morning_brief_read_http_error(error)
        raise AssertionError("Недостижимый код")
    return [_to_history_response(item) for item in items]


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
