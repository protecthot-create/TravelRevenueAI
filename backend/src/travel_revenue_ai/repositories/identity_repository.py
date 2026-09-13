"""Read-only repository для разрешения внешней identity в AppUser."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_revenue_ai.models.app_user import AppUser
from travel_revenue_ai.models.external_identity import ExternalIdentity
from travel_revenue_ai.security.principal import Principal


class IdentityRepository:
    """Выполняет только чтение identity и связанного AppUser."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def find_external_identity(self, principal: Principal) -> ExternalIdentity | None:
        """Находит identity строго по паре issuer и subject из Principal."""
        statement = select(ExternalIdentity).where(
            ExternalIdentity.external_issuer == principal.issuer,
            ExternalIdentity.external_subject == principal.subject_id,
        )
        return self.session.scalar(statement)

    def get_app_user_by_id(self, app_user_id: uuid.UUID) -> AppUser | None:
        """Возвращает внутреннего пользователя по идентификатору из identity."""
        return self.session.get(AppUser, app_user_id)
