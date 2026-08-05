"""Сервис генерации Morning Brief (Morning Brief Generator).

Формирует ежедневный брифинг из приоритетных Decision Card:
- top-5 возможностей;
- top-3 рисков;
- все рыночные инсайты;
- главное действие дня;
- краткий summary.

Spec: docs/system_architecture.md (секция 6), docs/decision_card_spec.md (секция 9),
docs/data_model.md (секция 5), docs/morning_brief.md

Архитектурные решения:
- MorningBriefResult, BriefSummary — dataclass пользовательского слоя (не ORM-модель).
- MorningBriefService принимает список DecisionCard, возвращает MorningBriefResult.
- Генерация текстов — по шаблонам, без LLM.
- Не зависит от FastAPI, работает только с доменными структурами.
- Не изменяет существующие сервисы (RevenueScoringService, FilteringService, DecisionCardService).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from travel_revenue_ai.services.decision_card_service import (
    CardStatus,
    DecisionCard,
    DecisionCardType,
    ImportanceLabel,
)


# =============================================================================
# Типы и перечисления
# =============================================================================


class BriefSection(str, Enum):
    """Секции брифа."""

    opportunities = "opportunities"
    risks = "risks"
    market_insights = "market_insights"
    main_action = "main_action"


# =============================================================================
# Результирующие структуры
# =============================================================================


@dataclass(frozen=True)
class BriefSummary:
    """Краткий summary брифа — сгенерированный текст для отображения."""

    # Заголовок брифа с датой
    title: str

    # Секция возможностей
    opportunities_header: str
    opportunities_intro: str
    opportunities_footer: str

    # Секция рисков
    risks_header: str
    risks_intro: str
    risks_footer: str

    # Секция рыночных инсайтов
    market_header: str
    market_intro: str

    # Главное действие
    main_action_header: str
    main_action_body: str

    # Итоговая строка
    closing: str

    # Полный текст для отображения
    full_text: str

    @classmethod
    def from_cards(
        cls,
        brief_date: date,
        opportunities: list[DecisionCard],
        risks: list[DecisionCard],
        market_insights: list[DecisionCard],
        main_action: DecisionCard | None,
    ) -> BriefSummary:
        """Генерирует BriefSummary из списка карточек."""
        date_str = brief_date.strftime("%d.%m.%Y")

        # Заголовок
        title = f"🌅 УТРЕННИЙ БРИФ — {date_str}"

        # Секция возможностей
        opp_count = len(opportunities)
        if opp_count > 0:
            opp_header = "💰 ВОЗМОЖНОСТИ"
            opp_intro = f"Топ-{opp_count} приоритетных возможностей на сегодня:"
            opp_footer = ""
        else:
            opp_header = "💰 ВОЗМОЖНОСТИ"
            opp_intro = "Сегодня нет приоритетных возможностей."
            opp_footer = ""

        # Секция рисков
        risk_count = len(risks)
        if risk_count > 0:
            risk_header = "⚠️ РИСКИ"
            risk_intro = f"Топ-{risk_count} рисков, требующих внимания:"
            risk_footer = ""
        else:
            risk_header = "⚠️ РИСКИ"
            risk_intro = "Сегодня нет критических рисков."
            risk_footer = ""

        # Секция рыночных инсайтов
        if market_insights:
            market_header = "📊 ЧТО ПРОИСХОДИТ НА РЫНКЕ"
            market_intro = "Ключевые рыночные сигналы:"
        else:
            market_header = "📊 РЫНОК"
            market_intro = "Нет новых значимых рыночных сигналов."

        # Главное действие
        if main_action:
            main_action_header = "🎯 ГЛАВНОЕ ДЕЙСТВИЕ"
            main_action_body = main_action.what_to_do
        else:
            main_action_header = "🎯 ГЛАВНОЕ ДЕЙСТВИЕ"
            main_action_body = "Нет приоритетного действия на сегодня."

        # Закрывающий текст
        closing = "—"

        # Формируем полный текст
        full_parts = [
            title,
            "",
            opp_header,
            "─" * 50,
            opp_intro,
        ]

        for i, card in enumerate(opportunities, 1):
            full_parts.append(f"{i}. {card.title} — {card.money_effect_display}")
            full_parts.append(f"   Что: {card.what_to_do}")
            full_parts.append(f"   Дедлайн: {card.deadline_display}")

        if opp_footer:
            full_parts.append(opp_footer)

        full_parts.extend(["", risk_header, "─" * 50, risk_intro])

        for i, card in enumerate(risks, 1):
            full_parts.append(f"{i}. {card.title} — {card.money_effect_display}")
            full_parts.append(f"   Что: {card.what_to_do}")
            full_parts.append(f"   Дедлайн: {card.deadline_display}")

        if risk_footer:
            full_parts.append(risk_footer)

        full_parts.extend(["", market_header, "─" * 50, market_intro])

        for card in market_insights:
            full_parts.append(f"• {card.title}: {card.summary}")

        full_parts.extend(["", main_action_header, "─" * 50, main_action_body, "", closing])

        full_text = "\n".join(full_parts)

        return cls(
            title=title,
            opportunities_header=opp_header,
            opportunities_intro=opp_intro,
            opportunities_footer=opp_footer,
            risks_header=risk_header,
            risks_intro=risk_intro,
            risks_footer=risk_footer,
            market_header=market_header,
            market_intro=market_intro,
            main_action_header=main_action_header,
            main_action_body=main_action_body,
            closing=closing,
            full_text=full_text,
        )


@dataclass
class MorningBriefResult:
    """Результат генерации Morning Brief — основной output сервиса."""

    # Метаданные
    brief_id: uuid.UUID = field(default_factory=uuid.uuid4)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    date: date = field(default_factory=date.today)

    # Отсортированные карточки
    opportunities: list[DecisionCard] = field(default_factory=list)
    risks: list[DecisionCard] = field(default_factory=list)
    market_insights: list[DecisionCard] = field(default_factory=list)

    # Главное действие дня
    main_action: DecisionCard | None = None

    # Сгенерированный summary
    summary: BriefSummary | None = None

    # Счётчики для аналитики
    total_cards_processed: int = 0
    opportunities_count: int = 0
    risks_count: int = 0
    market_insights_count: int = 0

    def to_display_dict(self) -> dict[str, Any]:
        """Возвращает словарь для отображения в UI."""
        return {
            "brief_id": str(self.brief_id),
            "date": self.date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "opportunities": [card.to_display_dict() for card in self.opportunities],
            "risks": [card.to_display_dict() for card in self.risks],
            "market_insights": [card.to_display_dict() for card in self.market_insights],
            "main_action": self.main_action.to_display_dict() if self.main_action else None,
            "summary_text": self.summary.full_text if self.summary else "",
            "summary": (
                {
                    "title": self.summary.title,
                    "opportunities_header": self.summary.opportunities_header,
                    "opportunities_intro": self.summary.opportunities_intro,
                    "risks_header": self.summary.risks_header,
                    "risks_intro": self.summary.risks_intro,
                    "market_header": self.summary.market_header,
                    "market_intro": self.summary.market_intro,
                    "main_action_header": self.summary.main_action_header,
                    "main_action_body": self.summary.main_action_body,
                }
                if self.summary
                else None
            ),
            "stats": {
                "total_cards_processed": self.total_cards_processed,
                "opportunities_count": self.opportunities_count,
                "risks_count": self.risks_count,
                "market_insights_count": self.market_insights_count,
            },
        }

    def to_morning_brief_dict(self) -> dict[str, Any]:
        """Возвращает словарь для сохранения в ORM-модель MorningBrief."""
        return {
            "top_opportunities": [card.decision_card_id for card in self.opportunities],
            "top_risks": [card.decision_card_id for card in self.risks],
            "main_action_id": self.main_action.decision_card_id if self.main_action else None,
            "summary_text": self.summary.full_text if self.summary else "",
        }


# =============================================================================
# Шаблоны для выбора главного действия
# =============================================================================


MAIN_ACTION_SELECTION_RULES = """
Правила выбора главного действия дня:
1. Сначала сравниваем общий бизнес-приоритет карточки.
2. Приоритет определяется через score, важность, уверенность и стабильные тай-брейки.
3. Сравнение всегда происходит только внутри объединенного набора opportunities + risks.
4. Market insights никогда не выбираются как главное действие.
"""


# =============================================================================
# Morning Brief Service
# =============================================================================


class MorningBriefService:
    """Сервис генерации Morning Brief.

    Принимает список DecisionCard и генерирует готовый MorningBriefResult
    с приоритетными возможностями, рисками и главным действием дня.

    Spec: docs/system_architecture.md (секция 6)
    """

    # Лимиты согласно спецификации
    MAX_OPPORTUNITIES: int = 5
    MAX_RISKS: int = 3

    def __init__(self, default_date: date | None = None) -> None:
        """Инициализирует сервис.

        Args:
            default_date: Дата брифа. По умолчанию — сегодня.
        """
        self.default_date = default_date or date.today()

    def generate_brief(
        self,
        cards: list[DecisionCard],
        brief_date: date | None = None,
    ) -> MorningBriefResult:
        """Генерирует MorningBriefResult из списка DecisionCard.

        Процесс:
        1. Валидирует входные карточки.
        2. Дедуплицирует карточки.
        3. Разделяет карточки по типам.
        4. Сортирует каждую группу по score (descending).
        5. Ограничивает opportunities и risks лимитами сервиса.
        6. Выбирает главное действие дня из opportunities + risks по общей политике.
        7. Генерирует summary текст.

        Args:
            cards: Список DecisionCard для включения в бриф.
            brief_date: Дата брифа. По умолчанию — из __init__ или сегодня.

        Returns:
            MorningBriefResult с отсортированными карточками и summary.

        Raises:
            ValueError: Если cards содержит невалидные элементы.
        """
        if cards is None:
            cards = []

        # Валидация входных данных
        valid_cards = [card for card in cards if isinstance(card, DecisionCard)]

        if len(valid_cards) != len(cards):
            invalid_count = len(cards) - len(valid_cards)
            # Невалидные карточки тихо пропускаем, чтобы не ломать генерацию брифа.
            _ = invalid_count

        # Сначала убираем дубликаты, потом строим итоговые группы.
        deduplicated_cards = self._deduplicate_cards(valid_cards)

        # Разделяем по типам
        opportunities = self._filter_by_type(
            deduplicated_cards, DecisionCardType.opportunity
        )
        risks = self._filter_by_type(deduplicated_cards, DecisionCardType.risk)
        market_insights = self._filter_by_type(
            deduplicated_cards, DecisionCardType.market_insight
        )

        # Сортируем по score (descending)
        opportunities = self._sort_by_score(opportunities)
        risks = self._sort_by_score(risks)
        market_insights = self._sort_by_score(market_insights)

        # Ограничиваем лимитами
        top_opportunities = opportunities[: self.MAX_OPPORTUNITIES]
        top_risks = risks[: self.MAX_RISKS]

        # Выбираем главное действие
        main_action = self._select_main_action(top_opportunities, top_risks)

        # Генерируем summary
        summary = BriefSummary.from_cards(
            brief_date=brief_date or self.default_date,
            opportunities=top_opportunities,
            risks=top_risks,
            market_insights=market_insights,
            main_action=main_action,
        )

        # Формируем результат
        result = MorningBriefResult(
            date=brief_date or self.default_date,
            opportunities=top_opportunities,
            risks=top_risks,
            market_insights=market_insights,
            main_action=main_action,
            summary=summary,
            total_cards_processed=len(valid_cards),
            opportunities_count=len(top_opportunities),
            risks_count=len(top_risks),
            market_insights_count=len(market_insights),
        )

        return result

    def _filter_by_type(
        self,
        cards: list[DecisionCard],
        card_type: DecisionCardType,
    ) -> list[DecisionCard]:
        """Фильтрует карточки по типу."""
        return [card for card in cards if card.card_type == card_type]

    def _sort_by_score(self, cards: list[DecisionCard]) -> list[DecisionCard]:
        """Сортирует карточки по score (descending)."""
        return sorted(cards, key=lambda c: c.score, reverse=True)

    def _select_main_action(
        self,
        opportunities: list[DecisionCard],
        risks: list[DecisionCard],
    ) -> DecisionCard | None:
        """Выбирает главное действие дня по общей бизнес-приоритетной политике.

        В выбор входят только итоговые opportunities и risks.
        Market insights никогда не участвуют в выборе главного действия.
        """
        candidates = [*risks, *opportunities]

        if not candidates:
            return None

        return max(candidates, key=self._business_priority_key)

    def _business_priority_key(
        self,
        card: DecisionCard,
    ) -> tuple[float, int, float, datetime, uuid.UUID]:
        """Возвращает детерминированный ключ бизнес-приоритета.

        Порядок сравнения:
        1. score
        2. importance_label
        3. confidence_raw
        4. generated_at
        5. decision_card_id
        """
        return (
            card.score,
            self._priority_label_rank(card.importance_label),
            card.confidence_raw,
            card.generated_at,
            card.decision_card_id,
        )

    def _priority_label_rank(self, importance_label: ImportanceLabel) -> int:
        """Преобразует importance_label в числовой ранг."""
        priority_map = {
            ImportanceLabel.critical: 4,
            ImportanceLabel.high: 3,
            ImportanceLabel.medium: 2,
            ImportanceLabel.low: 1,
        }
        return priority_map.get(importance_label, 0)

    def _deduplicate_cards(
        self,
        cards: list[DecisionCard],
    ) -> list[DecisionCard]:
        """Удаляет дубликаты карточек, сохраняя лучшую по бизнес-приоритету."""
        deduplicated: dict[str, DecisionCard] = {}

        for card in cards:
            key = self._build_dedup_key(card)
            existing = deduplicated.get(key)
            if existing is None or self._is_better_card(card, existing):
                deduplicated[key] = card

        return list(deduplicated.values())

    def _build_dedup_key(self, card: DecisionCard) -> str:
        """Строит ключ дедупликации для карточки."""
        if card.signal_id is not None:
            return f"signal:{card.signal_id}"

        parts = [
            card.card_type.value,
            card.title.strip().lower(),
            card.what_to_do.strip().lower(),
            card.summary.strip().lower(),
        ]
        return "|".join(parts)

    def _is_better_card(self, current: DecisionCard, existing: DecisionCard) -> bool:
        """Определяет, какая из двух карточек лучше."""
        return self._business_priority_key(current) > self._business_priority_key(existing)

    def generate_brief_from_filtered(
        self,
        cards: list[DecisionCard],
        brief_date: date | None = None,
    ) -> MorningBriefResult:
        """Генерирует бриф только из активных карточек.

        Фильтрует карточки по статусу active перед генерацией.

        Args:
            cards: Список DecisionCard.
            brief_date: Дата брифа.

        Returns:
            MorningBriefResult с только активными карточками.
        """
        active_cards = [
            card for card in cards if card.status_display == CardStatus.active
        ]
        return self.generate_brief(active_cards, brief_date)

    def generate_empty_brief(
        self,
        brief_date: date | None = None,
    ) -> MorningBriefResult:
        """Генерирует пустой бриф (когда нет карточек).

        Используется когда нет данных для формирования брифа.

        Args:
            brief_date: Дата брифа.

        Returns:
            MorningBriefResult с пустыми списками и дефолтным summary.
        """
        return self.generate_brief([], brief_date)