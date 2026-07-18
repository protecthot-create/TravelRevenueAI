"""Unit-тесты TelegramSourceAdapter и MockTelegramProvider."""

from datetime import datetime, timezone
from uuid import uuid4

from travel_revenue_ai.models.signal import SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.sources.mock_telegram_provider import (
    MockTelegramMessage,
    MockTelegramProvider,
)
from travel_revenue_ai.sources.telegram import TelegramSourceAdapter


def test_collect_signals_converts_all_default_mock_messages() -> None:
    """Адаптер создаёт новый Signal для каждого тестового Telegram-сообщения."""
    agency_id = uuid4()
    source_id = uuid4()

    signals = TelegramSourceAdapter(agency_id=agency_id, source_id=source_id).collect_signals()

    assert len(signals) == 3
    assert [signal.signal_type for signal in signals] == [
        SignalTypeEnum.opportunity,
        SignalTypeEnum.risk,
        SignalTypeEnum.market,
    ]

    for signal in signals:
        assert signal.agency_id == agency_id
        assert signal.source_id == source_id
        assert signal.status == SignalStatusEnum.new
        assert signal.raw_data["channel"] == "telegram"
        assert isinstance(signal.raw_data["message_id"], int)
        assert isinstance(signal.raw_data["chat_id"], int)
        assert signal.raw_data["chat_title"]
        assert signal.raw_data["sender_name"]
        assert signal.raw_data["text"]
        assert signal.raw_data["sent_at"]


def test_collect_signals_preserves_raw_telegram_fields() -> None:
    """Адаптер переносит поля сообщения в JSON-совместимый raw_data."""
    message = MockTelegramMessage(
        message_id=777,
        chat_id=-100555777,
        chat_title="Партнёрские тарифы",
        sender_name="Туроператор",
        text="Поставщик предупредил об изменении тарифа.",
        sent_at=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
        signal_type=SignalTypeEnum.risk,
    )
    provider = MockTelegramProvider(messages=[message])

    signal = TelegramSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=provider,
    ).collect_signals()[0]

    assert signal.signal_type == SignalTypeEnum.risk
    assert signal.status == SignalStatusEnum.new
    assert signal.raw_data == {
        "channel": "telegram",
        "message_id": 777,
        "chat_id": -100555777,
        "chat_title": "Партнёрские тарифы",
        "sender_name": "Туроператор",
        "text": "Поставщик предупредил об изменении тарифа.",
        "sent_at": "2026-07-17T10:00:00+00:00",
    }


def test_mock_provider_returns_a_copy_of_messages() -> None:
    """Внешнее изменение результата fetch_messages не меняет провайдер."""
    provider = MockTelegramProvider()

    messages = provider.fetch_messages()
    messages.clear()

    assert len(provider.fetch_messages()) == 3