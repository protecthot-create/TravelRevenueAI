"""Read-only repository для активных agency memberships."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_revenue_ai.models.agency_membership import AgencyMembership


class MembershipRepository:
    """Читает membership без изменения состояния сессии или транзакции."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active_by_app_user_id(self, app_user_id: UUID) -> list[AgencyMembership]:
        """Возвращает только active memberships пользователя."""
        statement = (
            select(AgencyMembership)
            .where(
                AgencyMembership.app_user_id == app_user_id,
                AgencyMembership.status == "active",
            )
            .order_by(AgencyMembership.agency_id)
        )
        return list(self.session.scalars(statement))

    def get_active_by_app_user_and_agency(
        self,
        *,
        app_user_id: UUID,
        agency_id: UUID,
    ) -> AgencyMembership | None:
        """Возвращает active membership конкретного пользователя и агентства."""
        statement = select(AgencyMembership).where(
            AgencyMembership.app_user_id == app_user_id,
            AgencyMembership.agency_id == agency_id,
            AgencyMembership.status == "active",
        )
        return self.session.scalar(statement)
