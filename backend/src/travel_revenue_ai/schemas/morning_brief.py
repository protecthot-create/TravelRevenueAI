"""Pydantic-схемы для модели MorningBrief.

MorningBriefCreate — входные данные для создания утреннего брифа.
MorningBriefResponse — данные для ответа API.

Spec: docs/data_model.md, секция 5.
"""

import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from travel_revenue_ai.models.morning_brief import MorningBriefStatusEnum


class MorningBriefCreate(BaseModel):
    """Схема для создания Morning Brief."""

    model_config = ConfigDict(
        from_attributes=True,
        strict=True,
        use_enum_values=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat(),
        },
    )

    agency_id: uuid.UUID = Field(
        ...,
        description="Идентификатор агентства-владельца",
        examples=[uuid.UUID("12345678-1234-5678-1234-567812345678")],
    )

    date: date_type = Field(
        ...,
        description="Дата брифа",
        examples=[date_type(2026, 7, 16)],
    )

    top_opportunities: list[uuid.UUID] = Field(
        default_factory=list,
        description="Список UUID Decision Card с топ-возможностями (не более 5)",
        examples=[[uuid.UUID("11111111-1111-1111-1111-111111111111")]],
    )

    top_risks: list[uuid.UUID] = Field(
        default_factory=list,
        description="Список UUID Decision Card с топ-рисками (не более 3)",
        examples=[[uuid.UUID("22222222-2222-2222-2222-222222222222")]],
    )

    main_action_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID главного действия дня",
        examples=[uuid.UUID("33333333-3333-3333-3333-333333333333")],
    )

    summary_text: str = Field(
        ...,
        min_length=1,
        description="Краткий текст брифа для отображения",
        examples=["Сегодня важно отправить рассылку и пересчитать маржу по Египту."],
    )

    status: MorningBriefStatusEnum = Field(
        default=MorningBriefStatusEnum.draft,
        description="Статус брифа: draft / sent / read",
        examples=[MorningBriefStatusEnum.draft.value],
    )

    @field_validator("top_opportunities", mode="before")
    @classmethod
    def validate_top_opportunities(
        cls, value: Any
    ) -> list[uuid.UUID]:
        """Проверяет список топ-возможностей и приводит значения к UUID."""
        return cls._validate_uuid_list(value, "top_opportunities", max_items=5)

    @field_validator("top_risks", mode="before")
    @classmethod
    def validate_top_risks(
        cls, value: Any
    ) -> list[uuid.UUID]:
        """Проверяет список топ-рисков и приводит значения к UUID."""
        return cls._validate_uuid_list(value, "top_risks", max_items=3)

    @field_validator("summary_text")
    @classmethod
    def validate_summary_text(cls, value: str) -> str:
        """Проверяет, что summary_text не пустой."""
        if not isinstance(value, str):
            raise ValueError("summary_text должен быть строкой")
        if len(value.strip()) == 0:
            raise ValueError("summary_text не может быть пустым")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(
        cls, value: str | MorningBriefStatusEnum
    ) -> MorningBriefStatusEnum:
        """Принимает строку или enum и возвращает валидный MorningBriefStatusEnum."""
        if isinstance(value, str):
            try:
                return MorningBriefStatusEnum(value)
            except ValueError as error:
                allowed = [enum_value.value for enum_value in MorningBriefStatusEnum]
                raise ValueError(
                    f"Недопустимый статус брифа: '{value}'. Допустимые: {allowed}"
                ) from error
        return value

    @staticmethod
    def _validate_uuid_list(
        value: Any,
        field_name: str,
        max_items: int,
    ) -> list[uuid.UUID]:
        """Валидирует список UUID и ограничивает его длину."""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{field_name} должен быть списком")

        result: list[uuid.UUID] = []
        for item in value:
            if isinstance(item, uuid.UUID):
                result.append(item)
                continue
            if isinstance(item, str):
                try:
                    result.append(uuid.UUID(item))
                except ValueError as error:
                    raise ValueError(
                        f"Недопустимый UUID в {field_name}: '{item}'"
                    ) from error
                continue
            raise ValueError(
                f"Элемент {field_name} должен быть UUID или строкой, "
                f"получен {type(item).__name__}"
            )

        if len(result) > max_items:
            raise ValueError(f"{field_name} не может содержать более {max_items} элементов")
        return result


class MorningBriefResponse(BaseModel):
    """Схема ответа API с данными Morning Brief."""

    model_config = ConfigDict(
        from_attributes=True,
        strict=True,
        use_enum_values=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat(),
        },
    )

    brief_id: uuid.UUID = Field(
        ...,
        description="Уникальный идентификатор брифа",
    )

    agency_id: uuid.UUID = Field(
        ...,
        description="Идентификатор агентства-владельца",
    )

    date: date_type = Field(
        ...,
        description="Дата брифа",
    )

    top_opportunities: list[uuid.UUID] = Field(
        default_factory=list,
        description="Список UUID Decision Card с топ-возможностями",
    )

    top_risks: list[uuid.UUID] = Field(
        default_factory=list,
        description="Список UUID Decision Card с топ-рисками",
    )

    main_action_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID главного действия дня",
    )

    summary_text: str = Field(
        ...,
        description="Краткий текст брифа для отображения",
    )

    status: MorningBriefStatusEnum = Field(
        ...,
        description="Статус брифа: draft / sent / read",
    )

    created_at: datetime = Field(
        ...,
        description="Дата и время создания",
    )

    sent_at: Optional[datetime] = Field(
        default=None,
        description="Дата и время отправки",
    )

    @field_validator("top_opportunities", mode="before")
    @classmethod
    def validate_top_opportunities(
        cls, value: Any
    ) -> list[uuid.UUID]:
        """Проверяет список топ-возможностей и приводит значения к UUID."""
        return MorningBriefCreate._validate_uuid_list(value, "top_opportunities", max_items=5)

    @field_validator("top_risks", mode="before")
    @classmethod
    def validate_top_risks(
        cls, value: Any
    ) -> list[uuid.UUID]:
        """Проверяет список топ-рисков и приводит значения к UUID."""
        return MorningBriefCreate._validate_uuid_list(value, "top_risks", max_items=3)

    @field_validator("summary_text")
    @classmethod
    def validate_summary_text(cls, value: str) -> str:
        """Проверяет, что summary_text не пустой."""
        if not isinstance(value, str):
            raise ValueError("summary_text должен быть строкой")
        if len(value.strip()) == 0:
            raise ValueError("summary_text не может быть пустым")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(
        cls, value: str | MorningBriefStatusEnum
    ) -> MorningBriefStatusEnum:
        """Принимает строку или enum и возвращает валидный MorningBriefStatusEnum."""
        if isinstance(value, str):
            try:
                return MorningBriefStatusEnum(value)
            except ValueError as error:
                allowed = [enum_value.value for enum_value in MorningBriefStatusEnum]
                raise ValueError(
                    f"Недопустимый статус брифа: '{value}'. Допустимые: {allowed}"
                ) from error
        return value

    @field_validator("created_at", "sent_at", mode="before")
    @classmethod
    def ensure_timezone_aware(
        cls, value: Optional[datetime]
    ) -> Optional[datetime]:
        """Гарантирует, что datetime содержит timezone-информацию."""
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)
