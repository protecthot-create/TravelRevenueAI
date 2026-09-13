"""Типизированные ошибки read-only identity resolution."""

from __future__ import annotations


class IdentityResolutionError(Exception):
    """Базовая ошибка разрешения внешней identity."""


class IdentityResolutionNotFoundError(IdentityResolutionError):
    """Для Principal не найдена связанная ExternalIdentity."""


class IdentityResolutionInactiveUserError(IdentityResolutionError):
    """Связанный AppUser существует, но отключён."""


class IdentityResolutionIntegrityError(IdentityResolutionError):
    """ExternalIdentity ссылается на отсутствующий AppUser."""


class IdentityResolutionPersistenceError(IdentityResolutionError):
    """Хранилище не смогло выполнить read-запрос identity resolution."""
