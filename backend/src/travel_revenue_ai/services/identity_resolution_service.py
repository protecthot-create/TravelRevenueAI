"""Read-only сервис разрешения Principal в канонический AppUser."""

from __future__ import annotations

from sqlalchemy.orm import Session

from travel_revenue_ai.models.app_user import AppUser
from travel_revenue_ai.repositories.identity_repository import IdentityRepository
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.identity_resolution_errors import (
    IdentityResolutionInactiveUserError,
    IdentityResolutionIntegrityError,
    IdentityResolutionNotFoundError,
    IdentityResolutionPersistenceError,
)


class IdentityResolutionService:
    """Разрешает подтверждённый Principal без загрузки membership или авторизации."""

    def __init__(
        self,
        *,
        repository: IdentityRepository | None = None,
        session: Session | None = None,
    ) -> None:
        if repository is None:
            if session is None:
                raise ValueError("Нужен repository или session")
            repository = IdentityRepository(session)
        self.repository = repository

    def resolve(self, principal: Principal) -> AppUser:
        """Возвращает активный AppUser, связанный с issuer и subject Principal."""
        try:
            external_identity = self.repository.find_external_identity(principal)
        except Exception as error:
            raise IdentityResolutionPersistenceError(
                "Не удалось прочитать внешнюю identity"
            ) from error

        if external_identity is None:
            raise IdentityResolutionNotFoundError(
                "Для Principal не найдена внешняя identity"
            )

        try:
            app_user = self.repository.get_app_user_by_id(external_identity.app_user_id)
        except Exception as error:
            raise IdentityResolutionPersistenceError(
                "Не удалось прочитать AppUser"
            ) from error

        if app_user is None:
            raise IdentityResolutionIntegrityError(
                "ExternalIdentity ссылается на отсутствующий AppUser"
            )

        if not app_user.is_active:
            raise IdentityResolutionInactiveUserError(
                "Связанный AppUser неактивен"
            )

        return app_user
