"""IMAP-провайдер для получения непрочитанных email-сообщений."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
import imaplib
import socket
from typing import Any

from travel_revenue_ai.models.signal import SignalTypeEnum


class ImapEmailProviderError(RuntimeError):
    """Контролируемая ошибка подключения или чтения IMAP."""


@dataclass(frozen=True, slots=True)
class ImapEmailMessage:
    """Сырым письмом, полученным через IMAP без классификации содержимого."""

    message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: datetime
    # Поле необходимо текущему контракту EmailMessage. Значение техническое:
    # IMAP-провайдер не классифицирует письмо как opportunity или risk.
    signal_type: SignalTypeEnum = SignalTypeEnum.market


class ImapEmailProvider:
    """Получает непрочитанные письма из настроенного IMAP-ящика.

    Подключение выполняется только во время ``fetch_messages``. Исключения
    преобразуются в ``ImapEmailProviderError``, который SourceManager изолирует
    в SourceResult без раскрытия credentials.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = 993,
        username: str,
        password: str,
        folder: str = "INBOX",
        timeout: float = 30.0,
    ) -> None:
        """Сохраняет параметры подключения без открытия IMAP-сессии."""
        self._host = host.strip()
        self._port = port
        self._username = username
        self._password = password
        self._folder = folder.strip() or "INBOX"
        self._timeout = timeout

        if not self._host:
            raise ValueError("Для IMAP-провайдера требуется host")
        if not self._username:
            raise ValueError("Для IMAP-провайдера требуется username")
        if not self._password:
            raise ValueError("Для IMAP-провайдера требуется password")
        if self._port <= 0:
            raise ValueError("IMAP port должен быть положительным числом")
        if self._timeout <= 0:
            raise ValueError("IMAP timeout должен быть положительным числом")

    def fetch_messages(self) -> list[ImapEmailMessage]:
        """Возвращает только непрочитанные сообщения выбранной IMAP-папки."""
        connection: imaplib.IMAP4_SSL | None = None
        try:
            connection = imaplib.IMAP4_SSL(
                self._host,
                self._port,
                timeout=self._timeout,
            )
            login_status, _ = connection.login(self._username, self._password)
            self._ensure_ok(login_status, "авторизация IMAP")

            select_status, _ = connection.select(self._folder, readonly=True)
            self._ensure_ok(select_status, f"открытие папки '{self._folder}'")

            search_status, search_data = connection.search(None, "UNSEEN")
            self._ensure_ok(search_status, "поиск непрочитанных писем")

            message_numbers = self._extract_message_numbers(search_data)
            messages: list[ImapEmailMessage] = []
            for message_number in message_numbers:
                fetch_status, fetch_data = connection.fetch(message_number, "(RFC822)")
                self._ensure_ok(fetch_status, "получение письма")

                raw_message = self._extract_raw_message(fetch_data)
                if raw_message is not None:
                    messages.append(
                        self._parse_message(
                            raw_message=raw_message,
                            fallback_message_id=message_number.decode(
                                "ascii",
                                errors="replace",
                            ),
                        )
                    )

            return messages
        except imaplib.IMAP4.error as error:
            raise ImapEmailProviderError(
                "Не удалось авторизоваться или выполнить IMAP-команду"
            ) from error
        except (imaplib.IMAP4.abort, OSError, socket.timeout, TimeoutError) as error:
            raise ImapEmailProviderError(
                "Не удалось подключиться к IMAP-серверу или истекло время ожидания"
            ) from error
        finally:
            if connection is not None:
                try:
                    connection.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass

    @staticmethod
    def _ensure_ok(status: str | bytes, operation: str) -> None:
        """Проверяет успешный статус IMAP-команды."""
        normalized_status = (
            status.decode("ascii", errors="replace")
            if isinstance(status, bytes)
            else status
        )
        if normalized_status.upper() != "OK":
            raise ImapEmailProviderError(f"IMAP не выполнил операцию: {operation}")

    @staticmethod
    def _extract_message_numbers(search_data: list[bytes]) -> list[bytes]:
        """Извлекает номера сообщений из ответа команды IMAP SEARCH."""
        if not search_data or not search_data[0]:
            return []
        return search_data[0].split()

    @staticmethod
    def _extract_raw_message(fetch_data: list[Any]) -> bytes | None:
        """Находит RFC822-байты в ответе IMAP FETCH."""
        for item in fetch_data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                return item[1]
        return None

    @classmethod
    def _parse_message(
        cls,
        *,
        raw_message: bytes,
        fallback_message_id: str,
    ) -> ImapEmailMessage:
        """Преобразует RFC822-письмо в структуру контракта EmailMessage."""
        message = message_from_bytes(raw_message)
        received_at = cls._parse_received_at(message.get("Date"))
        return ImapEmailMessage(
            message_id=message.get("Message-ID", "").strip()
            or f"<imap-{fallback_message_id}@{cls.__name__.lower()}>",
            sender=cls._decode_header(message.get("From")),
            recipient=cls._decode_header(message.get("To")),
            subject=cls._decode_header(message.get("Subject")),
            body=cls._extract_plain_text_body(message),
            received_at=received_at,
        )

    @staticmethod
    def _decode_header(value: str | None) -> str:
        """Декодирует RFC 2047-заголовок в строку Unicode."""
        if not value:
            return ""

        decoded_parts: list[str] = []
        for value_part, charset in decode_header(value):
            if isinstance(value_part, bytes):
                decoded_parts.append(
                    value_part.decode(charset or "utf-8", errors="replace")
                )
            else:
                decoded_parts.append(value_part)
        return "".join(decoded_parts)

    @classmethod
    def _extract_plain_text_body(cls, message: Message) -> str:
        """Возвращает plain-text или HTML как fallback для последующей нормализации."""
        parts = message.walk() if message.is_multipart() else (message,)
        plain_text_parts: list[str] = []
        html_parts: list[str] = []

        for part in parts:
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() not in {"text/plain", "text/html"}:
                continue

            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                text = payload.decode(
                    part.get_content_charset() or "utf-8",
                    errors="replace",
                )
            elif isinstance(payload, str):
                text = payload
            else:
                continue

            if text.strip():
                if part.get_content_type() == "text/plain":
                    plain_text_parts.append(text)
                else:
                    html_parts.append(text)

        selected_parts = plain_text_parts or html_parts
        return "\n".join(part.strip() for part in selected_parts if part.strip())

    @staticmethod
    def _parse_received_at(date_header: str | None) -> datetime:
        """Парсит Date в timezone-aware datetime с безопасным fallback."""
        if date_header:
            try:
                received_at = parsedate_to_datetime(date_header)
                if received_at.tzinfo is None:
                    return received_at.replace(tzinfo=timezone.utc)
                return received_at
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
        return datetime.now(timezone.utc)