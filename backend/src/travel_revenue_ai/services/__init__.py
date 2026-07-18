"""Service Layer для Travel Revenue AI.

Слой бизнес-логики, отделяющий API от моделей данных.
Каждый сервис отвечает за CRUD-операции и бизнес-правила
своей доменной области.

Архитектура:
    API → Services → Models → Database

Сервисы:
    - SignalService: работа с сигналами (CRUD + статусы)
    - RevenueScoringService: оценка сигналов (score, priority, breakdown)
    - FilteringService: фильтрация и приоритизация сигналов
    - [будущие сервисы: DecisionCardService, MorningBriefService и т.д.]
"""

from travel_revenue_ai.services.filtering_service import (
    DefaultFilteringStrategy,
    FilterDecision,
    FilterReason,
    FilterRejection,
    FilterResult,
    FilteringResult,
    FilteringService,
    FilteringStrategy,
)
from travel_revenue_ai.services.decision_card_service import (
    ActionItem,
    CardStatus,
    DecisionCard,
    DecisionCardService,
    DecisionCardType,
    ImportanceLabel,
    MoneyEffect,
)
from travel_revenue_ai.services.morning_brief_service import (
    BriefSummary,
    MorningBriefResult,
    MorningBriefService,
)
from travel_revenue_ai.services.pipeline_service import PipelineService
from travel_revenue_ai.services.revenue_scoring_service import (
    AgencySize,
    FullScoringStrategy,
    PriorityLabel,
    RevenueScoringService,
    ScoreBreakdown,
    ScoreResult,
    ScoringStrategy,
    Season,
)
from travel_revenue_ai.services.scheduler_service import DailySchedule, SchedulerService
from travel_revenue_ai.services.signal_service import SignalService
from travel_revenue_ai.services.source_collection_service import (
    SourceCollectionResult,
    SourceCollectionService,
)

__all__ = [
    # Signal Service
    "SignalService",
    # Decision Card
    "DecisionCardService",
    "DecisionCard",
    "DecisionCardType",
    "MoneyEffect",
    "ActionItem",
    "ImportanceLabel",
    "CardStatus",
    # Revenue Scoring
    "RevenueScoringService",
    "ScoreResult",
    "ScoreBreakdown",
    "PriorityLabel",
    "ScoringStrategy",
    "FullScoringStrategy",
    "AgencySize",
    "Season",
    # Filtering Engine
    "FilteringService",
    "FilterResult",
    "FilterRejection",
    "FilteringResult",
    "FilterDecision",
    "FilterReason",
    "FilteringStrategy",
    "DefaultFilteringStrategy",
    # Morning Brief
    "MorningBriefService",
    "MorningBriefResult",
    "BriefSummary",
    # Pipeline
    "PipelineService",
    # Source Collection
    "SourceCollectionService",
    "SourceCollectionResult",
    # Scheduler
    "SchedulerService",
    "DailySchedule",
]
