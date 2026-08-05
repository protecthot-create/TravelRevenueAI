"""Нейтральная заглушка оценки уверенности."""

from __future__ import annotations

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
)


class NullConfidenceEstimator:
    """Оценщик по умолчанию с консервативной уверенностью."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> ConfidenceLevel:
        """Не повышает уверенность без проверяемого основания."""
        return ConfidenceLevel.LOW