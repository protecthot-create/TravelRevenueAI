"""Router для CRUD операций с сигналами (Signal API).

Реализует Sprint 2.5 — Signal API + Sprint 2.6 — Service Layer Foundation.
- POST /signals — создание сигнала
- GET /signals/{signal_id} — получение сигнала по ID
- GET /signals — список сигналов с фильтрацией
- DELETE /signals/{signal_id} — удаление сигнала

Архитектура: API → Services → Models → Database

Spec: docs/data_model.md, docs/system_architecture.md
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from travel_revenue_ai.database import get_db
from travel_revenue_ai.models.signal import SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.schemas.signal import SignalCreate, SignalResponse
from travel_revenue_ai.services.signal_service import SignalService

router = APIRouter(
    prefix="/signals",
    tags=["signals"],
)


# =============================================================================
# Helper: конвертация ORM → Response
# =============================================================================

def _signal_to_response(signal: object) -> SignalResponse:
    """Преобразует ORM-модель Signal в Pydantic Response.

    Добавляет вычисляемые поля (is_processed, is_rejected и т.д.).
    """
    return SignalResponse(
        signal_id=signal.signal_id,
        agency_id=signal.agency_id,
        source_id=signal.source_id,
        signal_type=signal.signal_type,
        raw_data=signal.raw_data,
        status=signal.status,
        created_at=signal.created_at,
        updated_at=signal.updated_at,
        is_processed=signal.is_processed(),
        is_rejected=signal.is_rejected(),
        can_be_scored=signal.can_be_scored(),
        can_be_filtered=signal.can_be_filtered(),
    )


# =============================================================================
# POST /signals — Создание сигнала
# =============================================================================

@router.post(
    "",
    response_model=SignalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый сигнал",
    description="Создаёт сигнал из внешнего или внутреннего источника. "
                "Статус автоматически устанавливается в 'new'.",
)
def create_signal(
    data: SignalCreate,
    db: Annotated[Session, Depends(get_db)],
) -> SignalResponse:
    """Создаёт новый сигнал в системе.

    Args:
        data: Входные данные для создания сигнала.
        db: Сессия базы данных.

    Returns:
        Созданный сигнал с вычисляемыми полями.

    Raises:
        HTTPException 422: Если входные данные не прошли валидацию.
    """
    service = SignalService(db)
    signal = service.create_signal(
        agency_id=data.agency_id,
        source_id=data.source_id,
        signal_type=data.signal_type,
        raw_data=data.raw_data,
    )
    return _signal_to_response(signal)


# =============================================================================
# GET /signals/{signal_id} — Получение сигнала по ID
# =============================================================================

@router.get(
    "/{signal_id}",
    response_model=SignalResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить сигнал по ID",
    description="Возвращает сигнал по его уникальному идентификатору.",
)
def get_signal(
    signal_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> SignalResponse:
    """Возвращает сигнал по UUID.

    Args:
        signal_id: Уникальный идентификатор сигнала.
        db: Сессия базы данных.

    Returns:
        Найденный сигнал с вычисляемыми полями.

    Raises:
        HTTPException 404: Если сигнал не найден.
    """
    service = SignalService(db)
    signal = service.get_signal(signal_id)

    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Сигнал с id={signal_id} не найден",
        )

    return _signal_to_response(signal)


# =============================================================================
# GET /signals — Список сигналов с фильтрацией
# =============================================================================

@router.get(
    "",
    response_model=list[SignalResponse],
    status_code=status.HTTP_200_OK,
    summary="Список сигналов",
    description="Возвращает список сигналов с возможностью фильтрации "
                "по типу, статусу и агентству. Поддерживает пагинацию.",
)
def list_signals(
    db: Annotated[Session, Depends(get_db)],
    agency_id: uuid.UUID | None = Query(
        None,
        description="Фильтр по идентификатору агентства",
    ),
    signal_type: SignalTypeEnum | None = Query(
        None,
        description="Фильтр по типу сигнала",
    ),
    status: SignalStatusEnum | None = Query(
        None,
        description="Фильтр по статусу обработки",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Сколько записей пропустить (offset)",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Максимальное количество записей (limit)",
    ),
) -> list[SignalResponse]:
    """Возвращает список сигналов с фильтрацией и пагинацией.

    Args:
        db: Сессия базы данных.
        agency_id: Фильтр по агентству (опционально).
        signal_type: Фильтр по типу сигнала (опционально).
        status: Фильтр по статусу (опционально).
        skip: Смещение для пагинации.
        limit: Лимит записей на страницу.

    Returns:
        Список сигналов, соответствующих фильтрам.
    """
    service = SignalService(db)
    signals = service.list_signals(
        agency_id=agency_id,
        signal_type=signal_type,
        status=status,
        skip=skip,
        limit=limit,
    )
    return [_signal_to_response(s) for s in signals]


# =============================================================================
# DELETE /signals/{signal_id} — Удаление сигнала
# =============================================================================

@router.delete(
    "/{signal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сигнал",
    description="Удаляет сигнал по его идентификатору. Операция необратима.",
)
def delete_signal(
    signal_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Удаляет сигнал по UUID.

    Args:
        signal_id: Уникальный идентификатор сигнала.
        db: Сессия базы данных.

    Raises:
        HTTPException 404: Если сигнал не найден.
    """
    service = SignalService(db)
    signal = service.get_signal(signal_id)

    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Сигнал с id={signal_id} не найден",
        )

    service.delete_signal(signal)