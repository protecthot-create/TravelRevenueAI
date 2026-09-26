"""Публичные DTO первичного onboarding provisioning."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class OnboardingResponseDTO(BaseModel):
    """Минимальный публичный результат tenant provisioning."""

    app_user_id: UUID
    agency_id: UUID
    role: str
    replayed: bool
