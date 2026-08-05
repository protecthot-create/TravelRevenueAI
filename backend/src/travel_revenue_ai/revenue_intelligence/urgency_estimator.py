"""Нейтральная заглушка оценки срочности."""

from __future__ import annotations

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import BusinessOpportunity, UrgencyLevel


class NullUrgencyEstimator:
    """Оценщик по умолчанию с безопасным низким уровнем срочности."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> UrgencyLevel:
        """Не повышает срочность без детерминированного правила."""
        return UrgencyLevel.LOW