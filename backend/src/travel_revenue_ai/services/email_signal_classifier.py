"""Rule-based классификация нормализованных email-сигналов."""

from __future__ import annotations

from collections.abc import Mapping

from travel_revenue_ai.models.signal import SignalTypeEnum


class EmailSignalClassifier:
    """Классифицирует RU/EN письма по взвешенным правилам без AI.

    Веса позволяют различать сильные и фоновые формулировки, а синонимы делают
    правила устойчивее к вариациям текстов поставщиков и операторов.
    """

    _RULES: Mapping[SignalTypeEnum, Mapping[str, int]] = {
        SignalTypeEnum.risk: {
            "риск": 5,
            "потер": 5,
            "убыт": 5,
            "штраф": 5,
            "отмен": 5,
            "срочно": 4,
            "немедленно": 4,
            "закрыт": 4,
            "ограничен": 4,
            "предупрежд": 3,
            "подорожа": 3,
            "рост цен": 3,
            "тариф": 2,
            "risk": 5,
            "loss": 5,
            "penalt": 5,
            "cancel": 5,
            "urgent": 4,
            "immediately": 4,
            "closed": 4,
            "restriction": 4,
            "warning": 3,
            "price increase": 3,
            "fare increase": 3,
            "surcharge": 3,
        },
        SignalTypeEnum.opportunity: {
            "возможност": 4,
            "прибыл": 4,
            "выручк": 4,
            "заработ": 4,
            "скидк": 3,
            "акци": 3,
            "спецпредлож": 4,
            "раннее бронирован": 4,
            "повышенный спрос": 3,
            "рост спроса": 3,
            "доступн": 2,
            "выгодн": 3,
            "продаж": 2,
            "opportunit": 4,
            "profit": 4,
            "revenue": 4,
            "discount": 3,
            "promotion": 3,
            "special offer": 4,
            "early booking": 4,
            "high demand": 3,
            "demand growth": 3,
            "available": 2,
            "advantageous": 3,
            "sales": 2,
        },
        SignalTypeEnum.market: {
            "рынок": 3,
            "тренд": 3,
            "спрос": 2,
            "курс валют": 3,
            "валют": 2,
            "аналитик": 2,
            "статистик": 2,
            "прогноз": 2,
            "направлен": 2,
            "туризм": 2,
            "market": 3,
            "trend": 3,
            "demand": 2,
            "exchange rate": 3,
            "currency": 2,
            "analytics": 2,
            "statistics": 2,
            "forecast": 2,
            "destination": 2,
            "tourism": 2,
        },
    }

    def classify(self, normalized_text: str) -> SignalTypeEnum:
        """Возвращает тип с максимальной суммой сработавших весов.

        При равном score риск имеет приоритет над возможностью, так как потеря
        денег важнее одинаковой по силе возможности. Пустое и неизвестное письмо
        остаётся market, как в предыдущей реализации.
        """
        text = normalized_text.casefold()
        scores = {
            signal_type: self._score(text, rules)
            for signal_type, rules in self._RULES.items()
        }

        highest_score = max(scores.values())
        if highest_score == 0:
            return SignalTypeEnum.market

        for signal_type in (
            SignalTypeEnum.risk,
            SignalTypeEnum.opportunity,
            SignalTypeEnum.market,
        ):
            if scores[signal_type] == highest_score:
                return signal_type

        return SignalTypeEnum.market

    @staticmethod
    def _score(text: str, rules: Mapping[str, int]) -> int:
        """Суммирует веса всех совпавших ключевых слов и синонимов."""
        return sum(weight for pattern, weight in rules.items() if pattern in text)