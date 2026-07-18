"""Главный модуль FastAPI приложения Travel Revenue AI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from travel_revenue_ai.api.v1 import (
    morning_brief_router,
    signals_router,
    sources_router,
)
from travel_revenue_ai.config import settings
from travel_revenue_ai.observability.runtime import install_observability

# Создание приложения FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Регистрация API routers
app.include_router(signals_router, prefix="/api/v1")
app.include_router(morning_brief_router, prefix="/api/v1")
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
    """Проверка работоспособности приложения."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    """Корневой endpoint с базовой информацией."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }