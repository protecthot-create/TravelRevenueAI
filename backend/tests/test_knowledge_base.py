"""Unit-тесты Knowledge Base и её использования Intelligence Layer."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from travel_revenue_ai.intelligence import EntityExtractor, SignalPriority, SignalPriorityEstimator
from travel_revenue_ai.knowledge.loader import KnowledgeLoader
from travel_revenue_ai.knowledge.validator import KnowledgeValidationError, KnowledgeValidator


class StubKnowledgeLoader:
    """Минимальный загрузчик для проверки зависимости Intelligence Layer от KB."""

    def __init__(self, dictionaries: dict[str, dict[str, Any] | list[str]]) -> None:
        self.dictionaries = dictionaries
        self.requested_names: list[str] = []

    def load(self, name: str) -> dict[str, Any] | list[str]:
        self.requested_names.append(name)
        return self.dictionaries[name]


def test_loader_loads_all_required_dictionaries() -> None:
    """Загрузчик читает и валидирует весь обязательный комплект справочников."""
    loader = KnowledgeLoader()

    knowledge = loader.load_all()

    assert set(knowledge) == set(KnowledgeLoader.DICTIONARY_NAMES)
    assert knowledge["countries"]["турция"] == "Турция"
    assert "срочно" in knowledge["urgency_keywords"]


def test_loader_returns_cached_dictionary_until_cache_is_cleared(tmp_path: Path) -> None:
    """Повторная загрузка использует кэш, а clear_cache выполняет перезагрузку."""
    countries_path = tmp_path / "countries.json"
    countries_path.write_text('{"test": "Первое значение"}', encoding="utf-8")
    loader = KnowledgeLoader(data_directory=tmp_path)

    first = loader.load("countries")
    countries_path.write_text('{"test": "Второе значение"}', encoding="utf-8")
    cached = loader.load("countries")

    assert cached is first
    assert cached["test"] == "Первое значение"

    loader.clear_cache()
    reloaded = loader.load("countries")

    assert reloaded["test"] == "Второе значение"
    assert reloaded is not first


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        ("promo_keywords", ["Акция", " акция "], "дублирующиеся"),
        ("countries", {"": "Турция"}, "пустой ключ"),
    ],
)
def test_validator_rejects_duplicates_and_empty_records(
    name: str,
    payload: dict[str, str] | list[str],
    message: str,
) -> None:
    """Валидатор не принимает дубликаты и пустые записи."""
    with pytest.raises(KnowledgeValidationError, match=message):
        KnowledgeValidator().validate(name, payload)


def test_validator_rejects_broken_json(tmp_path: Path) -> None:
    """Валидатор преобразует ошибку синтаксиса JSON в доменную ошибку."""
    path = tmp_path / "countries.json"
    path.write_text('{"турция": ', encoding="utf-8")

    with pytest.raises(KnowledgeValidationError, match="битый JSON"):
        KnowledgeValidator().load_and_validate("countries", path)


def test_validator_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    """Повторяющиеся ключи JSON не перезаписываются молча."""
    path = tmp_path / "countries.json"
    path.write_text('{"турция": "Турция", "турция": "Turkey"}', encoding="utf-8")

    with pytest.raises(KnowledgeValidationError, match="дубликат ключа JSON"):
        KnowledgeValidator().load_and_validate("countries", path)


def test_entity_extractor_uses_injected_knowledge_loader() -> None:
    """EntityExtractor получает алиасы и паттерны исключительно из переданной KB."""
    loader = StubKnowledgeLoader(
        {
            "countries": {"тестляндия": "Тестляндия"},
            "cities": {},
            "tour_operators": {},
            "airlines": {},
            "hotel_chains": {},
            "currencies": {},
            "discount_patterns": {"patterns": [r"\bвыгода\s+(\d{1,3})\b"]},
            "deadline_patterns": {"patterns": [r"\b(?:сегодня)\b"]},
        }
    )

    entities = EntityExtractor(loader).extract(
        "Тестляндия: выгода 37, оформить сегодня",
        reference_date=date(2026, 7, 18),
    )

    assert entities.countries == ["Тестляндия"]
    assert entities.discounts == [37]
    assert entities.deadline == "2026-07-18"
    assert set(loader.requested_names) == {
        "countries",
        "cities",
        "tour_operators",
        "airlines",
        "hotel_chains",
        "currencies",
        "discount_patterns",
        "deadline_patterns",
    }


def test_priority_estimator_uses_injected_knowledge_loader() -> None:
    """SignalPriorityEstimator берёт ключевые слова только из переданной KB."""
    loader = StubKnowledgeLoader(
        {
            "urgency_keywords": ["экстренный_маркер"],
            "risk_keywords": ["риск_маркер"],
            "promo_keywords": ["промо_маркер"],
        }
    )

    priority = SignalPriorityEstimator(loader).estimate(
        text="Экстренный_маркер",
        discounts=[],
        deadline=None,
        operators=[],
        reference_date=date(2026, 7, 18),
    )

    assert priority is SignalPriority.MEDIUM
    assert loader.requested_names == ["urgency_keywords"]
