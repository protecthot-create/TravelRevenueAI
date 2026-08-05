"""Детерминированные детекторы возможностей слоя Revenue Intelligence."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from travel_revenue_ai.intelligence.entity_extractor import EntityExtractor
from travel_revenue_ai.knowledge.loader import KnowledgeLoader
from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceInput
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityType,
    UrgencyLevel,
)


class NullOpportunityDetector:
    """Детектор по умолчанию, намеренно не создающий бизнес-возможности."""

    def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
        """Возвращает пустой результат до явного подключения конкретного детектора."""
        return []


class RuleBasedOpportunityDetector:
    """Ищет промо-возможности только по детерминированным правилам и Knowledge Base.

    Компонент изолирован: он не вызывает Pipeline, API, БД, LLM или AI-модели.
    Правило срабатывает только при наличии промо-маркера из Knowledge Base и
    специфичного ключевого выражения типа возможности.
    """

    _TYPE_RULES: tuple[tuple[str, OpportunityType, tuple[str, ...]], ...] = (
        ("Promotion", OpportunityType.REVENUE_GROWTH, ("акция", "promotion", "promo")),
        ("Discount", OpportunityType.PRICING, ("скидка", "discount", "sale")),
        (
            "Commission Increase",
            OpportunityType.REVENUE_GROWTH,
            ("повышенная комиссия", "увеличенная комиссия", "commission increase"),
        ),
        (
            "Limited Offer",
            OpportunityType.REVENUE_GROWTH,
            ("ограниченное предложение", "limited offer", "limited availability"),
        ),
        (
            "Last Minute",
            OpportunityType.REVENUE_GROWTH,
            ("горящий тур", "горящие туры", "last minute"),
        ),
        (
            "Early Booking",
            OpportunityType.REVENUE_GROWTH,
            ("раннее бронирование", "early booking"),
        ),
        (
            "Price Drop",
            OpportunityType.PRICING,
            ("снижение цены", "цена снижена", "price drop", "prices dropped"),
        ),
        (
            "New Charter",
            OpportunityType.REVENUE_GROWTH,
            ("новый чартер", "new charter", "чартерный рейс"),
        ),
        (
            "New Destination",
            OpportunityType.SEGMENT,
            ("новое направление", "new destination"),
        ),
        (
            "Bonus Program",
            OpportunityType.REVENUE_GROWTH,
            ("бонусная программа", "бонусы за бронирование", "bonus program"),
        ),
        (
            "Hotel Promotion",
            OpportunityType.REVENUE_GROWTH,
            ("акция отеля", "hotel promotion", "hotel offer"),
        ),
        (
            "Flight Promotion",
            OpportunityType.REVENUE_GROWTH,
            ("акция на авиабилеты", "flight promotion", "flight offer"),
        ),
    )

    def __init__(
        self,
        knowledge_loader: KnowledgeLoader | None = None,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        """Инициализирует детектор с единым загрузчиком Knowledge Base."""
        self._knowledge_loader = knowledge_loader or KnowledgeLoader()
        self._entity_extractor = entity_extractor or EntityExtractor(self._knowledge_loader)

    def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
        """Возвращает все типы возможностей, подтверждённые одним сигналом."""
        text = self._input_text(input_data.raw_data)
        if not text:
            return []

        promo_keywords = self._promo_keywords()
        generic_promo_keywords = self._generic_promo_keywords(promo_keywords)
        promo_evidence = self._find_keywords(text, generic_promo_keywords)
        if not promo_evidence:
            return []

        entities = self._entity_extractor.extract(text)
        entity_values = self._entity_values(entities.to_dict())
        urgency_evidence = self._find_keywords(text, self._urgency_keywords())
        deadline_evidence = self._find_patterns(text, self._patterns("deadline_patterns"))
        discount_evidence = self._find_patterns(text, self._patterns("discount_patterns"))

        opportunities: list[BusinessOpportunity] = []
        for label, opportunity_type, keywords in self._TYPE_RULES:
            allowed_keywords = tuple(keyword for keyword in keywords if keyword in promo_keywords)
            type_evidence = self._find_keywords(text, allowed_keywords)
            if not type_evidence:
                continue

            evidence = self._unique(
                [*type_evidence, *promo_evidence, *discount_evidence, *deadline_evidence, *urgency_evidence]
            )
            opportunities.append(
                BusinessOpportunity(
                    title=label,
                    summary=self._summary(label, type_evidence, entities.deadline),
                    opportunity_type=opportunity_type,
                    source_signal_ids=[input_data.signal_id],
                    detected_entities=entity_values,
                    urgency=self._urgency(urgency_evidence, deadline_evidence),
                    confidence=self._confidence(type_evidence, promo_evidence, entity_values),
                    evidence=evidence,
                )
            )

        return opportunities

    def _promo_keywords(self) -> Sequence[str]:
        data = self._knowledge_loader.load("promo_keywords")
        if not isinstance(data, list) or not all(isinstance(value, str) for value in data):
            raise TypeError("Справочник 'promo_keywords' должен быть списком строк")
        return data

    @staticmethod
    def _generic_promo_keywords(promo_keywords: Sequence[str]) -> tuple[str, ...]:
        """Возвращает только общие промо-маркеры, подтверждённые Knowledge Base."""
        generic_markers = {
            "акция",
            "спецпредложение",
            "распродажа",
            "выгодн",
            "offer",
            "promotion",
            "sale",
            "promo",
        }
        return tuple(keyword for keyword in promo_keywords if keyword in generic_markers)

    def _urgency_keywords(self) -> Sequence[str]:
        data = self._knowledge_loader.load("urgency_keywords")
        if not isinstance(data, list) or not all(isinstance(value, str) for value in data):
            raise TypeError("Справочник 'urgency_keywords' должен быть списком строк")
        return data

    def _patterns(self, name: str) -> Sequence[str]:
        data = self._knowledge_loader.load(name)
        if not isinstance(data, Mapping) or not isinstance(data.get("patterns"), list):
            raise TypeError(f"Справочник '{name}' должен содержать список patterns")
        patterns = data["patterns"]
        if not all(isinstance(pattern, str) for pattern in patterns):
            raise TypeError(f"Справочник '{name}' должен содержать строковые patterns")
        return patterns

    @staticmethod
    def _input_text(raw_data: object) -> str:
        """Собирает текстовые поля сигнала без привязки к формату источника."""
        values: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, Mapping):
                for nested_value in value.values():
                    collect(nested_value)
            elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
                for nested_value in value:
                    collect(nested_value)

        collect(raw_data)
        return "\n".join(values)

    @staticmethod
    def _find_keywords(text: str, keywords: Sequence[str]) -> list[str]:
        return [
            keyword
            for keyword in keywords
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE)
        ]

    @staticmethod
    def _find_patterns(text: str, patterns: Sequence[str]) -> list[str]:
        evidence: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                evidence.append(match.group(0))
        return evidence

    @staticmethod
    def _entity_values(data: Mapping[str, object]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, values in data.items():
            if isinstance(values, list) and values:
                result[key] = [str(value) for value in values]
            elif key == "deadline" and isinstance(values, str):
                result[key] = [values]
        return result

    @staticmethod
    def _urgency(keyword_evidence: Sequence[str], deadline_evidence: Sequence[str]) -> UrgencyLevel:
        if any(value.casefold() in {"сегодня", "today", "до конца дня"} for value in keyword_evidence):
            return UrgencyLevel.CRITICAL
        if deadline_evidence or keyword_evidence:
            return UrgencyLevel.HIGH
        return UrgencyLevel.MEDIUM

    @staticmethod
    def _confidence(
        type_evidence: Sequence[str],
        promo_evidence: Sequence[str],
        entities: Mapping[str, Sequence[str]],
    ) -> ConfidenceLevel:
        if type_evidence and promo_evidence and any(
            values for key, values in entities.items() if key not in {"language"}
        ):
            return ConfidenceLevel.HIGH
        if type_evidence and promo_evidence:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    @staticmethod
    def _summary(label: str, evidence: Sequence[str], deadline: str | None) -> str:
        suffix = f"; дедлайн: {deadline}" if deadline else ""
        return f"Обнаружена возможность типа {label} по правилу: {', '.join(evidence)}{suffix}."

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        return [value for value in values if value and not (value in seen or seen.add(value))]