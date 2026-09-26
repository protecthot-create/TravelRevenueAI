"""Сервис атомарного первичного tenant provisioning для brand-new Clerk user."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.agency_membership import AgencyMembership
from travel_revenue_ai.models.app_user import AppUser
from travel_revenue_ai.models.external_identity import ExternalIdentity
from travel_revenue_ai.repositories.identity_repository import IdentityRepository
from travel_revenue_ai.repositories.membership_repository import MembershipRepository
from travel_revenue_ai.repositories.tenant_provisioning_repository import (
    TenantProvisioningRepository,
)
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.tenant_provisioning_errors import (
    TenantProvisioningError,
    TenantProvisioningInactiveUserError,
    TenantProvisioningPersistenceError,
    TenantProvisioningStateError,
)

OWNER_ROLE = "owner"
ACTIVE_STATUS = "active"


@dataclass(frozen=True, slots=True)
class TenantProvisioningResult:
    """Результат первичного tenant provisioning."""

    app_user_id: UUID
    agency_id: UUID
    role: str
    replayed: bool


class TenantProvisioningService:
    """Единственный владелец транзакции первичного tenant provisioning."""

    def __init__(
        self,
        *,
        session: Session,
        provisioning_repository: TenantProvisioningRepository | None = None,
        identity_repository: IdentityRepository | None = None,
        membership_repository: MembershipRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = provisioning_repository or TenantProvisioningRepository(session)
        self.identity_repository = identity_repository or IdentityRepository(session)
        self.membership_repository = membership_repository or MembershipRepository(session)

    def provision(self, principal: Principal) -> TenantProvisioningResult:
        """Атомарно создаёт tenant-цепочку или возвращает существующий state."""
        replayed = self._resolve_existing_state(principal)
        if replayed is not None:
            return replayed

        try:
            return self._provision_new_tenant(principal)
        except IntegrityError as error:
            self.session.rollback()
            return self._resolve_integrity_race(principal, error)
        except Exception as error:
            self.session.rollback()
            raise TenantProvisioningPersistenceError(
                "Не удалось атомарно выполнить первичный tenant provisioning"
            ) from error

    def _resolve_existing_state(
        self,
        principal: Principal,
    ) -> TenantProvisioningResult | None:
        """Возвращает replay существующего tenant или None, если identity нет."""
        try:
            external_identity = self.identity_repository.find_external_identity(principal)
        except Exception as error:
            raise TenantProvisioningPersistenceError(
                "Не удалось прочитать внешнюю identity"
            ) from error

        if external_identity is None:
            return None

        try:
            app_user = self.identity_repository.get_app_user_by_id(
                external_identity.app_user_id
            )
            memberships = (
                self.membership_repository.list_active_by_app_user_id(app_user.app_user_id)
                if app_user is not None
                else []
            )
        except Exception as error:
            raise TenantProvisioningPersistenceError(
                "Не удалось прочитать существующий tenant state"
            ) from error

        if app_user is None:
            raise TenantProvisioningStateError(
                "ExternalIdentity ссылается на отсутствующий AppUser"
            )
        if not app_user.is_active:
            raise TenantProvisioningInactiveUserError("Связанный AppUser неактивен")
        if not memberships:
            raise TenantProvisioningStateError(
                "ExternalIdentity существует без active agency membership"
            )
        if len(memberships) > 1:
            raise TenantProvisioningStateError(
                "Невозможно однозначно выбрать агентство для replay"
            )

        membership = memberships[0]
        return TenantProvisioningResult(
            app_user_id=app_user.app_user_id,
            agency_id=membership.agency_id,
            role=membership.role,
            replayed=True,
        )

    def _provision_new_tenant(self, principal: Principal) -> TenantProvisioningResult:
        """Создаёт четыре записи aggregate в одной транзакции с одним commit."""
        app_user = AppUser()
        self.repository.add_app_user(app_user)
        self.repository.flush()

        external_identity = ExternalIdentity(
            app_user_id=app_user.app_user_id,
            external_issuer=principal.issuer,
            external_subject=principal.subject_id,
        )
        self.repository.add_external_identity(external_identity)

        agency = Agency()
        self.repository.add_agency(agency)
        self.repository.flush()

        membership = AgencyMembership(
            agency_id=agency.agency_id,
            app_user_id=app_user.app_user_id,
            role=OWNER_ROLE,
            status=ACTIVE_STATUS,
        )
        self.repository.add_membership(membership)

        # Значения фиксируются до commit, так как commit истекает ORM-объекты.
        app_user_id = app_user.app_user_id
        agency_id = agency.agency_id
        role = membership.role
        self.session.commit()
        return TenantProvisioningResult(
            app_user_id=app_user_id,
            agency_id=agency_id,
            role=role,
            replayed=False,
        )

    def _resolve_integrity_race(
        self,
        principal: Principal,
        error: IntegrityError,
    ) -> TenantProvisioningResult:
        """Разрешает гонку повторным чтением после rollback без повторных записей."""
        try:
            replayed = self._resolve_existing_state(principal)
        except TenantProvisioningError:
            raise TenantProvisioningPersistenceError(
                "Повторное чтение tenant state после integrity race не удалось"
            ) from error
        if replayed is not None:
            return replayed
        raise TenantProvisioningPersistenceError(
            "Нарушение ограничения БД при первичном tenant provisioning"
        ) from error
