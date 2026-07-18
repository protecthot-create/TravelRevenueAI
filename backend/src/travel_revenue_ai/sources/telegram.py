"""Адаптер получения сырых сигналов из Telegram-источника."""

from typing import Any
from uuid import UUID

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum
from travel_revenue_ai.sources.base import BaseSourceAdapter
from travel_revenue_ai.sources.mock_telegram_provider import MockTelegramProvider
from travel_revenue_ai.sources.provider_contracts import TelegramMessage, TelegramProvider


class TelegramSourceAdapter(BaseSourceAdapter):
    """Преобразует сообщения MockTelegramProvider в новые сырые сигналы.

    Адаптер ограничен ingestion-слоем: он не выполняет подключение к Telegram API,
    не сохраняет сигналы в БД и не запускает обработку PipelineService.
    """

    def __init__(
        self,
        *,
        agency_id: UUID,
        source_id: UUID | None,
        provider: TelegramProvider | None = None,
        config: dict[str, Any] | None = None,
        adapter_name: str = "telegram",
    ) -> None:
        """Инициализирует адаптер и тестовый источник Telegram-сообщений."""
        super().__init__(
            adapter_name=adapter_name,
            agency_id=agency_id,
            source_id=source_id,
            config=config,
        )
        self._provider = provider or MockTelegramProvider()

    def collect_signals(self) -> list[Signal]:
        """Собирает сообщения и создаёт по одному новому Signal на каждое из них."""
        return [self._to_signal(message) for message in self._provider.fetch_messages()]

    def _to_signal(self, message: TelegramMessage) -> Signal:
        """Преобразует одно сырое сообщение в неприкреплённый объект Signal."""
        return Signal(
            agency_id=self.agency_id,
            source_id=self.source_id,
            signal_type=message.signal_type,
            status=SignalStatusEnum.new,
            raw_data={
                "channel": "telegram",
                "message_id": message.message_id,
                "chat_id": message.chat_id,
                "chat_title": message.chat_title,
                "sender_name": message.sender_name,
                "text": message.text,
                "sent_at": message.sent_at.isoformat(),
            },
        )