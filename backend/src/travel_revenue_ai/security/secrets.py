"""Шифрование и безопасное представление конфигурационных секретов."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

ENCRYPTED_SECRET_KEY = "_encrypted"
REDACTED_VALUE = "***REDACTED***"
SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
)


class SecretService:
    """Шифрует credentials перед записью в БД и расшифровывает их только для runtime."""

    def __init__(self, encryption_key: str | None, *, require_encryption: bool = False) -> None:
        """Инициализирует Fernet из ключа окружения.

        Ключ должен быть URL-safe base64-строкой Fernet. Для локальной обратной
        совместимости plaintext допускается только при ``require_encryption=False``.
        """
        self._require_encryption = require_encryption
        self._fernet = Fernet(encryption_key.encode("utf-8")) if encryption_key else None

        if self._require_encryption and self._fernet is None:
            raise ValueError("В production требуется переменная SECRET_ENCRYPTION_KEY")

    @property
    def encryption_enabled(self) -> bool:
        """Возвращает признак активного шифрования."""
        return self._fernet is not None

    def encrypt(self, credentials: Mapping[str, Any]) -> dict[str, str]:
        """Возвращает зашифрованный контейнер для хранения в JSON-поле БД."""
        normalized = dict(credentials)
        if self._fernet is None:
            if self._require_encryption:
                raise ValueError("Шифрование credentials не настроено")
            return normalized

        payload = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        token = self._fernet.encrypt(payload).decode("utf-8")
        return {ENCRYPTED_SECRET_KEY: token}

    def decrypt(self, stored_credentials: Mapping[str, Any]) -> dict[str, Any]:
        """Расшифровывает контейнер для передачи провайдеру в памяти процесса."""
        credentials = dict(stored_credentials)
        token = credentials.get(ENCRYPTED_SECRET_KEY)

        if token is None:
            if self._require_encryption and credentials:
                raise ValueError("Обнаружены незашифрованные credentials в production")
            return credentials

        if not isinstance(token, str) or self._fernet is None:
            raise ValueError("Невозможно расшифровать credentials: ключ не настроен")

        try:
            decoded = self._fernet.decrypt(token.encode("utf-8"))
            value = json.loads(decoded.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Зашифрованные credentials повреждены или используют другой ключ") from error

        if not isinstance(value, dict):
            raise ValueError("Расшифрованные credentials должны быть JSON-объектом")
        return value


def generate_secret_encryption_key() -> str:
    """Генерирует новый Fernet-ключ для безопасного хранения в secrets manager."""
    return Fernet.generate_key().decode("utf-8")


def fingerprint_secret(value: str) -> str:
    """Возвращает короткий необратимый отпечаток без раскрытия значения."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact_sensitive_data(value: Any) -> Any:
    """Рекурсивно маскирует значения полей с чувствительными названиями."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED_VALUE
            if _is_sensitive_key(str(key))
            else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    """Проверяет имя поля без учёта регистра."""
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)