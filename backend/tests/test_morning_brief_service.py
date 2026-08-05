"""Unit-тесты для MorningBriefService."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from travel_revenue_ai.services.decision_card_service import (
    CardStatus,
    DecisionCard,
    DecisionCardType,
    ImportanceLabel,
)
from travel_revenue_ai.services.morning_brief_service import MorningBriefService
from travel_revenue_ai.services.revenue_scoring_service import PriorityLabel


def _card(
    *,
    card_type: DecisionCardType,
    title: str,
    score: float,
    importance_label: ImportanceLabel,
    confidence_raw: float = 0.5,
    signal_id: UUID | None = None,
    generated_at: datetime | None = None,
    what_to_do: str = "Сделать действие",
    summary: str = "Краткое описание",
) -> DecisionCard:
    """Создаёт минимальную карточку для тестов morning brief."""
    return DecisionCard(
        card_type=card_type,
        title=title,
        summary=summary,
        money_effect_display="+10 000 ₽",
        importance_label=importance_label,
        why_it_matters="Почему это важно",
        what_to_do=what_to_do,
        deadline_display="сегодня",
        confidence_display="средняя",
        source_display="unit-test",
        status_display=CardStatus.active,
        signal_id=signal_id,
        score=score,
        priority_label=PriorityLabel.high,
        confidence_raw=confidence_raw,
        generated_at=generated_at or datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc),
        updated_at=generated_at or datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc),
    )


def test_generate_brief_selects_main_action_from_combined_opportunities_and_risks() -> None:
    """Главное действие выбирается из объединённого набора risks + opportunities."""
    service = MorningBriefService(default_date=date(2026, 7, 31))
    opportunity = _card(
        card_type=DecisionCardType.opportunity,
        title="Сильная возможность",
        score=95.0,
        importance_label=ImportanceLabel.critical,
        confidence_raw=0.9,
    )
    risk = _card(
        card_type=DecisionCardType.risk,
        title="Менее сильный риск",
        score=80.0,
        importance_label=ImportanceLabel.critical,
        confidence_raw=0.8,
    )

    result = service.generate_brief([risk, opportunity])

    assert result.main_action is not None
    assert result.main_action.title == "Сильная возможность"


def test_generate_brief_never_selects_market_insight_as_main_action() -> None:
    """Рыночный инсайт не становится главным действием даже при более высоком score."""
    service = MorningBriefService(default_date=date(2026, 7, 31))
    market_insight = _card(
        card_type=DecisionCardType.market_insight,
        title="Рынок перегрет",
        score=99.0,
        importance_label=ImportanceLabel.critical,
        confidence_raw=0.95,
    )
    opportunity = _card(
        card_type=DecisionCardType.opportunity,
        title="Рабочая возможность",
        score=70.0,
        importance_label=ImportanceLabel.high,
        confidence_raw=0.7,
    )

    result = service.generate_brief([market_insight, opportunity])

    assert result.main_action is not None
    assert result.main_action.title == "Рабочая возможность"
    assert all(card.title != result.main_action.title for card in result.market_insights)


def test_generate_brief_deduplicates_cards_by_signal_id_and_keeps_better_card() -> None:
    """Дубликаты по signal_id схлопываются с сохранением лучшей карточки."""
    service = MorningBriefService(default_date=date(2026, 7, 31))
    duplicate_signal_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    weaker = _card(
        card_type=DecisionCardType.opportunity,
        title="Дубликат",
        score=40.0,
        importance_label=ImportanceLabel.medium,
        confidence_raw=0.4,
        signal_id=duplicate_signal_id,
        what_to_do="Старое действие",
    )
    stronger = _card(
        card_type=DecisionCardType.opportunity,
        title="Дубликат",
        score=85.0,
        importance_label=ImportanceLabel.critical,
        confidence_raw=0.9,
        signal_id=duplicate_signal_id,
        what_to_do="Лучшее действие",
    )
    other = _card(
        card_type=DecisionCardType.risk,
        title="Отдельный риск",
        score=60.0,
        importance_label=ImportanceLabel.high,
        confidence_raw=0.6,
    )

    result = service.generate_brief([weaker, stronger, other])

    assert len(result.opportunities) == 1
    assert result.opportunities[0].what_to_do == "Лучшее действие"
    assert result.total_cards_processed == 3


def test_generate_brief_uses_importance_and_confidence_as_tie_breakers() -> None:
    """При равном score сервис использует importance, затем confidence."""
    service = MorningBriefService(default_date=date(2026, 7, 31))
    lower_priority = _card(
        card_type=DecisionCardType.opportunity,
        title="Ниже по важности",
        score=75.0,
        importance_label=ImportanceLabel.high,
        confidence_raw=0.95,
    )
    higher_priority = _card(
        card_type=DecisionCardType.risk,
        title="Выше по важности",
        score=75.0,
        importance_label=ImportanceLabel.critical,
        confidence_raw=0.40,
    )

    result = service.generate_brief([lower_priority, higher_priority])

    assert result.main_action is not None
    assert result.main_action.title == "Выше по важности"