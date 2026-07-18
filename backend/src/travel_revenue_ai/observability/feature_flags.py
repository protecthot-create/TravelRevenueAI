"""Конфигурационные feature flags для безопасного включения Intelligence Layer."""

from __future__ import annotations

from typing import Literal

from travel_revenue_ai.config import Settings, settings

FeatureFlagName = Literal[
    "intelligence_enabled",
    "intelligence_priority_enabled",
    "duplicate_detection_enabled",
    "entity_extraction_enabled",
]


class FeatureFlagService:
    """Предоставляет единый интерфейс чтения feature flags из конфигурации приложения."""

    def __init__(self, application_settings: Settings | None = None) -> None:
        """Использует глобальные настройки или переданный тестовый экземпляр."""
        self._settings = application_settings or settings

    def is_enabled(self, flag_name: FeatureFlagName) -> bool:
        """Возвращает состояние известного флага."""
        return bool(getattr(self._settings, flag_name))

    def snapshot(self) -> dict[FeatureFlagName, bool]:
        """Возвращает текущие состояния всех поддерживаемых флагов."""
        return {
            "intelligence_enabled": self.is_enabled("intelligence_enabled"),
            "intelligence_priority_enabled": self.is_enabled("intelligence_priority_enabled"),
            "duplicate_detection_enabled": self.is_enabled("duplicate_detection_enabled"),
            "entity_extraction_enabled": self.is_enabled("entity_extraction_enabled"),
        }