"""API v1 endpoints для Travel Revenue AI."""

from travel_revenue_ai.api.v1.morning_brief import router as morning_brief_router
from travel_revenue_ai.api.v1.signals import router as signals_router
from travel_revenue_ai.api.v1.sources import router as sources_router

__all__ = ["morning_brief_router", "signals_router", "sources_router"]
