"""Чистые mapper-функции runtime брифа в исторические ORM-модели."""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any

from travel_revenue_ai.models.decision_card import DecisionCard as DecisionCardORM
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.schemas.persisted_morning_brief import (
    MorningBriefExecutionContext,
    PersistedMorningBriefRequest,
)
from travel_revenue_ai.services.decision_card_service import DecisionCard
from travel_revenue_ai.services.morning_brief_service import MorningBriefResult
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    NumericDecisionCardMappingError,
    PersistedMorningBriefMappingError,
)

_MONEY_QUANTUM = Decimal("0.01")
_MAX_MONEY = Decimal("999999999999.99")


@dataclass(frozen=True)
class MappedCard:
    """Явная связь runtime-карточки и ORM-карточки с её секцией и порядком."""

    runtime_card: DecisionCard
    orm_card: DecisionCardORM
    section: str
    ordinal: int


def json_safe(value: Any) -> Any:
    """Преобразует значение в рекурсивно JSON-совместимый snapshot."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    raise PersistedMorningBriefMappingError(
        f"Неподдерживаемое значение в JSON snapshot: {type(value).__name__}"
    )


def money_to_decimal(value: Any) -> Decimal:
    """Нормализует эффект в безопасный для Numeric(14,2) Decimal."""
    if isinstance(value, bool):
        raise NumericDecisionCardMappingError("Булево значение не является денежным эффектом")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise NumericDecisionCardMappingError("Некорректный денежный эффект") from error

    if not decimal_value.is_finite():
        raise NumericDecisionCardMappingError("Денежный эффект должен быть конечным")

    try:
        decimal_value = decimal_value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise NumericDecisionCardMappingError("Денежный эффект не приводится к масштабу 2") from error

    if abs(decimal_value) > _MAX_MONEY:
        raise NumericDecisionCardMappingError("Денежный эффект превышает Numeric(14,2)")
    return decimal_value


def map_runtime_card(
    runtime_card: DecisionCard,
    *,
    agency_id: uuid.UUID,
    money_effect_raw: Any,
) -> DecisionCardORM:
    """Создаёт ORM-карточку без доступа к Session или изменения runtime объекта."""
    if runtime_card.signal_id is None:
        raise PersistedMorningBriefMappingError("Runtime-карточка не содержит signal_id")

    confidence = float(runtime_card.confidence_raw)
    score = float(runtime_card.score)
    if not math.isfinite(confidence) or not math.isfinite(score):
        raise PersistedMorningBriefMappingError("Score и confidence должны быть конечными")

    return DecisionCardORM(
        agency_id=agency_id,
        signal_id=runtime_card.signal_id,
        card_type=runtime_card.card_type.value,
        title=runtime_card.title,
        summary=runtime_card.summary,
        why_it_matters=runtime_card.why_it_matters,
        what_to_do=runtime_card.what_to_do,
        deadline=runtime_card.deadline_display,
        money_effect_raw=money_to_decimal(money_effect_raw),
        currency="RUB",
        money_effect_display=runtime_card.money_effect_display,
        score=score,
        confidence=confidence,
        priority=runtime_card.priority_label.value,
        status=runtime_card.status_display.value,
        feedback_state=runtime_card.feedback_state,
        reasoning=runtime_card.reasoning_trace,
        score_breakdown=json_safe(
            {
                "breakdown": runtime_card.breakdown,
                "applicable_modifiers": runtime_card.applicable_modifiers,
                "filter_result": runtime_card.filter_result,
            }
        ),
        audit_metadata=json_safe(runtime_card.audit_metadata),
        generated_at=runtime_card.generated_at,
    )


def map_brief(
    runtime_brief: MorningBriefResult,
    *,
    request: PersistedMorningBriefRequest,
    context: MorningBriefExecutionContext,
    mapped_cards: list[MappedCard],
) -> MorningBrief:
    """Создаёт ORM MorningBrief из runtime брифа и уже flushed ORM-карточек."""
    section_cards = {
        section: [item for item in mapped_cards if item.section == section]
        for section in ("opportunities", "risks", "market_insights")
    }

    for cards in section_cards.values():
        if any(card.orm_card.decision_card_id is None for card in cards):
            raise PersistedMorningBriefMappingError("Карточки должны быть flushed до map_brief")

    main_item = next(
        (
            item
            for item in mapped_cards
            if runtime_brief.main_action is item.runtime_card
            or (
                runtime_brief.main_action is not None
                and runtime_brief.main_action.decision_card_id
                == item.runtime_card.decision_card_id
            )
        ),
        None,
    )
    if runtime_brief.main_action is not None and main_item is None:
        raise PersistedMorningBriefMappingError(
            "Главная runtime-карточка не найдена среди mapped cards"
        )

    main_snapshot = (
        json_safe(runtime_brief.main_action.to_display_dict())
        if runtime_brief.main_action is not None
        else None
    )
    feature_flags = {
        **json_safe(context.feature_flags),
        "request_fingerprint": request.fingerprint(),
    }

    return MorningBrief(
        agency_id=request.agency_id,
        date=request.brief_date,
        generated_at=runtime_brief.generated_at,
        main_decision_card_id=main_item.orm_card.decision_card_id if main_item else None,
        top_opportunity_card_ids=[
            str(item.orm_card.decision_card_id) for item in section_cards["opportunities"]
        ],
        top_risk_card_ids=[str(item.orm_card.decision_card_id) for item in section_cards["risks"]],
        market_insight_card_ids=[
            str(item.orm_card.decision_card_id) for item in section_cards["market_insights"]
        ],
        opportunities_snapshot=json_safe(
            [item.runtime_card.to_display_dict() for item in section_cards["opportunities"]]
        ),
        risks_snapshot=json_safe(
            [item.runtime_card.to_display_dict() for item in section_cards["risks"]]
        ),
        market_insights_snapshot=json_safe(
            [item.runtime_card.to_display_dict() for item in section_cards["market_insights"]]
        ),
        main_action_snapshot=main_snapshot,
        summary_text=runtime_brief.summary.full_text if runtime_brief.summary else "",
        summary_snapshot=json_safe(runtime_brief.summary) if runtime_brief.summary else {},
        statistics_snapshot=json_safe(
            {
                "total_cards_processed": runtime_brief.total_cards_processed,
                "opportunities_count": runtime_brief.opportunities_count,
                "risks_count": runtime_brief.risks_count,
                "market_insights_count": runtime_brief.market_insights_count,
            }
        ),
        input_signal_ids=[str(signal_id) for signal_id in request.signal_ids],
        execution_id=context.execution_id,
        trigger_type=request.trigger_type.value,
        request_id=request.request_id,
        scheduler_job_id=request.scheduler_job_id,
        idempotency_key=request.idempotency_key,
        feature_flags_snapshot=feature_flags,
        engine_version=context.engine_version,
        scoring_version=context.scoring_version,
        filtering_version=context.filtering_version,
        started_at=context.started_at,
        completed_at=context.completed_at,
    )