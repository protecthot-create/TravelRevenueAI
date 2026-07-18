"""Pydantic-схемы конфигурации и публичного API источников данных."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from travel_revenue_ai.models.data_source import DataSourceTypeEnum, SyncStatusEnum
from travel_revenue_ai.services.source_health_service import SourceHealthStatusEnum


class DataSourceConfig(BaseModel):
    """Внутренняя независимая от транспорта конфигурация источника данных."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    source_id: uuid.UUID | None = Field(
        default=None,
        description="Идентификатор источника; отсутствует до сохранения ORM-модели",
    )
    agency_id: uuid.UUID
    source_name: str = Field(min_length=1, max_length=120)
    source_type: DataSourceTypeEnum
    enabled: bool = True
    credentials: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    last_sync: datetime | None = None
    sync_status: SyncStatusEnum = SyncStatusEnum.never_synced
    last_error: str | None = None


class DataSourceCreate(BaseModel):
    """Входные данные для создания источника.

    Credentials принимаются только на запись и никогда не возвращаются API.
    """

    agency_id: uuid.UUID
    source_name: str = Field(min_length=1, max_length=120)
    source_type: DataSourceTypeEnum
    enabled: bool = True
    credentials: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class DataSourceUpdate(BaseModel):
    """Изменяемые поля источника.

    Отсутствующие credentials сохраняют текущие значения; переданный пустой
    объект намеренно очищает credentials.
    """

    source_name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    credentials: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None


class DataSourceResponse(BaseModel):
    """Безопасное публичное представление источника без секретов."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    source_id: uuid.UUID
    agency_id: uuid.UUID
    source_name: str
    source_type: DataSourceTypeEnum
    enabled: bool
    settings: dict[str, Any]
    last_sync: datetime | None
    sync_status: SyncStatusEnum
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class SourceHealthResponse(BaseModel):
    """Публичное health-состояние одного источника без конфигурации и секретов."""

    source: DataSourceResponse
    status: SourceHealthStatusEnum
    last_sync: datetime | None
    last_error: str | None
    enabled: bool


class SourceConnectionTestResponse(BaseModel):
    """Результат ручной проверки подключения источника."""

    source: DataSourceResponse
    status: SyncStatusEnum
    last_sync: datetime
    last_error: str | None