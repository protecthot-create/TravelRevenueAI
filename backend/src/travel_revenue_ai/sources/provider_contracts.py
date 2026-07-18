"""Контракты провайдеров источников данных.

Адаптеры зависят от этих протоколов, а не от конкретных mock- или production-
реализаций. Реальные провайдеры будут добавляться в следующих спринтах.
"""

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from travel_revenue_ai.models.signal import SignalTypeEnum


@runtime_checkable
class EmailMessage(Protocol):
    """Минимальная структура письма, необходимая email-адаптеру."""

    message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: datetime
    signal_type: SignalTypeEnum


@runtime_checkable
class EmailProvider(Protocol):
    """Поставщик писем для EmailSourceAdapter."""

    def fetch_messages(self) -> Sequence[EmailMessage]:
        """Возвращает сообщения, готовые к преобразованию в сигналы."""


@runtime_checkable
class TelegramMessage(Protocol):
    """Минимальная структура сообщения, необходимая Telegram-адаптеру."""

    message_id: int
    chat_id: int
    chat_title: str
    sender_name: str
    text: str
    sent_at: datetime
    signal_type: SignalTypeEnum


@runtime_checkable
class TelegramProvider(Protocol):
    """Поставщик Telegram-сообщений для TelegramSourceAdapter."""

    def fetch_messages(self) -> Sequence[TelegramMessage]:
        """Возвращает сообщения, готовые к преобразованию в сигналы."""