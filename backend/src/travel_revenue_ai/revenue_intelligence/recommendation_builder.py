"""Детерминированный построитель рекомендаций Revenue Intelligence.

Модуль не вызывает внешние сервисы и не выполняет действия. Он только переводит
доказанную BusinessOpportunity в объяснимые объекты Recommendation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityType,
    Recommendation,
    RecommendationActionType,
    RecommendationPriority,
    UrgencyLevel,
)


class NullRecommendationBuilder:
    """Построитель по умолчанию, не создающий неподтверждённых действий."""

    def build(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> list[Recommendation]:
        """Возвращает пустой список до явного подключения правил."""
        return []


class RuleBasedRecommendationBuilder:
    """Строит рекомендации только по типу, срочности, уверенности и доказательствам.

    Builder не использует LLM, статистические модели, клиентскую историю, CRM,
    внешние API или финансовые прогнозы. Контекст принят только для соблюдения
    общего интерфейса и не участвует в принятии решения.
    """

    def build(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext | None = None,
    ) -> list[Recommendation]:
        """Возвращает дедуплицированный список действий для одной возможности."""
        del context

        if not opportunity.evidence:
            return []

        priority = self._priority_for(opportunity)
        deadline = self._deadline_for(opportunity)
        recommendations: list[Recommendation] = []

        if opportunity.confidence == ConfidenceLevel.LOW:
            action_type = (
                RecommendationActionType.IGNORE
                if opportunity.urgency == UrgencyLevel.LOW
                else RecommendationActionType.WAIT
            )
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    action_type,
                    priority=RecommendationPriority.LOW,
                    deadline=deadline,
                )
            )
            return self._merge_duplicates(recommendations)

        if opportunity.urgency == UrgencyLevel.CRITICAL:
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.ESCALATE_URGENT_OPPORTUNITY,
                    priority=RecommendationPriority.CRITICAL,
                    deadline=deadline,
                )
            )

        if opportunity.opportunity_type in {
            OpportunityType.REVENUE_GROWTH,
            OpportunityType.SEGMENT,
        }:
            recommendations.extend(self._promotion_actions(opportunity, priority, deadline))
        elif opportunity.opportunity_type == OpportunityType.RETENTION:
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.CALL_CLIENTS,
                    priority=priority,
                    deadline=deadline,
                )
            )
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.SEND_MESSENGER_CAMPAIGN,
                    priority=priority,
                    deadline=deadline,
                )
            )
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.CREATE_CRM_TASK,
                    priority=priority,
                    deadline=deadline,
                )
            )
        elif opportunity.opportunity_type == OpportunityType.PRICING:
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.NOTIFY_SALES_MANAGER,
                    priority=priority,
                    deadline=deadline,
                )
            )
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.CREATE_CRM_TASK,
                    priority=priority,
                    deadline=deadline,
                )
            )
            if self._has_entity(opportunity, "tour_operator"):
                recommendations.append(
                    self._make_recommendation(
                        opportunity,
                        RecommendationActionType.CONTACT_TOUR_OPERATOR,
                        priority=priority,
                        deadline=deadline,
                    )
                )
        elif opportunity.opportunity_type in {
            OpportunityType.COST_SAVING,
            OpportunityType.OPERATIONAL,
        }:
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.NOTIFY_SALES_MANAGER,
                    priority=priority,
                    deadline=deadline,
                )
            )
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.CREATE_CRM_TASK,
                    priority=priority,
                    deadline=deadline,
                )
            )

        if opportunity.urgency in {UrgencyLevel.LOW, UrgencyLevel.MEDIUM}:
            recommendations.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.MONITOR_PROMOTION,
                    priority=RecommendationPriority.LOW,
                    deadline=deadline,
                )
            )

        return self._merge_duplicates(recommendations)

    def _promotion_actions(
        self,
        opportunity: BusinessOpportunity,
        priority: RecommendationPriority,
        deadline: datetime | None,
    ) -> list[Recommendation]:
        """Возвращает каналы продвижения, подтверждённые найденными сущностями."""
        actions: list[Recommendation] = []

        if self._has_any_entity(opportunity, {"client_segment", "audience", "clients"}):
            actions.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.CALL_CLIENTS,
                    priority=priority,
                    deadline=deadline,
                )
            )
            actions.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.SEND_EMAIL_CAMPAIGN,
                    priority=priority,
                    deadline=deadline,
                )
            )
        if self._has_any_entity(opportunity, {"messenger", "messenger_channel"}):
            actions.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.SEND_MESSENGER_CAMPAIGN,
                    priority=priority,
                    deadline=deadline,
                )
            )
        if self._has_any_entity(opportunity, {"social_media", "social_network"}):
            actions.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.PUBLISH_SOCIAL_MEDIA_POST,
                    priority=priority,
                    deadline=deadline,
                )
            )
        if self._has_any_entity(opportunity, {"website", "landing_page"}):
            actions.append(
                self._make_recommendation(
                    opportunity,
                    RecommendationActionType.UPDATE_WEBSITE_BANNER,
                    priority=priority,
                    deadline=deadline,
                )
            )

        return actions

    def _make_recommendation(
        self,
        opportunity: BusinessOpportunity,
        action_type: RecommendationActionType,
        *,
        priority: RecommendationPriority,
        deadline: datetime | None,
    ) -> Recommendation:
        """Создаёт объяснимую рекомендацию из статического шаблона действия."""
        title, description, expected_result = _ACTION_DETAILS[action_type]
        return Recommendation(
            action_type=action_type,
            title=title,
            description=description,
            reason=(
                f"Возможность «{opportunity.title}» имеет тип "
                f"«{opportunity.opportunity_type.value}», срочность "
                f"«{opportunity.urgency.value}» и уверенность "
                f"«{opportunity.confidence.value}»."
            ),
            priority=priority,
            deadline=deadline,
            expected_result=expected_result,
            required_entities={
                entity_type: list(values)
                for entity_type, values in opportunity.detected_entities.items()
                if values
            },
            supporting_evidence=list(opportunity.evidence),
            supporting_signal_ids=list(opportunity.source_signal_ids),
        )

    @staticmethod
    def _priority_for(opportunity: BusinessOpportunity) -> RecommendationPriority:
        """Определяет приоритет только по срочности и уверенности."""
        if opportunity.urgency == UrgencyLevel.CRITICAL:
            return RecommendationPriority.CRITICAL
        if opportunity.urgency == UrgencyLevel.HIGH:
            return RecommendationPriority.HIGH
        if (
            opportunity.urgency == UrgencyLevel.MEDIUM
            and opportunity.confidence == ConfidenceLevel.HIGH
        ):
            return RecommendationPriority.HIGH
        if opportunity.urgency == UrgencyLevel.MEDIUM:
            return RecommendationPriority.MEDIUM
        return RecommendationPriority.LOW

    @staticmethod
    def _deadline_for(opportunity: BusinessOpportunity) -> datetime | None:
        """Выводит повторяемый дедлайн из срочности, не обращаясь к внешнему времени."""
        hours_by_urgency = {
            UrgencyLevel.CRITICAL: 4,
            UrgencyLevel.HIGH: 24,
            UrgencyLevel.MEDIUM: 72,
        }
        hours = hours_by_urgency.get(opportunity.urgency)
        return opportunity.created_at + timedelta(hours=hours) if hours else None

    @staticmethod
    def _has_entity(opportunity: BusinessOpportunity, entity_type: str) -> bool:
        """Проверяет наличие непустой сущности заданного типа."""
        return bool(opportunity.detected_entities.get(entity_type))

    @classmethod
    def _has_any_entity(
        cls,
        opportunity: BusinessOpportunity,
        entity_types: set[str],
    ) -> bool:
        """Проверяет наличие хотя бы одной сущности из заданного набора."""
        return any(cls._has_entity(opportunity, entity_type) for entity_type in entity_types)

    @staticmethod
    def _merge_duplicates(recommendations: list[Recommendation]) -> list[Recommendation]:
        """Объединяет одинаковые действия, сохраняя уникальные доказательства."""
        merged: dict[tuple[RecommendationActionType, str], Recommendation] = {}
        for recommendation in recommendations:
            key = (recommendation.action_type, recommendation.title)
            existing = merged.get(key)
            if existing is None:
                merged[key] = recommendation
                continue

            existing.required_entities = _merge_entities(
                existing.required_entities,
                recommendation.required_entities,
            )
            existing.supporting_evidence = _merge_strings(
                existing.supporting_evidence,
                recommendation.supporting_evidence,
            )
            existing.supporting_signal_ids = list(
                dict.fromkeys(
                    [*existing.supporting_signal_ids, *recommendation.supporting_signal_ids]
                )
            )
        return list(merged.values())


def _merge_entities(
    first: dict[str, list[str]],
    second: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Объединяет сущности без повторов и без изменения входных словарей."""
    keys = set(first) | set(second)
    return {
        key: _merge_strings(first.get(key, []), second.get(key, []))
        for key in keys
    }


