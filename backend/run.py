#!/usr/bin/env python3
"""Скрипт запуска Travel Revenue AI backend."""

import uvicorn

from travel_revenue_ai.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "travel_revenue_ai.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )