"""Детерминированные оценщики влияния на выручку.

Модуль не обращается к LLM, AI-моделям, CRM, истории продаж, внешним API,
базе данных или Pipeline. Денежный диапазон извлекается только из явно
указанного диапазона в доказательствах возможности.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    RevenueImpact,
    UrgencyLevel,
)


class NullRevenueEstimator:
    """Оценщик по умолчанию, не создающий неподтверждённых прогнозов."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> RevenueImpact | None:
        """Возвращает ``None`` до появления проверяемых правил оценки."""
        return None


class RuleBasedRevenueEstimator:
    """Строит RevenueImpact по прозрачным правилам без финансового прогноза.

    Числовая оценка допускается только когда строка ``evidence`` содержит
    полный денежный диапазон в одной валюте, например ``от 10 000 до 20 000 ₽``
    или ``10 000–20 000 RUB``. Суммы не вычисляются из типа возможности,
    срочности, сущностей или текстового описания.

    При отсутствии такого доказательства возвращается объект с пустыми
    границами: вызывающий код получает объяснимый статус ``unknown`` без
    выдуманной суммы.
    """

    _CURRENCY_CODES: dict[str, str] = {
        "₽": "RUB",
        "руб": "RUB",
        "руб.": "RUB",
        "рублей": "RUB",
        "rub": "RUB",
        "rur": "RUB",
        "$": "USD",
        "usd": "USD",
        "€": "EUR",
        "eur": "EUR",
    }
    _CURRENCY_PATTERN = r"₽|руб(?:\.|лей)?|rub|rur|\$|usd|€|eur"
    _NUMBER_PATTERN = r"\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)?"
    _RANGE_PATTERN = re.compile(
        rf"(?<!\w)(?:от\s+)?(?P<minimum>{_NUMBER_PATTERN})\s*"
        rf"(?:до|[-–—])\s*(?P<maximum>{_NUMBER_PATTERN})\s*"
        rf"(?P<currency>{_CURRENCY_PATTERN})(?!\w)",
        re.IGNORECASE,
    )

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> RevenueImpact:
        """Возвращает детерминированную оценку без изменения возможности или контекста."""
        match = self._first_explicit_range(opportunity.evidence)
        if match is None:
            return self._unknown_impact(opportunity)

        amount_min = self._parse_amount(match.group("minimum"))
        amount_max = self._parse_amount(match.group("maximum"))
        currency = self._normalize_currency(match.group("currency"))

        if amount_min > amount_max:
            return RevenueImpact(
                calculation_method="rule_based_explicit_evidence_range",
                explanation=(
                    "Явный денежный диапазон в evidence имеет обратный порядок "
                    "границ; оценка помечена как unknown."
                ),
                assumptions=[
                    "Диапазон не исправляется автоматически.",
                    "Нужен источник с границами в возрастающем порядке.",
                ],
            )

        return RevenueImpact(
            amount_min=amount_min,
            amount_max=amount_max,
            currency=currency,
            confidence=self._confidence(opportunity),
            calculation_method="rule_based_explicit_evidence_range",
            explanation=(
                "Диапазон извлечён из явно указанного денежного диапазона в evidence; "
                "оценщик не прогнозирует выручку и не изменяет указанную сумму."
            ),
            assumptions=[
                "Денежный диапазон в evidence относится к данной возможности.",
                "Валюта распознана по маркеру в той же строке evidence.",
                *self._context_assumptions(opportunity),
            ],
        )

    def _unknown_impact(self, opportunity: BusinessOpportunity) -> RevenueImpact:
        """Возвращает пустой диапазон при отсутствии проверяемой суммы."""
        return RevenueImpact(
            confidence=ConfidenceLevel.LOW,
            calculation_method="unknown_insufficient_explicit_evidence",
            explanation=(
                "Невозможно определить денежный диапазон: в evidence нет явного "
                "диапазона суммы с валютой. Значения не выводятся из косвенных признаков."
            ),
            assumptions=[
                "Тип возможности, срочность, сущности и уровень уверенности не являются "
                "денежными данными.",
                *self._context_assumptions(opportunity),
            ],
        )

    def _first_explicit_range(self, evidence: Iterable[str]) -> re.Match[str] | None:
        """Находит первый корректный диапазон в исходном порядке доказательств."""
        for value in evidence:
            match = self._RANGE_PATTERN.search(value)
            if match is not None:
                return match
        return None

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Преобразует явно записанную денежную сумму в число без округления."""
        return float(value.replace("\u00a0", "").replace(" ", "").replace(",", "."))

    def _normalize_currency(self, value: str) -> str:
        """Нормализует маркер валюты к трёхбуквенному коду."""
        return self._CURRENCY_CODES[value.casefold()]

    @staticmethod
    def _confidence(opportunity: BusinessOpportunity) -> ConfidenceLevel:
        """Понижает уверенность только по доступным качественным признакам."""
        if (
            opportunity.confidence == ConfidenceLevel.HIGH
            and opportunity.urgency in {UrgencyLevel.HIGH, UrgencyLevel.CRITICAL}
            and bool(opportunity.detected_entities)
        ):
            return ConfidenceLevel.HIGH
        if opportunity.confidence in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    @staticmethod
    def _context_assumptions(opportunity: BusinessOpportunity) -> list[str]:
        """Фиксирует только признаки, использованные для качественной уверенности."""
        opportunity_type = getattr(
            opportunity.opportunity_type,
            "value",
            str(opportunity.opportunity_type),
        )
        return [
            f"Тип возможности использован только для контекста: {opportunity_type}.",
            f"Срочность использована только для confidence: {opportunity.urgency.value}.",
            f"Исходный confidence возможности: {opportunity.confidence.value}.",
        ]
