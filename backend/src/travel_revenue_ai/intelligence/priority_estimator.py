"""Дополнительная explainable-оценка приоритета сигнала."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from travel_revenue_ai.intelligence.context import SignalPriority
from travel_revenue_ai.knowledge.loader import KnowledgeLoader


class SignalPriorityEstimator:
    """Оценивает срочность и полезность без замены Revenue Score.

    Результат предназначен только для ``metadata.intelligence.priority``.
    Он не вызывает RevenueScoringService и не влияет на его формулу.
    """

    def __init__(self, knowledge_loader: KnowledgeLoader | None = None) -> None:
        """Инициализирует оценщик с единой точкой доступа к Knowledge Base."""
        self._knowledge_loader = knowledge_loader or KnowledgeLoader()

    def estimate(
        self,
        *,
        text: str,
        discounts: list[int],
        deadline: str | None,
        operators: list[str],
        reference_date: date | None = None,
    ) -> SignalPriority:
        """Возвращает HIGH, MEDIUM или LOW по наблюдаемым признакам."""
        score = 0
        lowered = text.casefold()

        if any(keyword in lowered for keyword in self._keywords("urgency_keywords")) or any(
            keyword in lowered for keyword in self._keywords("risk_keywords")
        ):
            score += 3
        elif any(keyword in lowered for keyword in self._keywords("promo_keywords")):
            score += 1

        if discounts:
            maximum_discount = max(discounts)
            if maximum_discount >= 20:
                score += 2
            elif maximum_discount >= 10:
                score += 1

        if operators:
            score += 1

        remaining_days = self._remaining_days(deadline, reference_date or date.today())
        if remaining_days is not None:
            if remaining_days <= 1:
                score += 3
            elif remaining_days <= 3:
                score += 2
            elif remaining_days <= 7:
                score += 1

        if score >= 4:
            return SignalPriority.HIGH
        if score >= 2:
            return SignalPriority.MEDIUM
        return SignalPriority.LOW

    def _keywords(self, name: str) -> Sequence[str]:
        """Возвращает валидированный список ключевых слов из Knowledge Base."""
        data = self._knowledge_loader.load(name)
        if not isinstance(data, list):
            raise TypeError(f"Справочник '{name}' должен быть списком ключевых слов")
        return data

    @staticmethod
    def _remaining_days(deadline: str | None, reference_date: date) -> int | None:
        """Возвращает число дней до ISO-дедлайна, если он валиден."""
        if deadline is None:
            return None
        try:
            return (date.fromisoformat(deadline) - reference_date).days
        except ValueError:
            return None