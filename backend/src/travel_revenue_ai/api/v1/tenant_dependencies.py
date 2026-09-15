"""Общие FastAPI dependencies и HTTP mapping tenant authorization."""

from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from travel_revenue_ai.composition import build_tenant_authorization_service
from travel_revenue_ai.database import get_db
from travel_revenue_ai.security.clerk_auth import get_current_principal
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.security.tenant_context import TenantContext
from travel_revenue_ai.services.identity_resolution_errors import (
    IdentityResolutionInactiveUserError,
    IdentityResolutionIntegrityError,
    IdentityResolutionNotFoundError,
    IdentityResolutionPersistenceError,
)
from travel_revenue_ai.services.tenant_authorization_errors import (
    TenantAccessDeniedError,
    TenantAuthorizationIntegrityError,
    TenantAuthorizationPersistenceError,
    TenantSelectionRequiredError,
)


def _raise_authentication_required() -> NoReturn:
    """Возвращает единый 401 без раскрытия деталей identity resolution."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication_required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _raise_tenant_http_error(
    error: Exception,
    *,
    direct_resource: bool = False,
) -> NoReturn:
    """Преобразует tenant errors в стабильные безопасные HTTP-ответы."""
    if isinstance(
        error,
        (
            IdentityResolutionInactiveUserError,
            IdentityResolutionIntegrityError,
            IdentityResolutionNotFoundError,
        ),
    ):
        _raise_authentication_required()
    if isinstance(error, IdentityResolutionPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authorization_unavailable",
        ) from error
    if isinstance(error, TenantSelectionRequiredError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_selection_required",
        ) from error
    if isinstance(error, TenantAccessDeniedError):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND if direct_resource else status.HTTP_403_FORBIDDEN
            ),
            detail=("resource_not_found" if direct_resource else "tenant_access_denied"),
        ) from error
    if isinstance(error, TenantAuthorizationIntegrityError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="tenant_authorization_integrity_error",
        ) from error
    if isinstance(error, TenantAuthorizationPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authorization_unavailable",
        ) from error
    raise error


def authorize_tenant(
    *,
    db: Session,
    principal: Principal,
    agency_id: UUID | None = None,
    direct_resource: bool = False,
) -> TenantContext:
    """Разрешает tenant и применяет единый HTTP mapping для route-кода."""
    try:
        return build_tenant_authorization_service(db).authorize(principal, agency_id)
    except Exception as error:
        _raise_tenant_http_error(error, direct_resource=direct_resource)
        raise AssertionError("Недостижимый код")


def get_tenant_context(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    agency_id: UUID | None = Query(default=None),
) -> TenantContext:
    """Разрешает tenant из query agency_id или из singleton membership."""
    return authorize_tenant(db=db, principal=principal, agency_id=agency_id)


def get_path_tenant_context(
    agency_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    """Разрешает tenant из path-параметра agency_id."""
    return authorize_tenant(db=db, principal=principal, agency_id=agency_id)


def get_direct_tenant_context(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    agency_id: UUID | None = Query(default=None),
) -> TenantContext:
    """Разрешает tenant для прямого ресурса с безопасным 404 при отказе."""
    return authorize_tenant(
        db=db,
        principal=principal,
        agency_id=agency_id,
        direct_resource=True,
    )


def require_resource_tenant(
    tenant_context: TenantContext,
    resource_agency_id: UUID,
) -> None:
    """Скрывает прямой ресурс чужого tenant единым 404-ответом."""
    if tenant_context.agency_id != resource_agency_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource_not_found",
        )


def require_payload_tenant(
    tenant_context: TenantContext,
    payload_agency_id: UUID,
) -> None:
    """Отклоняет команду, которая пытается записать данные в чужой tenant."""
    if tenant_context.agency_id != payload_agency_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_access_denied",
        )
