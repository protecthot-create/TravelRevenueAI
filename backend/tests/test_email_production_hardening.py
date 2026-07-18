"""Регрессионные тесты production hardening для email ingestion."""

from datetime import datetime, timezone
from uuid import uuid4

from travel_revenue_ai.models.signal import SignalTypeEnum
from travel_revenue_ai.services.email_deduplication_service import EmailDeduplicationService
from travel_revenue_ai.services.email_ingestion_metrics import EmailIngestionMetrics
from travel_revenue_ai.services.email_normalizer_service import EmailNormalizerService
from travel_revenue_ai.services.email_signal_classifier import EmailSignalClassifier
from travel_revenue_ai.sources.email import EmailSourceAdapter
from travel_revenue_ai.sources.mock_email_provider import MockEmailMessage, MockEmailProvider


def _message(
    *,
    message_id: str,
    subject: str = "",
    body: str = "",
) -> MockEmailMessage:
    """Создаёт тестовое письмо без зависимости от бизнес-слоя."""
    return MockEmailMessage(
        message_id=message_id,
        sender="partner@example.test",
        recipient="sales@agency.test",
        subject=subject,
        body=body,
        received_at=datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc),
        signal_type=SignalTypeEnum.market,
    )


def _adapter(
    messages: list[MockEmailMessage],
    *,
    deduplication_service: EmailDeduplicationService | None = None,
    metrics: EmailIngestionMetrics | None = None,
) -> EmailSourceAdapter:
    """Создаёт изолированный email-адаптер для проверки ingestion."""
    return EmailSourceAdapter(
        agency_id=uuid4(),
        source_id=uuid4(),
        provider=MockEmailProvider(messages=messages),
        deduplication_service=deduplication_service,
        metrics=metrics,
    )


def test_repeated_message_is_not_converted_to_second_signal() -> None:
    """Повторный запуск с тем же Message-ID не создаёт второй Signal."""
    message = _message(
        message_id="<repeated@test>",
        subject="Акция",
        body="Доступна скидка на туры.",
    )
    deduplication_service = EmailDeduplicationService()
    adapter = _adapter([message], deduplication_service=deduplication_service)

    assert len(adapter.collect_signals()) == 1
    assert adapter.collect_signals() == []


def test_duplicate_message_id_is_skipped_and_counted() -> None:
    """Два письма с идентичным Message-ID дают один Signal и корректные метрики."""
    metrics = EmailIngestionMetrics()
    signals = _adapter(
        [
            _message(
                message_id="<duplicate@test>",
                subject="Акция",
                body="Доступна скидка.",
            ),
            _message(
                message_id="<DUPLICATE@test>",
                subject="Другая тема",
                body="Повтор доставки.",
            ),
        ],
        metrics=metrics,
    ).collect_signals()

    assert len(signals) == 1
    assert metrics.snapshot() == {
        "emails_received": 2,
        "emails_processed": 1,
        "emails_skipped": 1,
        "emails_failed": 0,
        "signals_created": 1,
    }


def test_normalizer_removes_html_and_reply_chain() -> None:
    """Из HTML удаляются теги и процитированная цепочка переписки."""
    normalized_text = EmailNormalizerService().normalize(
        subject="Обновление тарифа",
        body=(
            "<div>Цена вырастет завтра.</div>"
            "<div>On Tue, 16 Jul 2026 at 10:00, Support wrote:</div>"
            "<blockquote><p>Старое сообщение со скидкой.</p></blockquote>"
        ),
    )

    assert normalized_text == "Обновление тарифа Цена вырастет завтра."
    assert "Старое сообщение" not in normalized_text


def test_normalizer_removes_html_footer_and_disclaimer() -> None:
    """Из HTML сохраняется полезный текст без footer и disclaimer."""
    normalized_text = EmailNormalizerService().normalize(
        subject="Спецпредложение",
        body=(
            "<p>Доступна скидка 20% на раннее бронирование.</p>"
            "<footer>Отписаться от рассылки</footer>"
            "<p>This email is confidential and intended only for the recipient.</p>"
        ),
    )

    assert normalized_text == "Спецпредложение Доступна скидка 20% на раннее бронирование."
    assert "Отписаться" not in normalized_text
    assert "confidential" not in normalized_text.casefold()


def test_classifier_classifies_russian_email_as_opportunity() -> None:
    """Русские синонимы правил классифицируются как opportunity."""
    classifier = EmailSignalClassifier()

    assert (
        classifier.classify("Выгодное спецпредложение: скидка на раннее бронирование.")
        == SignalTypeEnum.opportunity
    )


def test_classifier_classifies_english_email_as_risk() -> None:
    """Английские синонимы правил классифицируются как risk."""
    classifier = EmailSignalClassifier()

    assert (
        classifier.classify("Urgent warning: fare increase and cancellation penalty tomorrow.")
        == SignalTypeEnum.risk
    )


def test_classifier_classifies_unknown_email_as_market() -> None:
    """Неизвестное письмо остаётся нейтральным market-сигналом."""
    assert EmailSignalClassifier().classify("Hello, please see the attached document.") == (
        SignalTypeEnum.market
    )


def test_very_large_email_is_bounded_without_losing_processing() -> None:
    """Очень большое письмо ограничивается и не ломает создание Signal."""
    body = "Доступна скидка. " + ("полезный текст " * 20_000)

    signal = _adapter(
        [
            _message(
                message_id="<large@test>",
                subject="Акция",
                body=body,
            )
        ]
    ).collect_signals()[0]

    assert len(signal.raw_data["normalized_text"]) == EmailNormalizerService.MAX_NORMALIZED_LENGTH
    assert signal.signal_type == SignalTypeEnum.opportunity