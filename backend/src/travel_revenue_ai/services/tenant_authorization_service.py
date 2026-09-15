"""Сервис разрешения tenant-контекста поверх CS10 identity foundation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from travel_revenue_ai.repositories.membership_repository import MembershipRepository
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.security.tenant_context import TenantContext
from travel_revenue_ai.services.identity_resolution_service import IdentityResolutionService
from travel_revenue_ai.services.tenant_authorization_errors import (
    TenantAccessDeniedError,
    TenantAuthorizationIntegrityError,
    TenantAuthorizationPersistenceError,
    TenantSelectionRequiredError,
)

if TYPE_CHECKING:
    from travel_revenue_ai.models.agency_membership import AgencyMembership


class TenantAuthorizationService:
    """Разрешает active agency membership без записи и без управления транзакцией."""

    def __init__(
        self,
        *,
        identity_service: IdentityResolutionService | None = None,
        membership_repository: MembershipRepository | None = None,
        session: Session | None = None,
    ) -> None:
        if identity_service is None or membership_repository is None:
            if session is None:
                raise ValueError("Нужен identity_service и membership_repository или session")
            identity_service = identity_service or IdentityResolutionService(session=session)
            membership_repository = membership_repository or MembershipRepository(session)
        self.identity_service = identity_service
        self.membership_repository = membership_repository

    def authorize(
        self,
        principal: Principal,
        agency_id: UUID | None = None,
    ) -> TenantContext:
        """Возвращает tenant-контекст для выбранного или однозначного агентства."""
        app_user = self.identity_service.resolve(principal)
        try:
            memberships = self.membership_repository.list_active_by_app_user_id(
                app_user.app_user_id
            )
        except Exception as error:
            raise TenantAuthorizationPersistenceError(
                "Не удалось прочитать active agency memberships"
            ) from error

        if not memberships:
            raise TenantAccessDeniedError("У пользователя нет active agency membership")

        if agency_id is not None:
            membership = next(
                (item for item in memberships if item.agency_id == agency_id),
                None,
            )
            if membership is None:
                raise TenantAccessDeniedError("Нет доступа к запрошенному агентству")
            return self._to_context(app_user.app_user_id, membership)

        if len(memberships) != 1:
            raise TenantSelectionRequiredError(
                "Для пользователя с несколькими агентствами нужно явно передать agency_id"
            )
        return self._to_context(app_user.app_user_id, memberships[0])

    @staticmethod
    def _to_context(app_user_id: UUID, membership: AgencyMembership) -> TenantContext:
        """Преобразует проверенный membership в неизменяемый контекст."""
        if membership.status != "active":
            raise TenantAuthorizationIntegrityError(
                "В tenant context попал неактивный membership"
            )
        return TenantContext(
            app_user_id=app_user_id,
            agency_id=membership.agency_id,
            role=membership.role,
        )
