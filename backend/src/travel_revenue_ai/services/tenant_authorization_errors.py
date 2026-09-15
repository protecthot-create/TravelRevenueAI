"""Типизированные ошибки tenant authorization."""

from __future__ import annotations


class TenantAuthorizationError(Exception):
    """Базовая ошибка разрешения tenant-контекста."""


class TenantAccessDeniedError(TenantAuthorizationError):
    """У пользователя нет active membership для запрошенного агентства."""


class TenantSelectionRequiredError(TenantAuthorizationError):
    """Пользователь состоит в нескольких агентствах и должен выбрать одно."""


class TenantAuthorizationIntegrityError(TenantAuthorizationError):
    """Данные identity или membership нарушают ожидаемую целостность."""


class TenantAuthorizationPersistenceError(TenantAuthorizationError):
    """Хранилище не смогло прочитать tenant authorization данные."""
