"""Типизированные ошибки первичного tenant provisioning."""

from __future__ import annotations


class TenantProvisioningError(Exception):
    """Базовая ошибка первичного tenant provisioning."""


class TenantProvisioningPersistenceError(TenantProvisioningError):
    """Хранилище не смогло выполнить атомарный provisioning tenant."""


class TenantProvisioningStateError(TenantProvisioningError):
    """Существующий identity state противоречив и не может быть разрешён."""


class TenantProvisioningInactiveUserError(TenantProvisioningStateError):
    """Связанный с identity AppUser отключён и не может получить tenant replay."""
