"""Создание подключений к внешним источникам без сетевой реализации."""

from collections.abc import Callable
from typing import Any


ConnectionFactory = Callable[[dict[str, Any]], object]


class ConnectionManager:
    """Создаёт подключения через явно зарегистрированные фабрики."""

    def __init__(self) -> None:
        """Создаёт пустой набор фабрик подключений."""
        self._factories: dict[str, ConnectionFactory] = {}

    def register(self, *, connection_type: str, factory: ConnectionFactory) -> None:
        """Регистрирует фабрику подключения для типа транспорта."""
        normalized_type = self._normalize_connection_type(connection_type)
        if normalized_type in self._factories:
            raise ValueError(f"Подключение типа '{connection_type}' уже зарегистрировано")
        self._factories[normalized_type] = factory

    def create(
        self,
        *,
        connection_type: str,
        credentials: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> object:
        """Создаёт подключение, передавая фабрике конфигурацию источника."""
        normalized_type = self._normalize_connection_type(connection_type)
        try:
            factory = self._factories[normalized_type]
        except KeyError as error:
            raise LookupError(
                f"Фабрика подключения для типа '{connection_type}' не зарегистрирована"
            ) from error

        return factory(
            {
                "credentials": dict(credentials or {}),
                "settings": dict(settings or {}),
            }
        )

    def is_registered(self, *, connection_type: str) -> bool:
        """Проверяет, есть ли фабрика подключения для указанного типа."""
        return self._normalize_connection_type(connection_type) in self._factories

    @staticmethod
    def _normalize_connection_type(connection_type: str) -> str:
        """Проверяет и нормализует имя транспорта."""
        normalized_type = connection_type.strip().lower()
        if not normalized_type:
            raise ValueError("Тип подключения не может быть пустым")
        return normalized_type