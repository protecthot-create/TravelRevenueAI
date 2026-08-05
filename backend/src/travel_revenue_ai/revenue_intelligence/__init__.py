"""Изолированный доменный слой Revenue Intelligence.

Пакет не подключён к действующему Pipeline и не выполняет операций ввода-вывода.
"""

from travel_revenue_ai.revenue_intelligence.contracts import (
    OpportunityRankingResult,
    RankedOpportunity,
    RevenueIntelligenceContext,
    RevenueIntelligenceError,
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.revenue_intelligence.engine import RevenueIntelligenceEngine
from travel_revenue_ai.revenue_intelligence.interfaces import OpportunityRanker
from travel_revenue_ai.revenue_intelligence.opportunity_ranker import (
    RuleBasedOpportunityRanker,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityGroup,
    OpportunityScore,
    OpportunityType,
    Recommendation,
    RecommendationPriority,
    RevenueImpact,
    RevenueOpportunity,
    RevenueRisk,
    RiskType,
    UrgencyLevel,
)

__all__ = [
    "BusinessOpportunity",
    "ConfidenceLevel",
    "OpportunityGroup",
    "OpportunityRanker",
    "OpportunityRankingResult",
    "OpportunityScore",
    "OpportunityType",
    "Recommendation",
    "RankedOpportunity",
    "RecommendationPriority",
    "RevenueImpact",
    "RevenueIntelligenceContext",
    "RevenueIntelligenceEngine",
    "RevenueIntelligenceError",
    "RevenueIntelligenceInput",
    "RevenueIntelligenceResult",
    "RevenueOpportunity",
    "RevenueRisk",
    "RiskType",
    "RuleBasedOpportunityRanker",
    "UrgencyLevel",
]