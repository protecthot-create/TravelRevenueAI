"""Сервис генерации Decision Card (Decision Card Generator).

Превращает результат фильтрации (FilterResult) в готовую для пользователя карточку
решения с заголовком, описанием, денежным эффектом, объяснением важности и действием.

Spec: docs/decision_card_spec.md, docs/data_model.md (секция 4)

Архитектурные решения:
- DecisionCard — dataclass пользовательского слоя (не ORM-модель).
- DecisionCardService принимает FilterResult и ScoreResult, возвращает DecisionCard.
- Генерация текстов — по шаблонам из decision_card_spec.md, без LLM.
- Не зависит от FastAPI, работает только с доменными структурами.
- Не изменяет существующие сервисы (RevenueScoringService, FilteringService).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from travel_revenue_ai.models.signal import SignalTypeEnum
from travel_revenue_ai.services.filtering_service import FilterResult
from travel_revenue_ai.services.revenue_scoring_service import PriorityLabel, ScoreResult


# =============================================================================
# Типы и перечисления
# =============================================================================


class DecisionCardType(str, Enum):
    """Тип карточки решения согласно спецификации."""

    opportunity = "Opportunity"
    risk = "Risk"
    market_insight = "Market Insight"
    operational_insight = "Operational Insight"


class ImportanceLabel(str, Enum):
    """Уровень важности для отображения пользователю."""

    critical = "Критический"
    high = "Высокий"
    medium = "Средний"
    low = "Низкий"


class CardStatus(str, Enum):
    """Статус карточки решения."""

    active = "active"
    done = "done"
    dismissed = "dismissed"


# =============================================================================
# Вспомогательные структуры
# =============================================================================


@dataclass(frozen=True)
class MoneyEffect:
    """Денежный эффект для отображения в карточке."""

    value: float
    formatted: str
    is_positive: bool
    is_forecast: bool = False
    is_at_risk: bool = False

    @classmethod
    def from_signal_data(
        cls,
        money_effect: float,
        probability: float,
        card_type: DecisionCardType,
    ) -> MoneyEffect:
        """Создаёт MoneyEffect из данных сигнала."""
        is_positive = card_type in (
            DecisionCardType.opportunity,
            DecisionCardType.market_insight,
            DecisionCardType.operational_insight,
        )
        is_forecast = probability < 0.70
        is_at_risk = card_type == DecisionCardType.risk
        abs_value = abs(money_effect)
        formatted = cls._format(abs_value, is_positive, is_forecast, is_at_risk)
        return cls(
            value=money_effect,
            formatted=formatted,
            is_positive=is_positive,
            is_forecast=is_forecast,
            is_at_risk=is_at_risk,
        )

    @staticmethod
    def _format(
        abs_value: float,
        is_positive: bool,
        is_forecast: bool,
        is_at_risk: bool,
    ) -> str:
        """Формирует отформатированную строку денежного эффекта."""
        if abs_value >= 1_000:
            display = f"+{int(abs_value):,} ₽".replace(",", " ")
        else:
            display = f"+{int(abs_value)} ₽"

        if not is_positive:
            display = display.replace("+", "-")

        if is_forecast and is_positive:
            display = f"до {display}"

        if is_at_risk:
            display = f"под угрозой {abs_value:,.0f} ₽".replace(",", " ").replace("+", "")

        return display


@dataclass(frozen=True)
class ActionItem:
    """Одно конкретное действие из блока «Что сделать»."""

    description: str
    deadline: str | None = None
    time_estimate_minutes: int | None = None


# =============================================================================
# Decision Card — пользовательский слой
# =============================================================================


@dataclass
class DecisionCard:
    """Карточка решения — основной продуктовый объект."""

    # Пользовательский слой
    card_type: DecisionCardType
    title: str
    summary: str
    money_effect_display: str
    importance_label: ImportanceLabel
    why_it_matters: str
    what_to_do: str
    deadline_display: str
    confidence_display: str
    source_display: str
    status_display: CardStatus = CardStatus.active

    # Внутренний слой
    decision_card_id: uuid.UUID = field(default_factory=uuid.uuid4)
    signal_id: uuid.UUID | None = None
    score: float = 0.0
    priority_label: PriorityLabel = PriorityLabel.low
    filter_result: str = "pass"
    breakdown: dict[str, Any] = field(default_factory=dict)
    reasoning_trace: str = ""
    applicable_modifiers: dict[str, float] = field(default_factory=dict)
    confidence_raw: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    feedback_state: str = "pending"
    audit_metadata: dict[str, Any] = field(default_factory=dict)

    def to_display_dict(self) -> dict[str, Any]:
        """Возвращает только пользовательский слой для отображения."""
        return {
            "card_type": self.card_type.value,
            "title": self.title,
            "summary": self.summary,
            "money_effect_display": self.money_effect_display,
            "importance_label": self.importance_label.value,
            "why_it_matters": self.why_it_matters,
            "what_to_do": self.what_to_do,
            "deadline_display": self.deadline_display,
            "confidence_display": self.confidence_display,
            "source_display": self.source_display,
            "status_display": self.status_display.value,
        }


# =============================================================================
# Шаблоны генерации текстов
# =============================================================================

DEFAULT_TITLES: dict[DecisionCardType, str] = {
    DecisionCardType.opportunity: "Новая возможность",
    DecisionCardType.risk: "Обнаружен риск",
    DecisionCardType.market_insight: "Рыночный сигнал",
    DecisionCardType.operational_insight: "Операционное улучшение",
}

WHY_IT_MATTERS_TEMPLATES: dict[DecisionCardType, str] = {
    DecisionCardType.opportunity: (
        "Спрос по направлению растёт, а время на продажу ограничено. "
        "Если действовать сейчас, можно успеть попасть в волну спроса."
    ),
    DecisionCardType.risk: (
        "Если не среагировать сейчас, можно потерять маржу "
        "по уже активным заявкам."
    ),
    DecisionCardType.market_insight: (
        "Рост интереса может увеличить поток заявок, "
        "если подготовить предложение заранее."
    ),
    DecisionCardType.operational_insight: "Оптимизация процесса сэкономит время и снизит риск ошибок.",
}

WHAT_TO_DO_TEMPLATES: dict[DecisionCardType, str] = {
    DecisionCardType.opportunity: "Отправить рассылку по базе клиентов и обновить баннеры на сайте.",
    DecisionCardType.risk: "Пересчитать маржу, предупредить менеджеров и обновить текущие предложения.",
    DecisionCardType.market_insight: "Подготовить актуальное предложение и усилить видимость направления.",
    DecisionCardType.operational_insight: "Внедрить предложенное улучшение в рабочий процесс.",
}

DEADLINE_TEMPLATES: dict[str, str] = {
    "critical": "Немедленно",
    "high": "сегодня",
    "medium": "в течение 2–3 дней",
    "low": "на этой неделе",
    "default": "когда будет возможность",
}

CONFIDENCE_TEMPLATES: dict[str, str] = {
    "high": "высокая",
    "medium": "средняя",
    "low": "низкая",
    "default": "средняя",
}

PRIORITY_TO_IMPORTANCE: dict[PriorityLabel, ImportanceLabel] = {
    PriorityLabel.critical: ImportanceLabel.critical,
    PriorityLabel.high: ImportanceLabel.high,
    PriorityLabel.medium: ImportanceLabel.medium,
    PriorityLabel.low: ImportanceLabel.low,
    PriorityLabel.noise: ImportanceLabel.low,
}

SIGNAL_TYPE_TO_CARD_TYPE: dict[SignalTypeEnum, DecisionCardType] = {
    SignalTypeEnum.opportunity: DecisionCardType.opportunity,
    SignalTypeEnum.risk: DecisionCardType.risk,
    SignalTypeEnum.market: DecisionCardType.market_insight,
    SignalTypeEnum.operational: DecisionCardType.operational_insight,
}


# =============================================================================
# Decision Card Service
# =============================================================================


class DecisionCardService:
    """Сервис генерации Decision Card."""

    def __init__(self, default_source: str = "рыночный сигнал") -> None:
        self.default_source = default_source

    def generate_card(
        self,
        filter_result: FilterResult,
        score_result: ScoreResult,
        signal_data: dict[str, Any] | None = None,
    ) -> DecisionCard:
        """Генерирует DecisionCard из результата фильтрации и оценки."""
        if filter_result is None:
            raise ValueError("filter_result не может быть None")
        if score_result is None:
            raise ValueError("score_result не может быть None")

        signal_data = signal_data or {}

        card_type = self._determine_card_type(signal_data)
        title = self._generate_title(card_type, signal_data)
        summary = self._generate_summary(card_type, signal_data)
        money_effect_display = self._generate_money_effect_display(card_type, signal_data)
        importance_label = self._map_importance(score_result.priority_label)
        why_it_matters = self._generate_why_it_matters(card_type, signal_data, score_result)
        what_to_do = self._generate_what_to_do(card_type, signal_data)
        deadline_display = self._generate_deadline(score_result, signal_data)
        confidence_display = self._generate_confidence(score_result.confidence)
        source_display = self._get_source_display(signal_data)

        return DecisionCard(
            card_type=card_type,
            title=title,
            summary=summary,
            money_effect_display=money_effect_display,
            importance_label=importance_label,
            why_it_matters=why_it_matters,
            what_to_do=what_to_do,
            deadline_display=deadline_display,
            confidence_display=confidence_display,
            source_display=source_display,
            signal_id=filter_result.signal_id,
            score=score_result.score,
            priority_label=score_result.priority_label,
            filter_result=filter_result.decision.value,
            breakdown={
                "money_score": score_result.breakdown.money_score,
                "urgency_score": score_result.breakdown.urgency_score,
                "probability_score": score_result.breakdown.probability_score,
                "controllability_score": score_result.breakdown.controllability_score,
            },
            reasoning_trace=score_result.reason,
            applicable_modifiers=score_result.breakdown.modifiers_applied,
            confidence_raw=score_result.confidence,
        )

    def _determine_card_type(self, signal_data: dict[str, Any]) -> DecisionCardType:
        """Определяет тип карточки на основе данных сигнала."""
        signal_type = signal_data.get("signal_type")
        if signal_type:
            try:
                return SIGNAL_TYPE_TO_CARD_TYPE[SignalTypeEnum(signal_type)]
            except (ValueError, KeyError):
                pass
        return DecisionCardType.opportunity

    def _generate_title(self, card_type: DecisionCardType, signal_data: dict[str, Any]) -> str:
        """Генерирует заголовок карточки."""
        if signal_data.get("title"):
            return str(signal_data["title"])
        return DEFAULT_TITLES.get(card_type, "Новая возможность")

    def _generate_summary(self, card_type: DecisionCardType, signal_data: dict[str, Any]) -> str:
        """Генерирует краткое описание."""
        if signal_data.get("summary"):
            return str(signal_data["summary"])

        summaries = {
            DecisionCardType.opportunity: "Спрос растёт, окно для действий ограничено.",
            DecisionCardType.risk: "Цена может измениться в ближайшее время.",
            DecisionCardType.market_insight: "Поисковый интерес по направлению вырос.",
            DecisionCardType.operational_insight: "Обнаружено улучшение в процессе.",
        }
        return summaries.get(card_type, "Новый сигнал для анализа.")

    def _generate_money_effect_display(
        self,
        card_type: DecisionCardType,
        signal_data: dict[str, Any],
    ) -> str:
        """Генерирует отображение денежного эффекта."""
        money_effect = float(signal_data.get("money_effect", 0.0))
        probability = float(signal_data.get("probability", 0.5))
        effect = MoneyEffect.from_signal_data(
            money_effect=money_effect,
            probability=probability,
            card_type=card_type,
        )
        return effect.formatted

    def _map_importance(self, priority_label: PriorityLabel) -> ImportanceLabel:
        """Маппит внутренний PriorityLabel в пользовательский ImportanceLabel."""
        return PRIORITY_TO_IMPORTANCE.get(priority_label, ImportanceLabel.low)

    def _generate_why_it_matters(
        self,
        card_type: DecisionCardType,
        signal_data: dict[str, Any],
        score_result: ScoreResult,
    ) -> str:
        """Генерирует блок «Почему это важно»."""
        if signal_data.get("why_important"):
            return str(signal_data["why_important"])

        template = WHY_IT_MATTERS_TEMPLATES.get(card_type, "")
        deadline = signal_data.get("deadline")
        if deadline and score_result.priority_label == PriorityLabel.critical:
            template = f"{template} Дедлайн близко."
        return template

    def _generate_what_to_do(self, card_type: DecisionCardType, signal_data: dict[str, Any]) -> str:
        """Генерирует блок «Что сделать»."""
        if signal_data.get("what_to_do"):
            return str(signal_data["what_to_do"])
        return WHAT_TO_DO_TEMPLATES.get(card_type, "Обработать сигнал.")

    def _generate_deadline(self, score_result: ScoreResult, signal_data: dict[str, Any]) -> str:
        """Генерирует отображение дедлайна."""
        if signal_data.get("deadline"):
            return str(signal_data["deadline"])
        priority_key = score_result.priority_label.value
        return DEADLINE_TEMPLATES.get(priority_key, DEADLINE_TEMPLATES["default"])

    def _generate_confidence(self, confidence: float) -> str:
        """Генерирует отображение уверенности."""
        if confidence >= 0.70:
            return CONFIDENCE_TEMPLATES["high"]
        if confidence >= 0.40:
            return CONFIDENCE_TEMPLATES["medium"]
        return CONFIDENCE_TEMPLATES["low"]

    def _get_source_display(self, signal_data: dict[str, Any]) -> str:
        """Возвращает источник сигнала для отображения."""
        if signal_data.get("source"):
            return str(signal_data["source"])
        return self.default_source

    def generate_cards(
        self,
        items: list[tuple[FilterResult, ScoreResult, dict[str, Any] | None]],
    ) -> list[DecisionCard]:
        """Пакетная генерация карточек для набора результатов."""
        cards: list[DecisionCard] = []
        for filter_result, score_result, signal_data in items:
            cards.append(self.generate_card(filter_result, score_result, signal_data))
        return cards