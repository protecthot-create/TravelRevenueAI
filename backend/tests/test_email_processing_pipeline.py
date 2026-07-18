"""Unit-тесты production email processing pipeline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from travel_revenue_ai.models.signal import SignalTypeEnum
from travel_revenue_ai.services.email_normalizer_service import EmailNormalizerService
from travel_revenue_ai.services.email_signal_classifier import EmailSignalClassifier
from travel_revenue_ai.sources.email import EmailSourceAdapter
from travel_revenue_ai.sources.mock_email_provider import MockEmailMessage, MockEmailProvider


@pytest.fixture
def normalizer() -> EmailNormalizerService:
    """Создаёт нормализатор писем."""
    return EmailNormalizerService()


@pytest.fixture
def classifier() -> EmailSignalClassifier:
    """Создаёт rule-based классификатор."""
    return EmailSignalClassifier()


def _message(
    *,
    message_id: str,
    subject: str = "",
    body: str = "",
    signal_type: SignalTypeEnum = SignalTypeEnum.market,
) -> MockEmailMessage:
    """Создаёт письмо для тестового провайдера."""
    return MockEmailMessage(
        message_id=message_id,
        sender="partner@example.test",
        recipient="sales@agency.test",
        subject=subject,
        body=body,
        received_at=datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc),
        signal_type=signal_type,
    )


def test_normalizer_cleans_html_and_removes_signature(
    normalizer: EmailNormalizerService,
) -> None:
    """HTML-теги, служебный контент, подпись и лишние пробелы удаляются."""
    normalized_text = normalizer.normalize(
        subject="  Акция   на Турцию ",
        body=(
            "<html><head><style>.hidden { display: none; }</style></head>"
            "<body><p>Доступна <b>скидка 15%</b> на туры.</p>"
            "<script>alert('noise')</script><p>Успейте до пятницы.</p>"
            "<p>С уважением,<br>Отдел продаж</p></body></html>"
        ),
    )

    assert normalized_text == "Акция на Турцию Доступна скидка 15% на туры. Успейте до пятницы."


def test_normalizer_keeps_plain_text_and_normalizes_whitespace(
    normalizer: EmailNormalizerService,
) -> None:
    """Обычный текст сохраняется без потери смысла и с едиными пробелами."""
    normalized_text = normalizer.normalize(
        subject="Рынок ОАЭ",
        body="  Спрос \n\n вырос   на семейные туры.\r\n\n-- \nПодпись",
    )

    assert normalized_text == "Рынок ОАЭ Спрос вырос на семейные туры."


def test_empty_email_becomes_empty_market_signal() -> None:
    """Пустое письмо не падает и классифицируется нейтрально как market."""
    signal = EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=MockEmailProvider(messages=[_message(message_id="<empty@test>")]),
    ).collect_signals()[0]

    assert signal.raw_data["normalized_text"] == ""
    assert signal.signal_type == SignalTypeEnum.market


def test_email_without_subject_uses_body_for_classification() -> None:
    """Письмо без Subject обрабатывается по телу без ошибок."""
    signal = EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=MockEmailProvider(
            messages=[
                _message(
                    message_id="<without-subject@test>",
                    body="Поставщик предупредил: тарифы подорожают завтра.",
                )
            ]
        ),
    ).collect_signals()[0]

    assert signal.raw_data["subject"] == ""
    assert signal.raw_data["normalized_text"] == (
        "Поставщик предупредил: тарифы подорожают завтра."
    )
    assert signal.signal_type == SignalTypeEnum.risk


def test_russian_text_is_normalized_and_classified_as_opportunity() -> None:
    """Русский Unicode-текст сохраняется и проходит rule-based классификацию."""
    signal = EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=MockEmailProvider(
            messages=[
                _message(
                    message_id="<russian@test>",
                    subject="Раннее бронирование",
                    body="Доступна выгодная скидка на туры в Турцию.",
                )
            ]
        ),
    ).collect_signals()[0]

    assert signal.raw_data["normalized_text"] == (
        "Раннее бронирование Доступна выгодная скидка на туры в Турцию."
    )
    assert signal.signal_type == SignalTypeEnum.opportunity


def test_classifier_prioritizes_risk_over_opportunity(
    classifier: EmailSignalClassifier,
) -> None:
    """При конфликте правил риск имеет приоритет над возможностью."""
    assert (
        classifier.classify("Срочно: акция отменена, возможна потеря выручки.")
        == SignalTypeEnum.risk
    )


def test_adapter_processes_multiple_messages_in_source_order() -> None:
    """Несколько писем обрабатываются независимо и в исходном порядке."""
    signals = EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=MockEmailProvider(
            messages=[
                _message(
                    message_id="<opportunity@test>",
                    subject="Акция",
                    body="Доступна скидка на туры.",
                ),
                _message(
                    message_id="<risk@test>",
                    subject="Изменение тарифа",
                    body="Цены подорожают завтра.",
                ),
                _message(
                    message_id="<market@test>",
                    subject="Рынок",
                    body="Опубликована статистика спроса.",
                ),
            ]
        ),
    ).collect_signals()

    assert [signal.raw_data["message_id"] for signal in signals] == [
        "<opportunity@test>",
        "<risk@test>",
        "<market@test>",
    ]
    assert [signal.signal_type for signal in signals] == [
        SignalTypeEnum.opportunity,
        SignalTypeEnum.risk,
        SignalTypeEnum.market,
    ]
    assert [signal.raw_data["normalized_text"] for signal in signals] == [
        "Акция Доступна скидка на туры.",
        "Изменение тарифа Цены подорожают завтра.",
        "Рынок Опубликована статистика спроса.",
    ]