"""Write-repository для атомарного tenant provisioning."""

from __future__ import annotations

from sqlalchemy.orm import Session

from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.agency_membership import AgencyMembership
from travel_revenue_ai.models.app_user import AppUser
from travel_revenue_ai.models.external_identity import ExternalIdentity


class TenantProvisioningRepository:
    """Добавляет записи provisioning в текущую транзакцию без владения commit."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_app_user(self, app_user: AppUser) -> None:
        """Добавляет AppUser в текущую транзакцию."""
        self.session.add(app_user)

    def add_external_identity(self, external_identity: ExternalIdentity) -> None:
        """Добавляет ExternalIdentity в текущую транзакцию."""
        self.session.add(external_identity)

    def add_agency(self, agency: Agency) -> None:
        """Добавляет Agency в текущую транзакцию."""
        self.session.add(agency)

    def add_membership(self, membership: AgencyMembership) -> None:
        """Добавляет AgencyMembership в текущую транзакцию."""
        self.session.add(membership)

    def flush(self) -> None:
        """Сбрасывает pending-записи в БД внутри текущей транзакции."""
        self.session.flush()
