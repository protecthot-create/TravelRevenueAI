"""Регистрация доменных моделей Travel Revenue AI."""

from travel_revenue_ai.models.action import Action
from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.agency_membership import AgencyMembership
from travel_revenue_ai.models.app_user import AppUser
from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.data_source import DataSource
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.external_identity import ExternalIdentity
from travel_revenue_ai.models.morning_brief import MorningBrief, MorningBriefStatusEnum
from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum

__all__ = [
    "Base",
    "Agency",
    "AppUser",
    "ExternalIdentity",
    "AgencyMembership",
    "DataSource",
    "DecisionCard",
    "MorningBrief",
    "MorningBriefStatusEnum",
    "Action",
    "Signal",
    "SignalStatusEnum",
    "SignalTypeEnum",
]
