"""Immutable tenant context после проверки identity и membership."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Минимальный контекст разрешённого агентства текущего пользователя."""

    app_user_id: UUID
    agency_id: UUID
    role: str
