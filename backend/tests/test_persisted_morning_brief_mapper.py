"""Unit-тесты чистых mapper-контрактов persisted MorningBrief."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

import pytest

from travel_revenue_ai.mappers.persisted_morning_brief_mapper import (
    json_safe,
    money_to_decimal,
)
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    NumericDecisionCardMappingError,
    PersistedMorningBriefMappingError,
)


class SnapshotKind(str, Enum):
    """Тестовое перечисление для JSON snapshot."""

    test = "test"


def test_money_to_decimal_uses_string_conversion_and_half_up_rounding() -> None:
    """Финансовое значение нормализуется без Decimal(float)."""
    assert money_to_decimal("12.345") == Decimal("12.35")
    assert money_to_decimal("-12.345") == Decimal("-12.35")
    assert money_to_decimal(12.3) == Decimal("12.30")


@pytest.mark.parametrize(
    "value",
    [
        True,
        "NaN",
        "Infinity",
        "-Infinity",
        "1000000000000.00",
    ],
)
def test_money_to_decimal_rejects_invalid_or_unrepresentable_values(value: object) -> None:
    """Некорректные значения не проходят в Numeric(14,2)."""
    with pytest.raises(NumericDecisionCardMappingError):
        money_to_decimal(value)


def test_json_safe_recursively_serializes_snapshot_values() -> None:
    """UUID, Decimal, даты и Enum не остаются в историческом JSON."""
    identifier = uuid.uuid4()
    value = {
        "uuid": identifier,
        "money": Decimal("12.30"),
        "date": date(2026, 7, 23),
        "timestamp": datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc),
        "kind": SnapshotKind.test,
        "nested": (Decimal("1.00"), {"id": identifier}),
    }

    snapshot = json_safe(value)

    assert snapshot == {
        "uuid": str(identifier),
        "money": "12.30",
        "date": "2026-07-23",
        "timestamp": "2026-07-23T09:00:00+00:00",
        "kind": "test",
        "nested": ["1.00", {"id": str(identifier)}],
    }
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_json_safe_rejects_unsupported_snapshot_value() -> None:
    """Неподдерживаемые объекты не сериализуются неявно."""
    with pytest.raises(PersistedMorningBriefMappingError):
        json_safe(object())