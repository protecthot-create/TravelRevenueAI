"""Production-провайдер Telegram на базе Telethon.

Провайдер получает только публичные сообщения из каналов и групп, заданных
в конфигурации DataSource. Он не записывает данные в БД и предоставляет
адаптеру только контракт TelegramProvider.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import Any, Protocol, cast

from travel_revenue_ai.models.signal import SignalTypeEnum


class TelegramProviderError(RuntimeError):
    """Безопасная ошибка production-провайдера Telegram."""


@dataclass(frozen=True, slots=True)
class TelegramApiMessage:
    """Нормализованное Telegram-сообщение для TelegramSourceAdapter."""

    message_id: int
    chat_id: int
    chat_title: str
    sender_name: str
    text: str
    sent_at: datetime
    signal_type: SignalTypeEnum = SignalTypeEnum.market


class TelegramClientProtocol(Protocol):
    """Минимальный синхронный интерфейс Telethon-клиента."""

    def connect(self) -> Any:
        """Открывает подключение к Telegram."""

    def disconnect(self) -> Any:
        """Закрывает подключение к Telegram."""

    def is_user_authorized(self) -> bool:
        """Проверяет авторизацию текущей сессии."""

    def start(self, *, phone: str) -> Any:
        """Авторизует клиента по номеру телефона."""

    def get_entity(self, entity: str) -> Any:
        """Получает сущность публичного канала или группы."""

    def iter_messages(self, entity: Any, *, limit: int) -> Iterator[Any]:
        """Итерирует последние сообщения сущности."""


TelegramClientFactory = Callable[[str, int, str], TelegramClientProtocol]


class TelegramApiProvider:
    """Читает сообщения публичных Telegram-каналов и групп через Telethon."""

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        session: str,
        channels: Sequence[str],
        phone: str | None = None,
        message_limit: int = 50,
        client_factory: TelegramClientFactory | None = None,
    ) -> None:
        """Сохраняет проверенную конфигурацию без создания подключения."""
        if api_id <= 0:
            raise TelegramProviderError("Конфигурация Telegram недействительна")
        if not api_hash.strip() or not session.strip():
            raise TelegramProviderError("Конфигурация Telegram недействительна")
        if message_limit <= 0:
            raise TelegramProviderError("Конфигурация Telegram недействительна")

        normalized_channels = tuple(
            channel.strip()
            for channel in channels
            if isinstance(channel, str) and channel.strip()
        )
        if not normalized_channels:
            raise TelegramProviderError("Не настроены Telegram-каналы")

        self._api_id = api_id
        self._api_hash = api_hash
        self._session = session
        self._channels = normalized_channels
        self._phone = phone.strip() if isinstance(phone, str) and phone.strip() else None
        self._message_limit = message_limit
        self._client_factory = client_factory or self._load_telethon_client_factory

    @classmethod
    def from_data_source_config(cls, config: dict[str, Any]) -> TelegramApiProvider:
        """Создаёт провайдер из стандартной структуры credentials/settings DataSource."""
        credentials = _get_mapping(config, "credentials")
        settings = _get_mapping(config, "settings")

        return cls(
            api_id=_get_required_int(credentials, settings, config, field_name="api_id"),
            api_hash=_get_required_string(credentials, settings, config, field_name="api_hash"),
            session=_get_required_string(credentials, settings, config, field_name="session"),
            phone=_get_optional_string(credentials, settings, config, field_name="phone"),
            channels=_get_channels(settings),
            message_limit=_get_optional_int(
                credentials,
                settings,
                config,
                field_name="message_limit",
                default=50,
            ),
        )

    def fetch_messages(self) -> Sequence[TelegramApiMessage]:
        """Получает сообщения всех настроенных публичных источников."""
        client: TelegramClientProtocol | None = None
        try:
            client = self._client_factory(self._session, self._api_id, self._api_hash)
            client.connect()
            self._ensure_authorized(client)

            result: list[TelegramApiMessage] = []
            for channel in self._channels:
                entity = client.get_entity(channel)
                result.extend(self._fetch_channel_messages(client, entity))
            return result
        except TelegramProviderError:
            raise
        except Exception as error:
            raise TelegramProviderError("Не удалось получить сообщения Telegram") from error
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    # Ошибка освобождения ресурса не должна раскрывать детали Telethon.
                    pass

    def _ensure_authorized(self, client: TelegramClientProtocol) -> None:
        """Проверяет готовность сессии и при необходимости запускает авторизацию."""
        if client.is_user_authorized():
            return
        if self._phone is None:
            raise TelegramProviderError("Telegram-сессия не авторизована")
        try:
            client.start(phone=self._phone)
        except Exception as error:
            raise TelegramProviderError("Не удалось авторизовать Telegram-сессию") from error

        if not client.is_user_authorized():
            raise TelegramProviderError("Telegram-сессия не авторизована")

    def _fetch_channel_messages(
        self,
        client: TelegramClientProtocol,
        entity: Any,
    ) -> list[TelegramApiMessage]:
        """Нормализует доступные текстовые сообщения одного канала или группы."""
        chat_id = _get_int_attribute(entity, "id", default=0)
        chat_title = _get_string_attribute(entity, "title", default=str(chat_id))
        result: list[TelegramApiMessage] = []

        for raw_message in client.iter_messages(entity, limit=self._message_limit):
            text = _get_message_text(raw_message)
            if not text:
                continue
            sent_at = _get_datetime_attribute(raw_message, "date")
            sender_name = _get_sender_name(raw_message)
            result.append(
                TelegramApiMessage(
                    message_id=_get_int_attribute(raw_message, "id", default=0),
                    chat_id=chat_id,
                    chat_title=chat_title,
                    sender_name=sender_name,
                    text=text,
                    sent_at=sent_at,
                )
            )
        return result

    @staticmethod
    def _load_telethon_client_factory(session: str, api_id: int, api_hash: str) -> TelegramClientProtocol:
        """Лениво импортирует Telethon, не ломая старт приложения без зависимости."""
        try:
            telethon_module = import_module("telethon")
            telegram_client = getattr(telethon_module, "TelegramClient")
        except (ImportError, AttributeError) as error:
            raise TelegramProviderError("Telegram-провайдер недоступен") from error
        return cast(TelegramClientProtocol, telegram_client(session, api_id, api_hash))


def _get_mapping(config: dict[str, Any], field_name: str) -> dict[str, Any]:
    """Возвращает вложенную конфигурацию DataSource или пустой словарь."""
    value = config.get(field_name, {})
    return value if isinstance(value, dict) else {}


def _get_value(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    field_name: str,
) -> Any:
    """Ищет поле сначала в credentials, затем в settings и плоском config."""
    for values in (credentials, settings, config):
        if field_name in values:
            return values[field_name]
    return None


def _get_required_string(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
) -> str:
    """Возвращает обязательную непустую строку без раскрытия её значения."""
    value = _get_value(credentials, settings, config, field_name)
    if not isinstance(value, str) or not value.strip():
        raise TelegramProviderError("Конфигурация Telegram недействительна")
    return value


def _get_optional_string(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
) -> str | None:
    """Возвращает необязательную непустую строку."""
    value = _get_value(credentials, settings, config, field_name)
    return value if isinstance(value, str) and value.strip() else None


def _get_required_int(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
) -> int:
    """Возвращает обязательный положительный идентификатор Telegram API."""
    value = _get_value(credentials, settings, config, field_name)
    if isinstance(value, bool):
        raise TelegramProviderError("Конфигурация Telegram недействительна")
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as error:
        raise TelegramProviderError("Конфигурация Telegram недействительна") from error
    if parsed_value <= 0:
        raise TelegramProviderError("Конфигурация Telegram недействительна")
    return parsed_value


def _get_optional_int(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    field_name: str,
    default: int,
) -> int:
    """Возвращает положительное целое значение или безопасный default."""
    value = _get_value(credentials, settings, config, field_name)
    if value is None:
        return default
    if isinstance(value, bool):
        raise TelegramProviderError("Конфигурация Telegram недействительна")
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as error:
        raise TelegramProviderError("Конфигурация Telegram недействительна") from error
    if parsed_value <= 0:
        raise TelegramProviderError("Конфигурация Telegram недействительна")
    return parsed_value


def _get_channels(settings: dict[str, Any]) -> Sequence[str]:
    """Возвращает настроенные каналы и публичные группы Telegram."""
    channels = settings.get("channels")
    if not isinstance(channels, list):
        raise TelegramProviderError("Не настроены Telegram-каналы")
    return channels


def _get_int_attribute(value: Any, field_name: str, *, default: int) -> int:
    """Безопасно читает числовое поле Telethon-объекта."""
    raw_value = getattr(value, field_name, default)
    return raw_value if isinstance(raw_value, int) else default


def _get_string_attribute(value: Any, field_name: str, *, default: str) -> str:
    """Безопасно читает строковое поле Telethon-объекта."""
    raw_value = getattr(value, field_name, default)
    return raw_value.strip() if isinstance(raw_value, str) and raw_value.strip() else default


def _get_datetime_attribute(value: Any, field_name: str) -> datetime:
    """Нормализует дату сообщения в UTC."""
    raw_value = getattr(value, field_name, None)
    if not isinstance(raw_value, datetime):
        return datetime.now(timezone.utc)
    return raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=timezone.utc)


def _get_message_text(message: Any) -> str:
    """Возвращает текст сообщения или пустую строку для нетекстового контента."""
    for field_name in ("message", "text"):
        value = getattr(message, field_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _get_sender_name(message: Any) -> str:
    """Формирует безопасное имя отправителя без дополнительного сетевого запроса."""
    sender = getattr(message, "sender", None)
    if sender is None:
        return "Неизвестный отправитель"

    first_name = _get_string_attribute(sender, "first_name", default="")
    last_name = _get_string_attribute(sender, "last_name", default="")
    username = _get_string_attribute(sender, "username", default="")
    display_name = " ".join(part for part in (first_name, last_name) if part)
    return display_name or username or "Неизвестный отправитель"