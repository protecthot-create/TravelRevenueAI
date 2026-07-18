"""Структуры данных Intelligence Layer.

Модуль не зависит от pipeline и хранит только объяснимые, сериализуемые
результаты rule-based анализа сигнала.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum


class SignalPriority(StrEnum):
    """Дополнительный приоритет сигнала, не заменяющий Revenue Score."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class SignalContext:
    """Структурированный контекст, извлечённый из одного сигнала.

    Все поля предназначены для JSON metadata. Неизвестные значения остаются
    ``None`` или пустыми коллекциями, поэтому отсутствие признака не
    интерпретируется как отрицательный факт.
    """

    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    airlines: list[str] = field(default_factory=list)
    hotels: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    currencies: list[str] = field(default_factory=list)
    discounts: list[int] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    deadline: str | None = None
    priority: SignalPriority = SignalPriority.LOW
    entities: dict[str, list[str]] = field(default_factory=dict)
    language: str = "unknown"
    duplicates: dict[str, object] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, object]:
        """Возвращает JSON-совместимое представление контекста."""
        return asdict(self)


def serialize_date(value: date | None) -> str | None:
    """Сериализует дату в ISO-формат для JSON metadata."""
    return value.isoformat() if value is not None else None