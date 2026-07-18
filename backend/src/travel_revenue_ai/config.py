"""Конфигурация приложения Travel Revenue AI."""

from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения и обязательные production-ограничения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Приложение
    app_name: str = "Travel Revenue AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Безопасность
    # Сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str | None = None

    # База данных
    # SQLite для MVP (по умолчанию), PostgreSQL для production
    # Примеры:
    #   SQLite:   sqlite:///./travel_revenue_ai.db
    #   PostgreSQL: postgresql+psycopg://user:pass@localhost/dbname
    database_url: str = "sqlite:///./travel_revenue_ai.db"

    # Пул соединений (актуально для PostgreSQL)
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # Scheduler
    morning_brief_run_time: str = "08:00"
    morning_brief_timezone: str = "Europe/Moscow"

    # Feature flags Intelligence Layer. Включены по умолчанию для обратной совместимости.
    intelligence_enabled: bool = True
    intelligence_priority_enabled: bool = True
    duplicate_detection_enabled: bool = True
    entity_extraction_enabled: bool = True

    @model_validator(mode="after")
    def validate_production_configuration(self) -> Self:
        """Блокирует небезопасную конфигурацию до старта production-приложения."""
        if not self.is_production:
            return self

        if not self.secret_encryption_key:
            raise ValueError("SECRET_ENCRYPTION_KEY обязателен при ENVIRONMENT=production")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS не может содержать '*' в production")
        if self.is_sqlite:
            raise ValueError("SQLite не поддерживается при ENVIRONMENT=production")
        return self

    @property
    def is_production(self) -> bool:
        """Проверяет, что активен production-режим."""
        return self.environment.strip().lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        """Проверяет, используется ли SQLite."""
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        """Проверяет, используется ли PostgreSQL."""
        return "postgresql" in self.database_url


settings = Settings()