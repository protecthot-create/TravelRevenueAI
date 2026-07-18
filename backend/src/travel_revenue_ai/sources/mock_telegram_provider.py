"""Тестовый провайдер Telegram-сообщений без подключения к Telegram API."""

from dataclasses import dataclass
from datetime import datetime, timezone

from travel_revenue_ai.models.signal import SignalTypeEnum


@dataclass(frozen=True, slots=True)
class MockTelegramMessage:
    """Сырым сообщением, полученным от Telegram-провайдера."""

    message_id: int
    chat_id: int
    chat_title: str
    sender_name: str
    text: str
    sent_at: datetime
    signal_type: SignalTypeEnum


class MockTelegramProvider:
    """Возвращает преднастроенные сообщения для локальной разработки и тестов.

    Провайдер намеренно не выполняет сетевые запросы, не хранит состояние и не
    меняет сообщения. Реальный Telegram-клиент будет добавлен только в отдельном
    спринте.
    """

    def __init__(self, messages: list[MockTelegramMessage] | None = None) -> None:
        """Инициализирует провайдер переданными или демонстрационными сообщениями."""
        self._messages = list(messages) if messages is not None else self._build_default_messages()

    def fetch_messages(self) -> list[MockTelegramMessage]:
        """Возвращает копию списка доступных Telegram-сообщений."""
        return list(self._messages)

    @staticmethod
    def _build_default_messages() -> list[MockTelegramMessage]:
        """Создаёт несколько реалистичных сообщений для разработки адаптера."""
        return [
            MockTelegramMessage(
                message_id=101,
                chat_id=-100120001,
                chat_title="Туроператор: акции и цены",
                sender_name="Отдел поддержки партнёров",
                text=(
                    "До конца недели действует раннее бронирование Турции. "
                    "На популярные отели осталось ограниченное количество мест."
                ),
                sent_at=datetime(2026, 7, 17, 8, 45, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.opportunity,
            ),
            MockTelegramMessage(
                message_id=102,
                chat_id=-100120002,
                chat_title="Авиатарифы: срочные уведомления",
                sender_name="Система тарифных уведомлений",
                text=(
                    "Завтра с 09:00 повышаются тарифы на рейсы в Хургаду. "
                    "Проверьте активные предложения и пересчитайте маржу."
                ),
                sent_at=datetime(2026, 7, 17, 9, 0, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.risk,
            ),
            MockTelegramMessage(
                message_id=103,
                chat_id=-100120003,
                chat_title="Рынок туризма",
                sender_name="Аналитический канал",
                text=(
                    "Растёт интерес к семейным турам в ОАЭ. "
                    "Данные требуют последующей нормализации и оценки."
                ),
                sent_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.market,
            ),
        ]