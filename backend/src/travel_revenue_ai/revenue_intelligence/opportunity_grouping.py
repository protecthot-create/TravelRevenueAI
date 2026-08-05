"""Нейтральная заглушка группировки возможностей."""

from __future__ import annotations

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    OpportunityGroup,
)


class NullOpportunityGrouper:
    """Группировщик по умолчанию, не объединяющий возможности без правил."""

    def group(
        self,
        opportunities: list[BusinessOpportunity],
        context: RevenueIntelligenceContext,
    ) -> list[OpportunityGroup]:
        """Возвращает пустой список до реализации правил связи сущностей."""
        return []