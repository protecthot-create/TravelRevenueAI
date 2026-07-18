"""Router для генерации утреннего брифа.

Реализует Sprint 3.4 — Morning Brief API.
Endpoint передаёт входные сигналы в PipelineService и возвращает
готовый MorningBriefResult без дублирования бизнес-логики.

Spec: docs/system_architecture.md, docs/data_model.md,
docs/decision_card_spec.md.
"""

import uuid
from typing import Any

from fastapi import APIRouter, status

from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.schemas.signal import SignalCreate
from travel_revenue_ai.services.pipeline_service import PipelineService

router = APIRouter(
    prefix="/morning-brief",
    tags=["morning-brief"],
)


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
    """Генерирует утренний бриф из переданных сигналов.

    Args:
        signals: Список входных сигналов в существующей Pydantic-схеме.

    Returns:
        Сериализованный MorningBriefResult.
    """
    pipeline_service = PipelineService()
    result = pipeline_service.generate_morning_brief(
        [_to_domain_signal(signal) for signal in signals]
    )
    return result.to_display_dict()