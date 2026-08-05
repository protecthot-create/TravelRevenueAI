"""Доменные модели изолированного слоя Revenue Intelligence.

Модели не являются ORM-сущностями и не зависят от API, базы данных или Pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class OpportunityType(StrEnum):
    """Тип бизнес-возможности."""

    REVENUE_GROWTH = "revenue_growth"
    COST_SAVING = "cost_saving"
    RETENTION = "retention"
    PRICING = "pricing"
    SEGMENT = "segment"
    OPERATIONAL = "operational"


class RiskType(StrEnum):
    """Тип угрозы выручке."""

    PRICE_INCREASE = "price_increase"
    DEMAND_DECLINE = "demand_decline"
    MARGIN_LOSS = "margin_loss"
    CANCELLATION = "cancellation"
    COMPETITIVE = "competitive"
    OPERATIONAL = "operational"
    OTHER = "other"


class UrgencyLevel(StrEnum):
    """Уровень срочности реакции."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(StrEnum):
    """Качественная интерпретация уверенности."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationPriority(StrEnum):
    """Приоритет рекомендуемого действия."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationActionType(StrEnum):
    """Поддерживаемый тип детерминированного действия."""

    CALL_CLIENTS = "call_clients"
    SEND_EMAIL_CAMPAIGN = "send_email_campaign"
    SEND_MESSENGER_CAMPAIGN = "send_messenger_campaign"
    PUBLISH_SOCIAL_MEDIA_POST = "publish_social_media_post"
    UPDATE_WEBSITE_BANNER = "update_website_banner"
    NOTIFY_SALES_MANAGER = "notify_sales_manager"
    CREATE_CRM_TASK = "create_crm_task"
    CONTACT_TOUR_OPERATOR = "contact_tour_operator"
    MONITOR_PROMOTION = "monitor_promotion"
    ESCALATE_URGENT_OPPORTUNITY = "escalate_urgent_opportunity"
    WAIT = "wait"
    IGNORE = "ignore"


class RevenueImpact(BaseModel):
    """Оценка диапазона влияния на выручку без обещания результата.

    Пустые границы означают, что доступных фактов недостаточно для
    детерминированной денежной оценки. Это не является прогнозом.
    """

    amount_min: float | None = Field(default=None, ge=0)
    amount_max: float | None = Field(default=None, ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    calculation_method: str = Field(min_length=1)
    explanation: str = Field(
        default="Объяснение оценки не задано.",
        min_length=1,
    )
    assumptions: list[str] = Field(default_factory=list)

    @property
    def revenue_range_min(self) -> float | None:
        """Возвращает нижнюю границу в терминологии Revenue Estimation Engine."""
        return self.amount_min

    @property
    def revenue_range_max(self) -> float | None:
        """Возвращает верхнюю границу в терминологии Revenue Estimation Engine."""
        return self.amount_max

    def model_post_init(self, __context: object) -> None:
        """Гарантирует согласованность границ диапазона."""
        if (self.amount_min is None) != (self.amount_max is None):
            raise ValueError("Границы диапазона должны быть заданы одновременно")
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_min > self.amount_max
        ):
            raise ValueError("amount_min не может быть больше amount_max")


class RevenueOpportunity(BaseModel):
    """Возможность дополнительной выручки."""

    estimated_revenue: float | None = Field(default=None, ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    revenue_range_min: float | None = Field(default=None, ge=0)
    revenue_range_max: float | None = Field(default=None, ge=0)
    affected_clients_count: int | None = Field(default=None, ge=0)
    conversion_probability: float | None = Field(default=None, ge=0, le=1)


class RevenueRisk(BaseModel):
    """Угроза потери выручки."""

    estimated_loss: float = Field(ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    risk_type: RiskType
    probability: float = Field(ge=0, le=1)
    deadline: datetime | None = None
    mitigation_actions: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """Объяснимое действие, сформированное детерминированным правилом.

    Поля ``action`` и ``rationale`` поддерживаются как входная совместимость
    с RC2.2; новые рекомендации должны использовать расширенный контракт.
    """

    action_type: RecommendationActionType = RecommendationActionType.WAIT
    title: str = Field(default="Ожидать подтверждения", min_length=1)
    description: str = Field(default="Недостаточно данных для активного действия.", min_length=1)
    reason: str = Field(default="Действие сформировано по детерминированному правилу.", min_length=1)
    priority: RecommendationPriority
    deadline: datetime | None = None
    expected_result: str | None = None
    required_entities: dict[str, list[str]] = Field(default_factory=dict)
    supporting_evidence: list[str] = Field(default_factory=list)
    supporting_signal_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: object) -> object:
        """Преобразует поля RC2.2 в расширенный контракт без потери данных."""
        if not isinstance(value, dict):
            return value

        normalized = value.copy()
        action = normalized.pop("action", None)
        rationale = normalized.pop("rationale", None)
        expected_effect = normalized.pop("expected_effect", None)
        target_segment = normalized.pop("target_segment", None)

        if action:
            normalized.setdefault("title", action)
            normalized.setdefault("description", action)
        if rationale:
            normalized.setdefault("reason", rationale)
        if expected_effect:
            normalized.setdefault("expected_result", expected_effect)
        if target_segment:
            normalized.setdefault("required_entities", {"segment": [target_segment]})
        return normalized

    @property
    def action(self) -> str:
        """Возвращает заголовок для обратной совместимости с RC2.2."""
        return self.title

    @property
    def rationale(self) -> str:
        """Возвращает объяснение для обратной совместимости с RC2.2."""
        return self.reason

    @property
    def expected_effect(self) -> str | None:
        """Возвращает ожидаемый результат для обратной совместимости с RC2.2."""
        return self.expected_result


class OpportunityScore(BaseModel):
    """Разложенная оценка возможности для будущей приоритизации."""

    revenue_score: float = Field(ge=0, le=100)
    urgency_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    relevance_score: float = Field(ge=0, le=100)
    deadline_score: float = Field(default=0, ge=0, le=100)
    recommendation_priority_score: float = Field(default=0, ge=0, le=100)
    final_score: float = Field(ge=0, le=100)
    explanation: str = Field(min_length=1)


class BusinessOpportunity(BaseModel):
    """Объяснимая возможность, полученная из одного или нескольких сигналов."""

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    opportunity_type: OpportunityType
    source_signal_ids: list[UUID] = Field(default_factory=list)
    detected_entities: dict[str, list[str]] = Field(default_factory=dict)
    revenue_impact: RevenueImpact | None = None
    urgency: UrgencyLevel = UrgencyLevel.LOW
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    recommended_actions: list[Recommendation] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    score: OpportunityScore | None = None


class OpportunityGroup(BaseModel):
    """Группа связанных возможностей с общими бизнес-сущностями."""

    group_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1)
    opportunities: list[BusinessOpportunity] = Field(default_factory=list)
    shared_entities: dict[str, list[str]] = Field(default_factory=dict)
    combined_revenue_impact: RevenueImpact | None = None
    group_confidence: ConfidenceLevel = ConfidenceLevel.LOW