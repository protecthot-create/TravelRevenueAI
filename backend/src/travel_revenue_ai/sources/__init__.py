"""Инфраструктура подключения внешних и внутренних источников сигналов.

Публичные экспорты загружаются лениво, чтобы независимые провайдеры не тянули
Email ingestion и Scheduler при импорте отдельного модуля источника.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BaseSourceAdapter",
    "SourceManager",
    "SourceMetadata",
    "SourceResult",
    "EmailSourceAdapter",
    "MockEmailMessage",
    "MockEmailProvider",
    "TelegramSourceAdapter",
    "MockTelegramMessage",
    "MockTelegramProvider",
]


def __getattr__(name: str) -> Any:
    """Лениво возвращает совместимые публичные экспорты Source Framework."""
    if name == "BaseSourceAdapter":
        from travel_revenue_ai.sources.base import BaseSourceAdapter

        return BaseSourceAdapter
    if name in {"SourceMetadata", "SourceResult"}:
        from travel_revenue_ai.sources.contracts import SourceMetadata, SourceResult

        return {"SourceMetadata": SourceMetadata, "SourceResult": SourceResult}[name]
    if name == "SourceManager":
        from travel_revenue_ai.sources.manager import SourceManager

        return SourceManager
    if name == "EmailSourceAdapter":
        from travel_revenue_ai.sources.email import EmailSourceAdapter

        return EmailSourceAdapter
    if name in {"MockEmailMessage", "MockEmailProvider"}:
        from travel_revenue_ai.sources.mock_email_provider import MockEmailMessage, MockEmailProvider

        return {"MockEmailMessage": MockEmailMessage, "MockEmailProvider": MockEmailProvider}[name]
    if name == "TelegramSourceAdapter":
        from travel_revenue_ai.sources.telegram import TelegramSourceAdapter

        return TelegramSourceAdapter
    if name in {"MockTelegramMessage", "MockTelegramProvider"}:
        from travel_revenue_ai.sources.mock_telegram_provider import (
            MockTelegramMessage,
            MockTelegramProvider,
        )

        return {
            "MockTelegramMessage": MockTelegramMessage,
            "MockTelegramProvider": MockTelegramProvider,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")