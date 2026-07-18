"""Реестр фабрик провайдеров источников данных."""

from collections.abc import Callable
from typing import Any


ProviderFactory = Callable[[dict[str, Any]], object]


class ProviderRegistry:
    """Хранит фабрики провайдеров по типу источника и имени реализации."""

    def __init__(self) -> None:
        """Создаёт пустой реестр провайдеров."""
        self._factories: dict[tuple[str, str], ProviderFactory] = {}

    def register(
        self,
        *,
        source_type: str,
        provider_name: str,
        factory: ProviderFactory,
    ) -> None:
        """Регистрирует единственную фабрику для пары типа и имени провайдера."""
        key = self._make_key(source_type=source_type, provider_name=provider_name)
        if key in self._factories:
            raise ValueError(
                f"Провайдер '{provider_name}' уже зарегистрирован для типа '{source_type}'"
            )
        self._factories[key] = factory

    def create(
        self,
        *,
        source_type: str,
        provider_name: str,
        config: dict[str, Any] | None = None,
    ) -> object:
        """Создаёт провайдер через зарегистрированную фабрику."""
        key = self._make_key(source_type=source_type, provider_name=provider_name)
        try:
            factory = self._factories[key]
        except KeyError as error:
            raise LookupError(
                f"Провайдер '{provider_name}' не зарегистрирован для типа '{source_type}'"
            ) from error
        return factory(dict(config or {}))

    def is_registered(self, *, source_type: str, provider_name: str) -> bool:
        """Проверяет наличие фабрики в реестре."""
        key = self._make_key(source_type=source_type, provider_name=provider_name)
        return key in self._factories

    @staticmethod
    def _make_key(*, source_type: str, provider_name: str) -> tuple[str, str]:
        """Нормализует ключ провайдера и отклоняет пустые значения."""
        normalized_source_type = source_type.strip().lower()
        normalized_provider_name = provider_name.strip().lower()
        if not normalized_source_type or not normalized_provider_name:
            raise ValueError("Тип источника и имя провайдера не могут быть пустыми")
        return normalized_source_type, normalized_provider_name