"""Стандартная регистрация доступных провайдеров источников."""

from typing import Any

from travel_revenue_ai.sources.connection_manager import ConnectionManager
from travel_revenue_ai.sources.imap_email_provider import ImapEmailProvider
from travel_revenue_ai.sources.mock_email_provider import MockEmailProvider
from travel_revenue_ai.sources.mock_telegram_provider import MockTelegramProvider
from travel_revenue_ai.sources.provider_registry import ProviderRegistry
from travel_revenue_ai.sources.telegram_api_provider import TelegramApiProvider


def register_default_providers(registry: ProviderRegistry) -> None:
    """Регистрирует локальные mock-провайдеры через единый Registry.

    Реальные IMAP, Telethon/Pyrogram, RSS и CRM провайдеры будут добавлены
    позднее отдельными фабриками без изменения source adapters.
    """
    registry.register(
        source_type="email",
        provider_name="mock",
        factory=_create_mock_email_provider,
    )
    registry.register(
        source_type="email",
        provider_name="imap",
        factory=_create_imap_email_provider,
    )
    registry.register(
        source_type="telegram",
        provider_name="mock",
        factory=_create_mock_telegram_provider,
    )
    registry.register(
        source_type="telegram",
        provider_name="api",
        factory=_create_telegram_api_provider,
    )


def register_default_connections(connection_manager: ConnectionManager) -> None:
    """Регистрирует production-фабрики транспортных подключений."""
    connection_manager.register(
        connection_type="telegram",
        factory=_create_telegram_connection,
    )


def _create_mock_email_provider(config: dict[str, Any]) -> MockEmailProvider:
    """Создаёт существующий mock email-провайдер без сетевого подключения."""
    del config
    return MockEmailProvider()


def _create_imap_email_provider(config: dict[str, Any]) -> ImapEmailProvider:
    """Создаёт IMAP-провайдер из credentials и settings DataSource."""
    credentials = _get_nested_mapping(config, "credentials")
    settings = _get_nested_mapping(config, "settings")

    return ImapEmailProvider(
        host=_get_required_string(
            credentials,
            settings,
            config,
            field_name="host",
        ),
        port=_get_optional_int(
            credentials,
            settings,
            config,
            field_name="port",
            default=993,
        ),
        username=_get_required_string(
            credentials,
            settings,
            config,
            field_name="username",
        ),
        password=_get_required_string(
            credentials,
            settings,
            config,
            field_name="password",
        ),
        folder=_get_optional_string(
            credentials,
            settings,
            config,
            field_name="folder",
            default="INBOX",
        ),
        timeout=_get_optional_float(
            credentials,
            settings,
            config,
            field_name="timeout",
            default=30.0,
        ),
    )


def _get_nested_mapping(config: dict[str, Any], field_name: str) -> dict[str, Any]:
    """Возвращает вложенный словарь конфигурации или пустой словарь."""
    value = config.get(field_name, {})
    return value if isinstance(value, dict) else {}


def _get_required_string(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
) -> str:
    """Получает обязательную строку, сначала из credentials, затем из settings."""
    value = _get_value(credentials, settings, config, field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Для IMAP-провайдера требуется {field_name}")
    return value


def _get_optional_string(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
    default: str,
) -> str:
    """Получает необязательную строку конфигурации."""
    value = _get_value(credentials, settings, config, field_name)
    return value if isinstance(value, str) and value.strip() else default


def _get_optional_int(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
    default: int,
) -> int:
    """Получает необязательное целое число конфигурации."""
    value = _get_value(credentials, settings, config, field_name)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"IMAP {field_name} должен быть целым числом")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"IMAP {field_name} должен быть целым числом") from error


def _get_optional_float(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
    default: float,
) -> float:
    """Получает необязательное число с плавающей точкой конфигурации."""
    value = _get_value(credentials, settings, config, field_name)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"IMAP {field_name} должен быть числом")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"IMAP {field_name} должен быть числом") from error


def _get_value(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    field_name: str,
) -> Any:
    """Ищет поле в стандартных секциях DataSource и плоском конфиге."""
    for values in (credentials, settings, config):
        if field_name in values:
            return values[field_name]
    return None


def _create_telegram_api_provider(config: dict[str, Any]) -> TelegramApiProvider:
    """Создаёт Telethon-провайдер из конфигурации DataSource."""
    return TelegramApiProvider.from_data_source_config(config)


def _create_telegram_connection(config: dict[str, Any]) -> TelegramApiProvider:
    """Создаёт Telegram-подключение из credentials/settings ConnectionManager."""
    return TelegramApiProvider.from_data_source_config(config)


def _create_mock_telegram_provider(config: dict[str, Any]) -> MockTelegramProvider:
    """Создаёт существующий mock Telegram-провайдер без сетевого подключения."""
    del config
    return MockTelegramProvider()