"""Pydantic-схемы для модели Signal.

SignalCreate — входные данные для создания сигнала.
SignalResponse — выходные данные для ответа API.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from travel_revenue_ai.models.signal import SignalStatusEnum, SignalTypeEnum


class SignalCreate(BaseModel):
    """Схема для создания нового сигнала.

    Используется в POST /signals как тело запроса.
    Поля `status`, `created_at`, `updated_at` не включаются —
    они назначаются автоматически на уровне модели.
    """

    model_config = ConfigDict(
        # Разрешаем создание из атрибутов ORM-модели
        from_attributes=True,
        # Строгая проверка типов
        strict=True,
        # Используем enum values вместо объектов при сериализации
        use_enum_values=True,
    )

    agency_id: uuid.UUID = Field(
        ...,
        description="Идентификатор агентства-владельца сигнала",
        examples=[uuid.UUID("12345678-1234-5678-1234-567812345678")],
    )

    source_id: uuid.UUID = Field(
        ...,
        description="Идентификатор источника данных",
        examples=[uuid.UUID("87654321-4321-8765-4321-876543218765")],
    )

    signal_type: SignalTypeEnum = Field(
        ...,
        description="Тип сигнала: opportunity / risk / market / operational",
        examples=["opportunity", "risk"],
    )

    raw_data: dict[str, Any] = Field(
        ...,
        description="Сырые данные сигнала в JSON-формате",
        examples=[{"event": "price_drop", "destination": "Turkey", "change_percent": -15}],
    )

    @field_validator("raw_data")
    @classmethod
    def validate_raw_data_not_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Проверяет, что raw_data является непустым JSON-объектом."""
        if not isinstance(value, dict):
            raise ValueError("raw_data должен быть JSON-объектом (dict)")
        if len(value) == 0:
            raise ValueError("raw_data не может быть пустым объектом")
        return value

    @field_validator("signal_type", mode="before")
    @classmethod
    def validate_signal_type_input(cls, value: str | SignalTypeEnum) -> SignalTypeEnum:
        """Принимает строку или enum и возвращает валидный SignalTypeEnum."""
        if isinstance(value, str):
            try:
                return SignalTypeEnum(value)
            except ValueError as error:
                allowed = [e.value for e in SignalTypeEnum]
                raise ValueError(
                    f"Недопустимый тип сигнала: '{value}'. Допустимые: {allowed}"
                ) from error
        return value


class SignalResponse(BaseModel):
    """Схема для ответа API с данными сигнала.

    Используется в GET /signals/{id}, POST /signals и других эндпоинтах.
    Включает все поля модели + вычисляемые флаги.
    """

    model_config = ConfigDict(
        from_attributes=True,
        strict=True,
        use_enum_values=True,
        # Сериализуем datetime в ISO-формат с timezone
        json_encoders={
            datetime: lambda dt: dt.isoformat(),
        },
    )

    signal_id: uuid.UUID = Field(
        ...,
        description="Уникальный идентификатор сигнала",
        examples=[uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")],
    )

    agency_id: uuid.UUID = Field(
        ...,
        description="Идентификатор агентства-владельца",
    )

    source_id: uuid.UUID = Field(
        ...,
        description="Идентификатор источника данных",
    )

    signal_type: SignalTypeEnum = Field(
        ...,
        description="Тип сигнала",
    )

    raw_data: dict[str, Any] = Field(
        ...,
        description="Сырые данные сигнала",
    )

    status: SignalStatusEnum = Field(
        ...,
        description="Текущий статус обработки: new / normalized / scored / filtered / rejected",
    )

    created_at: datetime = Field(
        ...,
        description="Дата и время поступления сигнала (UTC)",
    )

    updated_at: datetime = Field(
        ...,
        description="Дата и время последнего обновления (UTC)",
    )

    # Вычисляемые поля (не хранятся в БД, добавляются при сериализации)
    is_processed: bool = Field(
        ...,
        description="Прошёл ли сигнал полную обработку (filtered или rejected)",
    )

    is_rejected: bool = Field(
        ...,
        description="Был ли сигнал отклонён",
    )

    can_be_scored: bool = Field(
        ...,
        description="Готов ли сигнал для оценки scoring engine (status == normalized)",
    )

    can_be_filtered: bool = Field(
        ...,
        description="Готов ли сигнал для фильтрации (status == scored)",
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_status_input(cls, value: str | SignalStatusEnum) -> SignalStatusEnum:
        """Принимает строку или enum и возвращает валидный SignalStatusEnum."""
        if isinstance(value, str):
            try:
                return SignalStatusEnum(value)
            except ValueError as error:
                allowed = [e.value for e in SignalStatusEnum]
                raise ValueError(
                    f"Недопустимый статус: '{value}'. Допустимые: {allowed}"
                ) from error
        return value

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        """Гарантирует, что datetime содержит timezone-информацию."""
        if value.tzinfo is None:
            # Если timezone отсутствует, считаем что это UTC
            return value.replace(tzinfo=datetime.timezone.utc)
        return value