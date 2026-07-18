"""Unit-тесты IMAP email-провайдера без подключения к почтовому серверу."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import imaplib
import pytest

from travel_revenue_ai.models.signal import SignalTypeEnum
from travel_revenue_ai.sources.default_providers import register_default_providers
from travel_revenue_ai.sources.imap_email_provider import (
    ImapEmailProvider,
    ImapEmailProviderError,
)
from travel_revenue_ai.sources.mock_email_provider import MockEmailProvider
from travel_revenue_ai.sources.provider_registry import ProviderRegistry


def _create_provider() -> ImapEmailProvider:
    """Создаёт провайдер с тестовой конфигурацией."""
    return ImapEmailProvider(
        host="imap.example.test",
        port=993,
        username="sales@example.test",
        password="test-password",
    )


def _build_connection() -> MagicMock:
    """Создаёт замоканное успешное IMAP-подключение."""
    connection = MagicMock()
    connection.login.return_value = ("OK", [b"Logged in"])
    connection.select.return_value = ("OK", [b"1"])
    connection.search.return_value = ("OK", [b"1"])
    connection.logout.return_value = ("BYE", [b"Logged out"])
    return connection


def test_fetch_messages_returns_unread_plain_text_messages() -> None:
    """Провайдер читает UNSEEN, парсит заголовки и plain-text тело."""
    connection = _build_connection()
    connection.fetch.return_value = (
        "OK",
        [
            (
                b"1 (RFC822 {260})",
                b"Message-ID: <message-123@example.test>\r\n"
                b"From: Partner <partner@example.test>\r\n"
                b"To: Sales <sales@example.test>\r\n"
                b"Subject: =?UTF-8?B?0KLQtdGB0YI=?=\r\n"
                b"Date: Fri, 17 Jul 2026 08:15:00 +0300\r\n"
                b"Content-Type: multipart/alternative; boundary=boundary\r\n"
                b"\r\n"
                b"--boundary\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"\r\n"
                b"Plain text body\r\n"
                b"--boundary\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"\r\n"
                b"<p>HTML body</p>\r\n"
                b"--boundary--\r\n",
            )
        ],
    )

    with patch(
        "travel_revenue_ai.sources.imap_email_provider.imaplib.IMAP4_SSL",
        return_value=connection,
    ) as imap_ssl:
        messages = _create_provider().fetch_messages()

    assert len(messages) == 1
    assert messages[0].message_id == "<message-123@example.test>"
    assert messages[0].sender == "Partner <partner@example.test>"
    assert messages[0].recipient == "Sales <sales@example.test>"
    assert messages[0].subject == "Тест"
    assert messages[0].body == "Plain text body"
    assert messages[0].signal_type == SignalTypeEnum.market
    assert messages[0].received_at.isoformat() == "2026-07-17T08:15:00+03:00"
    imap_ssl.assert_called_once_with("imap.example.test", 993, timeout=30.0)
    connection.login.assert_called_once_with("sales@example.test", "test-password")
    connection.select.assert_called_once_with("INBOX", readonly=True)
    connection.search.assert_called_once_with(None, "UNSEEN")
    connection.fetch.assert_called_once_with(b"1", "(RFC822)")
    connection.logout.assert_called_once()


def test_fetch_messages_returns_empty_list_for_empty_inbox() -> None:
    """Пустой результат IMAP SEARCH возвращает пустой список."""
    connection = _build_connection()
    connection.search.return_value = ("OK", [b""])

    with patch(
        "travel_revenue_ai.sources.imap_email_provider.imaplib.IMAP4_SSL",
        return_value=connection,
    ):
        messages = _create_provider().fetch_messages()

    assert messages == []
    connection.fetch.assert_not_called()
    connection.logout.assert_called_once()


def test_fetch_messages_converts_authentication_error_to_controlled_error() -> None:
    """Ошибка логина не выходит наружу как необработанное исключение IMAP."""
    connection = MagicMock()
    connection.login.side_effect = imaplib.IMAP4.error("authentication failed")

    with (
        patch(
            "travel_revenue_ai.sources.imap_email_provider.imaplib.IMAP4_SSL",
            return_value=connection,
        ),
        pytest.raises(
            ImapEmailProviderError,
            match="Не удалось авторизоваться или выполнить IMAP-команду",
        ),
    ):
        _create_provider().fetch_messages()

    connection.logout.assert_called_once()


def test_fetch_messages_converts_connection_error_to_controlled_error() -> None:
    """Недоступный IMAP-сервер возвращает контролируемую ошибку."""
    with (
        patch(
            "travel_revenue_ai.sources.imap_email_provider.imaplib.IMAP4_SSL",
            side_effect=OSError("connection refused"),
        ),
        pytest.raises(
            ImapEmailProviderError,
            match="Не удалось подключиться к IMAP-серверу",
        ),
    ):
        _create_provider().fetch_messages()


def test_default_registry_creates_imap_from_datasource_configuration() -> None:
    """Registry создаёт IMAP-провайдер из credentials и settings DataSource."""
    registry = ProviderRegistry()
    register_default_providers(registry)

    provider = registry.create(
        source_type="email",
        provider_name="imap",
        config={
            "credentials": {
                "host": "imap.example.test",
                "username": "sales@example.test",
                "password": "test-password",
            },
            "settings": {
                "port": 1993,
                "folder": "Revenue",
                "timeout": 12.5,
            },
        },
    )
    mock_provider = registry.create(source_type="email", provider_name="mock")

    assert isinstance(provider, ImapEmailProvider)
    assert isinstance(mock_provider, MockEmailProvider)
    assert provider._host == "imap.example.test"  # type: ignore[attr-defined]
    assert provider._port == 1993  # type: ignore[attr-defined]
    assert provider._folder == "Revenue"  # type: ignore[attr-defined]
    assert provider._timeout == 12.5  # type: ignore[attr-defined]