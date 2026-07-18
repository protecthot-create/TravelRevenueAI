"""Unit-тесты EmailSourceAdapter и MockEmailProvider."""

from datetime import datetime, timezone
from uuid import uuid4

from travel_revenue_ai.models.signal import SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.sources.email import EmailSourceAdapter
from travel_revenue_ai.sources.mock_email_provider import MockEmailMessage, MockEmailProvider


def test_collect_signals_converts_all_default_mock_messages() -> None:
    """Адаптер создаёт новый Signal для каждого тестового письма."""
    agency_id = uuid4()
    source_id = uuid4()

    signals = EmailSourceAdapter(agency_id=agency_id, source_id=source_id).collect_signals()

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
        assert signal.raw_data["channel"] == "email"
        assert signal.raw_data["message_id"]
        assert signal.raw_data["subject"]
        assert signal.raw_data["body"]
        assert signal.raw_data["received_at"]


def test_collect_signals_preserves_raw_email_fields() -> None:
    """Адаптер переносит поля конкретного письма в JSON-совместимый raw_data."""
    message = MockEmailMessage(
        message_id="<custom-message@example.test>",
        sender="operator@example.test",
        recipient="sales@agency.test",
        subject="Проверьте стоимость авиабилетов",
        body="Поставщик предупредил об изменении тарифа.",
        received_at=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
        signal_type=SignalTypeEnum.risk,
    )
    provider = MockEmailProvider(messages=[message])

    signal = EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=provider,
    ).collect_signals()[0]

    assert signal.signal_type == SignalTypeEnum.risk
    assert signal.status == SignalStatusEnum.new
    assert signal.raw_data == {
        "channel": "email",
        "message_id": "<custom-message@example.test>",
        "from": "operator@example.test",
        "to": "sales@agency.test",
        "subject": "Проверьте стоимость авиабилетов",
        "body": "Поставщик предупредил об изменении тарифа.",
        "normalized_text": (
            "Проверьте стоимость авиабилетов "
            "Поставщик предупредил об изменении тарифа."
        ),
        "received_at": "2026-07-17T10:00:00+00:00",
    }


def test_mock_provider_returns_a_copy_of_messages() -> None:
    """Внешнее изменение результата fetch_messages не меняет провайдер."""
    provider = MockEmailProvider()

    messages = provider.fetch_messages()
    messages.clear()

    assert len(provider.fetch_messages()) == 3