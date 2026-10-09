"""Composition root приложения.

Собирает инфраструктурные и доменные зависимости на границе приложения.
PipelineService не знает о конкретных RuleBased-компонентах Revenue Intelligence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from travel_revenue_ai.config import Settings, settings
from travel_revenue_ai.database import SessionLocal
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
from travel_revenue_ai.services.scheduler_service import SchedulerService
from travel_revenue_ai.services.signal_service import SignalService
from travel_revenue_ai.services.source_collection_service import (
    SourceCollectionResult,
    SourceCollectionService,
)
from travel_revenue_ai.services.tenant_authorization_service import TenantAuthorizationService
from travel_revenue_ai.services.tenant_provisioning_service import TenantProvisioningService
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


class ScheduledCollectionJob:
    """Runtime-джоба планового запуска Morning Brief с per-run сессией.

    Каждый плановый прогон создаёт свежую SQLAlchemy-сессию и заново собирает
    граф зависимостей через ``build_source_collection_service``: адаптеры
    источников не кэшируются между прогонами, а сессия гарантированно
    закрывается и при успехе, и при ошибке. Транзакциями владеют существующие
    сервисы — обёртка не делает commit и rollback самостоятельно.
    """

    def __init__(
        self,
        app_settings: Settings = settings,
        session_factory: Callable[[], Session] = SessionLocal,
        collection_builder: Callable[[Session, Settings], SourceCollectionService] | None = None,
    ) -> None:
        """Принимает фабрику сессий и опциональный builder для тестовых подмен."""
        self._app_settings = app_settings
        self._session_factory = session_factory
        self._collection_builder = collection_builder or build_source_collection_service
        self._logger = logging.getLogger(__name__)

    def collect_and_generate_morning_brief(self) -> SourceCollectionResult:
        """Выполняет один плановый запуск с независимой сессией и логом итога."""
        self._logger.info("Плановый запуск Morning Brief начат")
        session = self._session_factory()
        try:
            source_collection_service = self._collection_builder(session, self._app_settings)
            result = source_collection_service.collect_and_generate_morning_brief()
        except Exception as error:
            self._logger.error(
                "Плановый запуск Morning Brief завершился ошибкой",
                extra={"error_type": type(error).__name__},
            )
            raise
        finally:
            session.close()
        self._logger.info(
            "Плановый запуск Morning Brief завершён: collected=%d, saved=%d, "
            "errors=%d, persisted_agencies=%d",
            result.collected_count,
            result.saved_count,
            result.errors_count,
            len(result.persisted_briefs),
        )
        return result


def build_scheduler_service(
    app_settings: Settings = settings,
    session_factory: Callable[[], Session] = SessionLocal,
) -> SchedulerService:
    """Собирает SchedulerService для планового запуска в FastAPI lifespan.

    Возвращает существующий SchedulerService без изменения его контракта:
    ежедневная задача регистрируется через ``register_daily_job``, а каждый
    прогон получает свежую сессию через ``ScheduledCollectionJob``.
    """
    scheduled_job = ScheduledCollectionJob(
        app_settings=app_settings,
        session_factory=session_factory,
    )
    return SchedulerService(
        source_collection_service=scheduled_job,
        app_settings=app_settings,
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


def build_tenant_provisioning_service(
    session: Session,
) -> TenantProvisioningService:
    """Собирает write-сервис первичного tenant provisioning для одного запроса."""
    return TenantProvisioningService(session=session)


def build_persisted_morning_brief_service(
    session: Session,
    app_settings: Settings = settings,
) -> PersistedMorningBriefService:
    """Собирает persisted use case, не присоединяя его к API."""
    return PersistedMorningBriefService(
        session=session,
        pipeline_service=build_pipeline_service(app_settings),
    )
