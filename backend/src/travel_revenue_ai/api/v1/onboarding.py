"""HTTP-граница первичного onboarding provisioning brand-new Clerk user.

Endpoint требует только Clerk-аутентификацию: TenantContext у нового
пользователя ещё не существует и создаётся самим provisioning-сервисом.
Tenant authorization dependency здесь намеренно не подключается.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from travel_revenue_ai.composition import build_tenant_provisioning_service
from travel_revenue_ai.database import get_db
from travel_revenue_ai.schemas.onboarding import OnboardingResponseDTO
from travel_revenue_ai.security.clerk_auth import get_current_principal
from travel_revenue_ai.security.principal import Principal
from travel_revenue_ai.services.tenant_provisioning_errors import (
    TenantProvisioningInactiveUserError,
    TenantProvisioningPersistenceError,
    TenantProvisioningStateError,
)

router = APIRouter(
    prefix="/onboarding",
    tags=["onboarding"],
)


@router.post(
    "",
    response_model=OnboardingResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Первичный onboarding authenticated Clerk user",
)
def onboard_principal(
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> OnboardingResponseDTO:
    """Атомарно создаёт tenant-цепочку или возвращает существующий tenant."""
    service = build_tenant_provisioning_service(db)
    try:
        result = service.provision(principal)
    except Exception as error:
        _raise_onboarding_http_error(error)
        raise AssertionError("Недостижимый код")
    response.status_code = (
        status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED
    )
    return OnboardingResponseDTO(
        app_user_id=result.app_user_id,
        agency_id=result.agency_id,
        role=result.role,
        replayed=result.replayed,
    )


def _raise_onboarding_http_error(error: Exception) -> None:
    """Преобразует typed provisioning errors в стабильные HTTP-ответы."""
    if isinstance(error, TenantProvisioningInactiveUserError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_provisioning_inactive_user",
        )
    if isinstance(error, TenantProvisioningStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="tenant_provisioning_state_conflict",
        )
    if isinstance(error, TenantProvisioningPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="tenant_provisioning_failed",
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="internal_server_error",
    )
