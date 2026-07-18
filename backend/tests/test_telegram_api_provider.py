"""Unit-тесты production Telegram-провайдера без реального Telegram API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

import pytest

from travel_revenue_ai.models.signal import SignalTypeEnum
from travel_revenue_ai.sources.connection_manager import ConnectionManager
from travel_revenue_ai.sources.default_providers import (
    register_default_connections,
    register_default_providers,
)
from travel_revenue_ai.sources.mock_telegram_provider import MockTelegramMessage, MockTelegramProvider
from travel_revenue_ai.sources.provider_registry import ProviderRegistry
from travel_revenue_ai.sources.telegram import TelegramSourceAdapter
from travel_revenue_ai.sources.telegram_api_provider import (
    TelegramApiProvider,
    TelegramClientProtocol,
    TelegramProviderError,
)


@dataclass
class FakeEntity:
    """Минимальная публичная сущность Telethon для unit-тестов."""

    id: int
    title: str


@dataclass
class FakeSender:
    """Минимальный отправитель сообщения Telethon для unit-тестов."""

    first_name: str = ""
    last_name: str = ""
    username: str = ""


@dataclass
class FakeMessage:
    """Минимальное текстовое сообщение Telethon для unit-тестов."""

    id: int
    message: str
    date: datetime
    sender: FakeSender | None = None


class FakeTelethonClient(TelegramClientProtocol):
    """Синхронный fake-клиент, не выполняющий сетевые вызовы."""

    def __init__(
        self,
        *,
        entities: dict[str, FakeEntity],
        messages: dict[int, list[FakeMessage]],
        authorized: bool = True,
        entity_error: Exception | None = None,
    ) -> None:
        """Сохраняет заданные сценарии Telethon."""
        self._entities = entities
        self._messages = messages
        self._authorized = authorized
        self._entity_error = entity_error
        self.connected = False
        self.disconnected = False
        self.started_with_phone: str | None = None
        self.requested_entities: list[str] = []

    def connect(self) -> None:
        """Имитирует открытие подключения."""
        self.connected = True

    def disconnect(self) -> None:
        """Имитирует закрытие подключения."""
        self.disconnected = True

    def is_user_authorized(self) -> bool:
        """Возвращает заданный статус сессии."""
        return self._authorized

    def start(self, *, phone: str) -> None:
        """Имитирует авторизацию по номеру телефона."""
        self.started_with_phone = phone
        self._authorized = True

    def get_entity(self, entity: str) -> FakeEntity:
        """Возвращает публичный канал или имитирует его недоступность."""
        self.requested_entities.append(entity)
        if self._entity_error is not None:
            raise self._entity_error
        return self._entities[entity]

    def iter_messages(self, entity: Any, *, limit: int) -> Iterator[FakeMessage]:
        """Возвращает последние сообщения сущности с соблюдением limit."""
        return iter(self._messages[entity.id][:limit])


def _create_provider(
    client: FakeTelethonClient,
    *,
    channels: list[str] | None = None,
    phone: str | None = None,
    message_limit: int = 50,
) -> TelegramApiProvider:
    """Создаёт провайдер с внедрённым fake Telethon-клиентом."""
    return TelegramApiProvider(
        api_id=123456,
        api_hash="test-api-hash",
        session="test-session",
        channels=channels or ["@travel_channel"],
        phone=phone,
        message_limit=message_limit,
        client_factory=lambda _session, _api_id, _api_hash: client,
    )


def test_fetch_messages_connects_and_returns_multiple_messages() -> None:
    """Провайдер читает несколько сообщений публичного канала и закрывает подключение."""
    entity = FakeEntity(id=-100100, title="Туристический канал")
    client = FakeTelethonClient(
        entities={"@travel_channel": entity},
        messages={
            entity.id: [
                FakeMessage(
                    id=1,
                    message="Новые цены на Турцию",
                    date=datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc),
                    sender=FakeSender(first_name="Иван", last_name="Петров"),
                ),
                FakeMessage(
                    id=2,
                    message="Срочно обновите предложения",
                    date=datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc),
                    sender=FakeSender(username="operator"),
                ),
            ]
        },
    )

    messages = _create_provider(client).fetch_messages()

    assert client.connected is True
    assert client.disconnected is True
    assert client.requested_entities == ["@travel_channel"]
    assert [message.message_id for message in messages] == [1, 2]
    assert messages[0].chat_id == -100100
    assert messages[0].chat_title == "Туристический канал"
    assert messages[0].sender_name == "Иван Петров"
    assert messages[1].sender_name == "operator"
    assert all(message.signal_type is SignalTypeEnum.market for message in messages)


@pytest.mark.parametrize(
    ("credentials", "expected_error"),
    [
        ({"api_id": "not-an-id", "api_hash": "hash", "session": "session"}, "Конфигурация"),
        ({"api_id": 123456, "api_hash": "", "session": "session"}, "Конфигурация"),
    ],
)
def test_from_data_source_config_rejects_invalid_credentials(
    credentials: dict[str, object],
    expected_error: str,
) -> None:
    """Неверные api_id и api_hash не запускают Telethon и не раскрываются наружу."""
    with pytest.raises(TelegramProviderError, match=expected_error):
        TelegramApiProvider.from_data_source_config(
            {
                "credentials": credentials,
                "settings": {"channels": ["@travel_channel"]},
            }
        )


def test_from_data_source_config_rejects_empty_channels() -> None:
    """Пустой список каналов явно возвращает безопасную ошибку конфигурации."""
    with pytest.raises(TelegramProviderError, match="Не настроены Telegram-каналы"):
        TelegramApiProvider.from_data_source_config(
            {
                "credentials": {
                    "api_id": 123456,
                    "api_hash": "test-api-hash",
                    "session": "test-session",
                },
                "settings": {"channels": []},
            }
        )


def test_fetch_messages_converts_unavailable_channel_to_safe_error() -> None:
    """Недоступный публичный канал не раскрывает исключение Telethon."""
    client = FakeTelethonClient(
        entities={},
        messages={},
        entity_error=RuntimeError("ChannelPrivateError: internal details"),
    )

    with pytest.raises(TelegramProviderError, match="Не удалось получить сообщения Telegram") as error:
        _create_provider(client).fetch_messages()

    assert "ChannelPrivateError" not in str(error.value)
    assert client.disconnected is True


def test_fetch_messages_uses_phone_only_for_unauthorized_session() -> None:
    """Номер телефона используется только когда существующая сессия не авторизована."""
    entity = FakeEntity(id=-100100, title="Туристический канал")
    client = FakeTelethonClient(
        entities={"@travel_channel": entity},
        messages={entity.id: []},
        authorized=False,
    )

    assert _create_provider(client, phone="+79990000000").fetch_messages() == []
    assert client.started_with_phone == "+79990000000"


def test_source_adapter_is_compatible_with_mock_and_production_provider() -> None:
    """TelegramSourceAdapter использует общий Protocol без ветвления по реализации."""
    entity = FakeEntity(id=-100100, title="Туристический канал")
    client = FakeTelethonClient(
        entities={"@travel_channel": entity},
        messages={
            entity.id: [
                FakeMessage(
                    id=42,
                    message="Изменились тарифы",
                    date=datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc),
                )
            ]
        },
    )
    production_provider = _create_provider(client)
    mock_provider = MockTelegramProvider(
        messages=[
            MockTelegramMessage(
                message_id=43,
                chat_id=-100101,
                chat_title="Mock-канал",
                sender_name="Mock",
                text="Тестовое сообщение",
                sent_at=datetime(2026, 7, 18, 10, 1, tzinfo=timezone.utc),
                signal_type=SignalTypeEnum.market,
            )
        ]
    )

    production_signal = TelegramSourceAdapter(
        agency_id=pytest.importorskip("uuid").uuid4(),
        source_id=None,
        provider=production_provider,
    ).collect_signals()[0]
    mock_signal = TelegramSourceAdapter(
        agency_id=pytest.importorskip("uuid").uuid4(),
        source_id=None,
        provider=mock_provider,
    ).collect_signals()[0]

    assert production_signal.raw_data["message_id"] == 42
    assert mock_signal.raw_data["message_id"] == 43
    assert production_signal.signal_type is SignalTypeEnum.market
    assert mock_signal.signal_type is SignalTypeEnum.market


def test_default_registry_and_connection_manager_create_telegram_provider() -> None:
    """Registry и ConnectionManager создают production-провайдер из DataSource config."""
    config = {
        "credentials": {
            "api_id": 123456,
            "api_hash": "test-api-hash",
            "session": "test-session",
        },
        "settings": {"channels": ["@travel_channel"]},
    }
    registry = ProviderRegistry()
    register_default_providers(registry)
    connection_manager = ConnectionManager()
    register_default_connections(connection_manager)

    provider = registry.create(source_type="telegram", provider_name="api", config=config)
    connection = connection_manager.create(
        connection_type="telegram",
        credentials=config["credentials"],
        settings=config["settings"],
    )

    assert isinstance(provider, TelegramApiProvider)
    assert isinstance(connection, TelegramApiProvider)