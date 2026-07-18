"""Проверка целостности JSON-справочников Knowledge Base."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class KnowledgeValidationError(ValueError):
    """Справочник Knowledge Base имеет некорректный формат."""


class KnowledgeValidator:
    """Валидирует структуру, пустые значения и дубликаты справочников."""

    _MAPPING_DICTIONARIES = frozenset(
        {"countries", "cities", "tour_operators", "airlines", "hotel_chains", "currencies"}
    )
    _KEYWORD_DICTIONARIES = frozenset({"promo_keywords", "risk_keywords", "urgency_keywords"})
    _PATTERN_DICTIONARIES = frozenset({"discount_patterns", "deadline_patterns"})

    def load_and_validate(self, name: str, path: Path) -> dict[str, Any] | list[str]:
        """Загружает один JSON-файл и сразу проверяет его структуру."""
        try:
            with path.open(encoding="utf-8") as source:
                data = json.load(source, object_pairs_hook=self._unique_object)
        except FileNotFoundError as error:
            raise KnowledgeValidationError(f"Справочник '{name}' не найден: {path}") from error
        except json.JSONDecodeError as error:
            raise KnowledgeValidationError(
                f"Справочник '{name}' содержит битый JSON: {error.msg}"
            ) from error

        self.validate(name, data)
        if isinstance(data, dict | list):
            return data
        raise KnowledgeValidationError(f"Справочник '{name}' имеет неподдерживаемый тип данных")

    def validate(self, name: str, data: object) -> None:
        """Проверяет данные одного известного справочника."""
        if name in self._MAPPING_DICTIONARIES:
            self._validate_mapping(name, data)
            return
        if name in self._KEYWORD_DICTIONARIES:
            self._validate_keywords(name, data)
            return
        if name in self._PATTERN_DICTIONARIES:
            self._validate_patterns(name, data)
            return
        raise KnowledgeValidationError(f"Неизвестный справочник Knowledge Base: '{name}'")

    @staticmethod
    def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        """Не допускает дублирующиеся ключи, которые json обычно перезаписывает."""
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise KnowledgeValidationError(f"Обнаружен дубликат ключа JSON: '{key}'")
            result[key] = value
        return result

    def _validate_mapping(self, name: str, data: object) -> None:
        """Проверяет словарь алиасов и канонических значений."""
        mapping = self._require_mapping(name, data)
        if not mapping:
            raise KnowledgeValidationError(f"Справочник '{name}' не должен быть пустым")
        self._validate_nonempty_strings(name, mapping, "ключ")
        self._validate_nonempty_strings(name, mapping.values(), "значение")
        self._validate_duplicates(name, mapping.keys())

    def _validate_keywords(self, name: str, data: object) -> None:
        """Проверяет список ключевых слов."""
        self._validate_duplicates(name, self._require_string_list(name, data))

    def _validate_patterns(self, name: str, data: object) -> None:
        """Проверяет конфигурацию регулярных выражений и номеров месяцев."""
        mapping = self._require_mapping(name, data)
        self._validate_duplicates(name, self._require_string_list(name, mapping.get("patterns")))

        months = mapping.get("months")
        if months is None:
            return

        month_mapping = self._require_mapping(name, months)
        self._validate_nonempty_strings(name, month_mapping, "ключ месяца")
        for month, number in month_mapping.items():
            if not isinstance(number, int) or not 1 <= number <= 12:
                raise KnowledgeValidationError(
                    f"Справочник '{name}' содержит некорректный номер месяца для '{month}'"
                )

    @staticmethod
    def _require_mapping(name: str, data: object) -> Mapping[str, Any]:
        """Возвращает JSON-объект или бросает понятную ошибку структуры."""
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError(f"Справочник '{name}' должен быть JSON-объектом")
        return data

    @staticmethod
    def _require_string_list(name: str, data: object) -> list[str]:
        """Возвращает непустой массив строк или бросает понятную ошибку."""
        if not isinstance(data, list) or not data:
            raise KnowledgeValidationError(
                f"Справочник '{name}' должен быть непустым JSON-массивом строк"
            )
        if any(not isinstance(value, str) or not value.strip() for value in data):
            raise KnowledgeValidationError(f"Справочник '{name}' содержит пустую или нестроковую запись")
        return data

    @staticmethod
    def _validate_nonempty_strings(name: str, values: object, label: str) -> None:
        """Проверяет, что все значения и ключи являются непустыми строками."""
        if any(not isinstance(value, str) or not value.strip() for value in values):  # type: ignore[union-attr]
            raise KnowledgeValidationError(f"Справочник '{name}' содержит пустой {label}")

    @staticmethod
    def _validate_duplicates(name: str, values: object) -> None:
        """Ищет дубликаты без учёта регистра и начальных/конечных пробелов."""
        normalized = [value.casefold().strip() for value in values]  # type: ignore[union-attr]
        if len(normalized) != len(set(normalized)):
            raise KnowledgeValidationError(f"Справочник '{name}' содержит дублирующиеся записи")