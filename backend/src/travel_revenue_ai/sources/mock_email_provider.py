"""Тестовый провайдер email-сообщений без подключения к IMAP."""

from dataclasses import dataclass
from datetime import datetime, timezone

from travel_revenue_ai.models.signal import SignalTypeEnum


@dataclass(frozen=True, slots=True)
class MockEmailMessage:
    """Сырым письмом, полученным от почтового провайдера."""

    message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: datetime
    signal_type: SignalTypeEnum


class MockEmailProvider:
    """Возвращает преднастроенные письма для локальной разработки и тестов.

    Провайдер намеренно не выполняет сетевые запросы, не хранит состояние и не
    меняет письма. Реальный IMAP-клиент будет добавлен только в отдельном спринте.
    """

    def __init__(self, messages: list[MockEmailMessage] | None = None) -> None:
        """Инициализирует провайдер переданными или демонстрационными письмами."""
        self._messages = list(messages) if messages is not None else self._build_default_messages()

    def fetch_messages(self) -> list[MockEmailMessage]:
        """Возвращает копию списка доступных писем."""
        return list(self._messages)

    @staticmethod
    def _build_default_messages() -> list[MockEmailMessage]:
        """Создаёт несколько реалистичных писем для разработки адаптера."""
        return [
            MockEmailMessage(
                message_id="<turkey-early-booking@example.test>",
                sender="partners@tour-operator.test",
                recipient="sales@agency.test",
                subject="Раннее бронирование Турции: цены вырастут через 14 дней",
                body=(
                    "С 1 августа цены на летние туры в Турцию вырастут. "
                    "До повышения доступны места по текущему тарифу."
                ),
                received_at=datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.opportunity,
            ),
            MockEmailMessage(
                message_id="<egypt-flight-price@example.test>",
                sender="alerts@flight-provider.test",
                recipient="sales@agency.test",
                subject="Изменение тарифа: билеты в Египет подорожают завтра",
                body=(
                    "Тарифы на рейсы Москва — Хургада изменятся 18 июля. "
                    "Проверьте активные предложения и пересчитайте маржу."
                ),
                received_at=datetime(2026, 7, 17, 8, 15, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.risk,
            ),
            MockEmailMessage(
                message_id="<uae-demand-trend@example.test>",
                sender="analytics@market-data.test",
                recipient="sales@agency.test",
                subject="Рынок ОАЭ: растёт спрос на семейные туры",
                body=(
                    "За последнюю неделю спрос на семейные поездки в ОАЭ вырос. "
                    "Данные требуют последующей нормализации и оценки."
                ),
                received_at=datetime(2026, 7, 17, 8, 30, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.market,
            ),
        ]