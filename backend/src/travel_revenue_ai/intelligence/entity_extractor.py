"""Rule-based извлечение сущностей из текстов туристических сигналов."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from travel_revenue_ai.knowledge.loader import KnowledgeLoader


@dataclass(frozen=True, slots=True)
class ExtractedEntities:
    """Результат извлечения признаков, пригодный для JSON metadata."""

    countries: list[str]
    cities: list[str]
    operators: list[str]
    airlines: list[str]
    hotels: list[str]
    directions: list[str]
    currencies: list[str]
    discounts: list[int]
    dates: list[str]
    deadline: str | None
    language: str

    def to_dict(self) -> dict[str, list[str] | list[int] | str | None]:
        """Преобразует результат к JSON-совместимому словарю."""
        return {
            "countries": self.countries,
            "cities": self.cities,
            "operators": self.operators,
            "airlines": self.airlines,
            "hotels": self.hotels,
            "directions": self.directions,
            "currencies": self.currencies,
            "discounts": self.discounts,
            "dates": self.dates,
            "deadline": self.deadline,
            "language": self.language,
        }


class EntityExtractor:
    """Извлекает туристические сущности через справочники Knowledge Base."""

    _ISO_DATE_PATTERN = re.compile(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b")
    _RU_DATE_PATTERN = re.compile(
        r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|"
        r"сентября|октября|ноября|декабря)\b",
        re.IGNORECASE,
    )
    _MONTHS = {
        "января": 1,
        "февраля": 2,
        "марта": 3,
        "апреля": 4,
        "мая": 5,
        "июня": 6,
        "июля": 7,
        "августа": 8,
        "сентября": 9,
        "октября": 10,
        "ноября": 11,
        "декабря": 12,
    }

    def __init__(self, knowledge_loader: KnowledgeLoader | None = None) -> None:
        """Инициализирует извлекатель с единой точкой доступа к справочникам."""
        self._knowledge_loader = knowledge_loader or KnowledgeLoader()

    def extract(self, text: str, *, reference_date: date | None = None) -> ExtractedEntities:
        """Извлекает сущности и даты из произвольного текста."""
        source = text or ""
        lowered = source.casefold()
        reference = reference_date or date.today()

        countries = self._find_dictionary_values(lowered, self._mapping("countries"))
        cities = self._find_dictionary_values(lowered, self._mapping("cities"))
        operators = self._find_dictionary_values(lowered, self._mapping("tour_operators"))
        airlines = self._find_dictionary_values(lowered, self._mapping("airlines"))
        hotels = self._find_dictionary_values(lowered, self._mapping("hotel_chains"))
        currencies = self._find_dictionary_values(lowered, self._mapping("currencies"))
        discounts = self._find_discounts(source)
        dates = self._find_dates(source, reference)
        deadline = self._find_deadline(source, reference)
        directions = self._unique(countries + cities)

        return ExtractedEntities(
            countries=countries,
            cities=cities,
            operators=operators,
            airlines=airlines,
            hotels=hotels,
            directions=directions,
            currencies=currencies,
            discounts=discounts,
            dates=dates,
            deadline=deadline,
            language=self._detect_language(source),
        )

    def _mapping(self, name: str) -> Mapping[str, str]:
        """Возвращает валидированный алиасный словарь из Knowledge Base."""
        data = self._knowledge_loader.load(name)
        if not isinstance(data, Mapping):
            raise TypeError(f"Справочник '{name}' должен быть словарём алиасов")
        return data

    def _patterns(self, name: str) -> Sequence[str]:
        """Возвращает валидированный набор регулярных выражений из Knowledge Base."""
        data = self._knowledge_loader.load(name)
        if not isinstance(data, Mapping) or not isinstance(data.get("patterns"), list):
            raise TypeError(f"Справочник '{name}' должен содержать список patterns")
        return data["patterns"]

    @staticmethod
    def _find_dictionary_values(text: str, dictionary: Mapping[str, str]) -> list[str]:
        return EntityExtractor._unique(
            value
            for keyword, value in dictionary.items()
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE)
        )

    def _find_discounts(self, text: str) -> list[int]:
        values: list[int] = []
        for pattern in self._patterns("discount_patterns"):
            values.extend(int(value) for value in re.findall(pattern, text, re.IGNORECASE))

        return sorted({value for value in values if 0 < value <= 100})

    def _find_dates(self, text: str, reference: date) -> list[str]:
        dates: list[str] = []
        for year, month, day in self._ISO_DATE_PATTERN.findall(text):
            try:
                dates.append(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                continue

        for day, month_name in self._RU_DATE_PATTERN.findall(text.casefold()):
            try:
                candidate = date(reference.year, self._MONTHS[month_name], int(day))
                if candidate < reference - timedelta(days=31):
                    candidate = candidate.replace(year=candidate.year + 1)
                dates.append(candidate.isoformat())
            except ValueError:
                continue

        return self._unique(dates)

    def _find_deadline(self, text: str, reference: date) -> str | None:
        for pattern in self._patterns("deadline_patterns"):
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            candidate = match.group(1) if match.lastindex else match.group(0)
            if candidate.casefold() in {"сегодня", "today"}:
                return reference.isoformat()
            if candidate.casefold() in {"завтра", "tomorrow"}:
                return (reference + timedelta(days=1)).isoformat()

            dates = self._find_dates(candidate, reference)
            if dates:
                return dates[0]

        return None

    @staticmethod
    def _detect_language(text: str) -> str:
        if re.search(r"[А-Яа-яЁё]", text):
            return "ru"
        if re.search(r"[A-Za-z]", text):
            return "en"
        return "unknown"

    @staticmethod
    def _unique(values: object) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:  # type: ignore[union-attr]
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result