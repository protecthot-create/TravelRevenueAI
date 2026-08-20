"""API v1 endpoints для Travel Revenue AI."""

from travel_revenue_ai.api.v1.morning_brief import (
    decision_cards_router,
    morning_brief_history_router,
    router as morning_brief_router,
)
from travel_revenue_ai.api.v1.signals import router as signals_router
from travel_revenue_ai.api.v1.sources import router as sources_router

__all__ = [
    "decision_cards_router",
    "morning_brief_history_router",
    "morning_brief_router",
    "signals_router",
    "sources_router",
]
