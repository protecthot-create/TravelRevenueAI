"""Главный модуль FastAPI приложения Travel Revenue AI."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from travel_revenue_ai.api.v1 import (
    decision_cards_router,
    morning_brief_history_router,
    morning_brief_router,
    signals_router,
    sources_router,
)
from travel_revenue_ai.config import settings
from travel_revenue_ai.health import is_ready, readiness_checks
from travel_revenue_ai.observability.runtime import install_observability

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Проверяет обязательную инфраструктуру до приёма пользовательского трафика."""
    checks = readiness_checks(http_metrics.render_prometheus)
    if not is_ready(checks):
        details = "; ".join(
            f"{name}: {result['detail']}"
            for name, result in checks.items()
            if result["status"] != "ok"
        )
        raise RuntimeError(f"Startup validation не пройдена: {details}")
    yield


# Создание приложения FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Регистрация API routers
app.include_router(signals_router, prefix="/api/v1")
app.include_router(morning_brief_router, prefix="/api/v1")
app.include_router(morning_brief_history_router, prefix="/api/v1")
app.include_router(decision_cards_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")


# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

http_metrics = install_observability(app, log_level=settings.log_level)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Сохраняет совместимый базовый health endpoint."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health/live", tags=["system"])
async def liveness_check() -> dict[str, str]:
    """Подтверждает, что HTTP-процесс приложения отвечает."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
async def readiness_check(response: Response) -> dict[str, object]:
    """Проверяет готовность зависимостей к обработке рабочего трафика."""
    checks = readiness_checks(http_metrics.render_prometheus)
    ready = is_ready(checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "error", "checks": checks}


@app.get("/", tags=["system"])
async def root() -> dict:
    """Корневой endpoint с базовой информацией."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }