"""API управления конфигурациями и состоянием источников данных."""

from datetime import date
import uuid
from typing import Annotated

from travel_revenue_ai.composition import build_source_collection_service
from travel_revenue_ai.schemas.persisted_morning_brief import BriefTriggerType

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from travel_revenue_ai.database import get_db
from travel_revenue_ai.schemas.data_source import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    SourceConnectionTestResponse,
    SourceHealthResponse,
)
from travel_revenue_ai.services.data_source_service import DataSourceService
from travel_revenue_ai.services.source_health_service import SourceHealthService

router = APIRouter(prefix="/sources", tags=["sources"])


def _to_response(source: object) -> DataSourceResponse:
    """Преобразует ORM-объект в публичный ответ без credentials."""
    return DataSourceResponse.model_validate(source)


def _get_required_source(
    service: DataSourceService,
    source_id: uuid.UUID,
) -> object:
    """Возвращает источник или единообразную ошибку 404."""
    source = service.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Источник с id={source_id} не найден",
        )
    return source


@router.get(
    "/health",
    response_model=list[SourceHealthResponse],
    summary="Получить health-статусы источников",
)
def list_source_health(
    db: Annotated[Session, Depends(get_db)],
    agency_id: uuid.UUID | None = Query(default=None),
) -> list[SourceHealthResponse]:
    """Возвращает безопасное health-состояние всех доступных источников."""
    source_service = DataSourceService(db)
    health_service = SourceHealthService()
    sources = source_service.list_sources(agency_id=agency_id)
    return [
        SourceHealthResponse(
            source=_to_response(source),
            status=health_service.get_status(source),
            last_sync=source.last_sync,
            last_error=source.last_error,
            enabled=source.enabled,
        )
        for source in sources
    ]


@router.get("", response_model=list[DataSourceResponse], summary="Список источников")
def list_sources(
    db: Annotated[Session, Depends(get_db)],
    agency_id: uuid.UUID | None = Query(default=None),
) -> list[DataSourceResponse]:
    """Возвращает список источников без паролей, tokens и IMAP credentials."""
    sources = DataSourceService(db).list_sources(agency_id=agency_id)
    return [_to_response(source) for source in sources]


@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать источник",
)
def create_source(
    data: DataSourceCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceResponse:
    """Сохраняет конфигурацию источника; секреты не попадают в ответ."""
    return _to_response(DataSourceService(db).create_source(data))


@router.post(
    "/collect",
    summary="Запустить ручной сбор источников и формирование брифов",
)
def collect_sources(
    db: Annotated[Session, Depends(get_db)],
    brief_date: date | None = Query(default=None),
    run_id: str | None = Query(default=None, max_length=128),
) -> dict[str, object]:
    """Собирает enabled-источники и возвращает только безопасную сводку запуска."""
    result = build_source_collection_service(db).collect_and_generate_morning_brief(
        brief_date=brief_date,
        trigger_type=BriefTriggerType.manual,
        run_id=run_id,
    )
    return {
        "collected_count": result.collected_count,
        "saved_count": result.saved_count,
        "errors_count": result.errors_count,
        "persisted_brief_agency_ids": [
            str(agency_id) for agency_id in result.persisted_briefs
        ],
    }


@router.get(
    "/{source_id}",
    response_model=DataSourceResponse,
    summary="Получить источник",
)
def get_source(
    source_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceResponse:
    """Возвращает публичную конфигурацию одного источника."""
    service = DataSourceService(db)
    return _to_response(_get_required_source(service, source_id))


@router.put(
    "/{source_id}",
    response_model=DataSourceResponse,
    summary="Изменить источник",
)
def update_source(
    source_id: uuid.UUID,
    data: DataSourceUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceResponse:
    """Обновляет разрешённые поля источника."""
    service = DataSourceService(db)
    source = _get_required_source(service, source_id)
    return _to_response(service.update_source(source, data))


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить источник",
)
def delete_source(
    source_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Удаляет источник данных."""
    service = DataSourceService(db)
    service.delete_source(_get_required_source(service, source_id))


@router.post(
    "/{source_id}/test",
    response_model=SourceConnectionTestResponse,
    summary="Проверить подключение источника",
)
def test_source_connection(
    source_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> SourceConnectionTestResponse:
    """Проверяет IMAP/mock подключение и сохраняет только безопасный результат."""
    service = DataSourceService(db)
    source = service.test_connection(_get_required_source(service, source_id))
    return SourceConnectionTestResponse(
        source=_to_response(source),
        status=source.sync_status,
        last_sync=source.last_sync,
        last_error=source.last_error,
    )