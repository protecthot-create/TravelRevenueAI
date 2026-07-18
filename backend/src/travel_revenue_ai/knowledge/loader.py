"""Единая точка загрузки и кэширования Knowledge Base."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from travel_revenue_ai.knowledge.validator import KnowledgeValidator


class KnowledgeLoader:
    """Загружает, валидирует и кэширует JSON-справочники Knowledge Base."""

    DICTIONARY_NAMES = (
        "countries",
        "cities",
        "tour_operators",
        "airlines",
        "hotel_chains",
        "currencies",
        "promo_keywords",
        "risk_keywords",
        "urgency_keywords",
        "discount_patterns",
        "deadline_patterns",
    )

    def __init__(
        self,
        data_directory: Path | None = None,
        *,
        validator: KnowledgeValidator | None = None,
    ) -> None:
        """Инициализирует загрузчик с опциональным каталогом для тестов."""
        self._data_directory = data_directory or Path(__file__).with_name("data")
        self._validator = validator or KnowledgeValidator()
        self._cache: dict[str, dict[str, Any] | list[str]] = {}

    def load_all(self) -> Mapping[str, dict[str, Any] | list[str]]:
        """Загружает все обязательные справочники и возвращает кэш."""
        for name in self.DICTIONARY_NAMES:
            self.load(name)
        return self._cache

    def load(self, name: str) -> dict[str, Any] | list[str]:
        """Возвращает валидированный справочник, используя кэш после первого чтения."""
        if name not in self.DICTIONARY_NAMES:
            raise KeyError(f"Неизвестный справочник Knowledge Base: '{name}'")

        if name not in self._cache:
            self._cache[name] = self._validator.load_and_validate(
                name,
                self._data_directory / f"{name}.json",
            )
        return self._cache[name]

    def clear_cache(self) -> None:
        """Очищает кэш для контролируемой перезагрузки справочников."""
        self._cache.clear()