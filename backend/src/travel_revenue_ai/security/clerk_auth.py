"""Безопасная read-only аутентификация Clerk session token."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, NoReturn

from clerk_backend_api import Clerk
from clerk_backend_api.security import AuthStatus, AuthenticateRequestOptions
from fastapi import HTTPException, Request, status

from travel_revenue_ai.config import Settings, settings
from travel_revenue_ai.security.principal import Principal

logger = logging.getLogger(__name__)
_AUTHENTICATION_FAILED_EVENT = "authentication_failed"
_BEARER_HEADER_PATTERN = re.compile(r"Bearer [^\s]+")


class AuthenticationError(Exception):
    """Внутренняя ошибка аутентификации без credential-контекста."""



@lru_cache(maxsize=1)
def get_clerk_client() -> Clerk:
    """Возвращает один Clerk client на процесс без передачи секретов в конструктор."""
    return Clerk()


def _authentication_required() -> NoReturn:
    """Возвращает единый безопасный ответ для любой auth-ошибки."""
    logger.warning(
        _AUTHENTICATION_FAILED_EVENT,
        extra={"event": _AUTHENTICATION_FAILED_EVENT},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication_required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _has_strict_bearer_header(request: Request) -> bool:
    """Проверяет единственный допустимый формат Authorization без чтения cookie."""
    authorization = request.headers.get("Authorization")
    return authorization is not None and _BEARER_HEADER_PATTERN.fullmatch(authorization) is not None


def _build_authenticate_options(app_settings: Settings) -> AuthenticateRequestOptions:
    """Строит SDK options с безопасным приоритетом JWT public key над secret key."""
    if not app_settings.clerk_issuer or not app_settings.clerk_issuer.strip():
        raise ValueError("Clerk issuer is not configured")

    options: dict[str, Any] = {"accepts_token": ["session_token"]}
    if app_settings.clerk_jwt_key:
        options["jwt_key"] = app_settings.clerk_jwt_key
    elif app_settings.clerk_secret_key:
        options["secret_key"] = app_settings.clerk_secret_key
    else:
        raise ValueError("Clerk verification key is not configured")

    if app_settings.clerk_audience:
        options["audience"] = app_settings.clerk_audience
    if app_settings.clerk_authorized_parties:
        options["authorized_parties"] = list(app_settings.clerk_authorized_parties)

    return AuthenticateRequestOptions(**options)


async def _authenticate_request(request: Request) -> Principal:
    """Проверяет Bearer session token и возвращает только минимальный Principal."""
    if not _has_strict_bearer_header(request):
        raise AuthenticationError

    options = _build_authenticate_options(settings)
    request_state = await get_clerk_client().authenticate_request_async(request, options)
    if request_state.status != AuthStatus.SIGNED_IN:
        raise AuthenticationError

    payload = request_state.payload
    if not isinstance(payload, Mapping):
        raise AuthenticationError

    issuer_claim = payload.get("iss")
    if not isinstance(issuer_claim, str) or issuer_claim != settings.clerk_issuer:
        raise AuthenticationError

    subject_claim = payload.get("sub")
    if not isinstance(subject_claim, str) or not subject_claim.strip():
        raise AuthenticationError

    return Principal(
        subject_id=subject_claim,
        issuer=issuer_claim,
        token_type="session_token",
    )


async def require_principal(request: Request) -> Principal:
    """Преобразует внутреннюю auth-ошибку в единый HTTP 401."""
    try:
        return await _authenticate_request(request)
    except Exception:
        logger.warning(
            _AUTHENTICATION_FAILED_EVENT,
            extra={"event": _AUTHENTICATION_FAILED_EVENT},
        )
        return _authentication_required()
