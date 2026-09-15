"""Composition root приложения.

Собирает инфраструктурные и доменные зависимости на границе приложения.
PipelineService не знает о конкретных RuleBased-компонентах Revenue Intelligence.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from travel_revenue_ai.config import Settings, settings
from travel_revenue_ai.repositories.membership_repository import MembershipRepository
from travel_revenue_ai.revenue_intelligence.engine import RevenueIntelligenceEngine
from travel_revenue_ai.revenue_intelligence.opportunity_detector import (
    RuleBasedOpportunityDetector,
)
from travel_revenue_ai.revenue_intelligence.opportunity_ranker import (
    RuleBasedOpportunityRanker,
)
from travel_revenue_ai.revenue_intelligence.recommendation_builder import (
    RuleBasedRecommendationBuilder,
)
from travel_revenue_ai.revenue_intelligence.revenue_estimator import (
    RuleBasedRevenueEstimator,
)
from travel_revenue_ai.security.secrets import SecretService
from travel_revenue_ai.services.data_source_service import DataSourceService
from travel_revenue_ai.services.identity_resolution_service import IdentityResolutionService
from travel_revenue_ai.services.morning_brief_read_service import MorningBriefReadService
from travel_revenue_ai.services.persisted_morning_brief_service import (
    PersistedMorningBriefService,
)
from travel_revenue_ai.services.pipeline_service import PipelineService
from travel_revenue_ai.services.signal_service import SignalService
from travel_revenue_ai.services.source_collection_service import SourceCollectionService
from travel_revenue_ai.services.tenant_authorization_service import TenantAuthorizationService
from travel_revenue_ai.sources.default_providers import register_default_providers
from travel_revenue_ai.sources.manager import SourceManager
from travel_revenue_ai.sources.provider_registry import ProviderRegistry
from travel_revenue_ai.sources.runtime_factory import DataSourceRuntimeFactory


def build_revenue_intelligence_engine(
    app_settings: Settings = settings,
) -> RevenueIntelligenceEngine | None:
    """Создаёт Engine только при явно включённом feature flag."""
    if not app_settings.revenue_intelligence_enabled:
        return None

    return RevenueIntelligenceEngine(
        detectors=(RuleBasedOpportunityDetector(),),
        revenue_estimator=RuleBasedRevenueEstimator(),
        recommendation_builder=RuleBasedRecommendationBuilder(),
        opportunity_ranker=RuleBasedOpportunityRanker(),
    )


def build_pipeline_service(
    app_settings: Settings = settings,
) -> PipelineService:
    """Собирает Pipeline с изолированным необязательным Engine."""
    return PipelineService(
        revenue_intelligence_engine=build_revenue_intelligence_engine(app_settings)
    )


def build_source_collection_service(
    session: Session,
    app_settings: Settings = settings,
    agency_id: UUID | None = None,
) -> SourceCollectionService:
    """Собирает runtime-источники и orchestration-сервис одного запуска."""
    provider_registry = ProviderRegistry()
    register_default_providers(provider_registry)

    secret_service = SecretService(
        app_settings.secret_encryption_key,
        require_encryption=app_settings.is_production,
    )
    source_manager = SourceManager()
    data_source_service = DataSourceService(
        session,
        provider_registry=provider_registry,
        secret_service=secret_service,
    )
    runtime_factory = DataSourceRuntimeFactory(
        provider_registry=provider_registry,
        secret_service=secret_service,
    )
    runtime_factory.register_enabled_sources(
        source_manager=source_manager,
        data_sources=data_source_service.list_sources(agency_id=agency_id),
    )

    return SourceCollectionService(
        source_manager=source_manager,
        signal_service=SignalService(session),
        pipeline_service=build_pipeline_service(app_settings),
        persisted_morning_brief_service=build_persisted_morning_brief_service(
            session,
            app_settings,
        ),
    )


def build_morning_brief_read_service(
    session: Session,
) -> MorningBriefReadService:
    """Собирает read-only сервис persisted MorningBrief для одного HTTP-запроса."""
    return MorningBriefReadService(session=session)


def build_identity_resolution_service(
    session: Session,
) -> IdentityResolutionService:
    """Собирает read-only resolver identity для одного запроса."""
    return IdentityResolutionService(session=session)


def build_tenant_authorization_service(
    session: Session,
) -> TenantAuthorizationService:
    """Собирает read-only tenant authorization для одного запроса."""
    return TenantAuthorizationService(
        identity_service=build_identity_resolution_service(session),
        membership_repository=MembershipRepository(session),
    )


def build_persisted_morning_brief_service(
    session: Session,
    app_settings: Settings = settings,
) -> PersistedMorningBriefService:
    """Собирает persisted use case, не присоединяя его к API."""
    return PersistedMorningBriefService(
        session=session,
        pipeline_service=build_pipeline_service(app_settings),
    )
