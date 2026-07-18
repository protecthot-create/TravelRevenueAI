"""Pydantic модели для API."""

from travel_revenue_ai.schemas.morning_brief import MorningBriefCreate, MorningBriefResponse
from travel_revenue_ai.schemas.signal import SignalCreate, SignalResponse

__all__ = [
    "MorningBriefCreate",
    "MorningBriefResponse",
    "SignalCreate",
    "SignalResponse",
]