def _merge_strings(first: list[str], second: list[str]) -> list[str]:
    """Объединяет строки, сохраняя порядок первого появления."""
    return list(dict.fromkeys([*first, *second]))


_ACTION_DETAILS: dict[RecommendationActionType, tuple[str, str, str]] = {
    RecommendationActionType.CALL_CLIENTS: (
        "Позвонить целевому сегменту",
        "Связаться с целевым сегментом по подтверждённой возможности.",
        "Целевой сегмент получит релевантное предложение.",
    ),
    RecommendationActionType.SEND_EMAIL_CAMPAIGN: (
        "Запустить email-кампанию",
        "Подготовить и отправить письмо по подтверждённому сегменту.",
        "Подтверждённый сегмент получит сообщение о возможности.",
    ),
    RecommendationActionType.SEND_MESSENGER_CAMPAIGN: (
        "Запустить кампанию в мессенджере",
        "Подготовить сообщение для указанного канала мессенджера.",
        "Аудитория мессенджера получит подтверждённое сообщение.",
    ),
    RecommendationActionType.PUBLISH_SOCIAL_MEDIA_POST: (
        "Опубликовать пост в социальных сетях",
        "Разместить пост в указанном социальном канале.",
        "Подтверждённый социальный канал получит публикацию.",
    ),
    RecommendationActionType.UPDATE_WEBSITE_BANNER: (
        "Обновить баннер на сайте",
        "Обновить баннер или посадочную страницу по найденной возможности.",
        "Посетители сайта увидят актуальное предложение.",
    ),
    RecommendationActionType.NOTIFY_SALES_MANAGER: (
        "Уведомить менеджера по продажам",
        "Передать менеджеру подтверждённый факт для ручной обработки.",
        "Менеджер получит объяснимую задачу на проверку.",
    ),
    RecommendationActionType.CREATE_CRM_TASK: (
        "Создать задачу для последующей обработки",
        "Зафиксировать задачу как рекомендацию; интеграция с CRM не выполняется.",
        "Будет сформирован объект задачи для будущей интеграции.",
    ),
    RecommendationActionType.CONTACT_TOUR_OPERATOR: (
        "Связаться с туроператором",
        "Запросить уточнение по подтверждённой сущности туроператора.",
        "Будет получено ручное уточнение условий у туроператора.",
    ),
    RecommendationActionType.MONITOR_PROMOTION: (
        "Наблюдать за возможностью",
        "Отслеживать подтверждённый сигнал до появления более сильного основания.",
        "Будет сохранено наблюдение без активного вмешательства.",
    ),
    RecommendationActionType.ESCALATE_URGENT_OPPORTUNITY: (
        "Эскалировать срочную возможность",
        "Немедленно передать критичную возможность ответственному владельцу.",
        "Критичная возможность будет замечена в приоритетном порядке.",
    ),
    RecommendationActionType.WAIT: (
        "Ожидать подтверждения",
        "Не выполнять активных действий до повышения уверенности сигнала.",
        "Будут исключены действия по недостаточно подтверждённому сигналу.",
    ),
    RecommendationActionType.IGNORE: (
        "Игнорировать сигнал",
        "Не выполнять действие: низкая срочность и низкая уверенность не обосновывают вмешательство.",
        "Пользователь не будет отвлечён слабым сигналом.",
    ),
}