"""Инфраструктура базы данных Travel Revenue AI.

Модуль предоставляет:
- engine — движок SQLAlchemy для выполнения SQL
- SessionLocal — фабрика сессий для работы с БД
- get_db — dependency для FastAPI, управляет жизненным циклом сессии
- init_db — создание всех таблиц (для MVP без Alembic)

Архитектура:
- SQLite для MVP (zero-config, файл на диске)
- PostgreSQL для production (переключение через env DATABASE_URL)
- Единый интерфейс, независимый от движка БД
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from travel_revenue_ai.config import settings
from travel_revenue_ai.models.base import Base

# =============================================================================
# Engine
# =============================================================================

def _create_engine() -> Engine:
    """Создаёт SQLAlchemy engine с настройками под текущую БД.

    SQLite: используем check_same_thread=False для совместимости с FastAPI
    PostgreSQL: настраиваем пул соединений для production нагрузки
    """
    if settings.is_sqlite:
        # SQLite специфика: нужен connect_args для многопоточности
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            # Echo SQL-запросов в debug-режиме
            echo=settings.debug,
        )

    # PostgreSQL: полноценный пул соединений
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        echo=settings.debug,
    )


engine = _create_engine()

# =============================================================================
# Session Factory
# =============================================================================

# autocommit=False — транзакции явные, commit только когда нужно
# autoflush=False — flush только при commit или явном вызове
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# =============================================================================
# Dependency для FastAPI
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """Генератор сессии БД для использования в FastAPI dependency.

    Использование:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...

    Гарантирует закрытие сессии даже при исключении.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================================================================
# Инициализация БД (MVP)
# =============================================================================

def init_db() -> None:
    """Создаёт все таблицы на основе моделей, наследующих Base.

    ⚠️ Только для MVP и разработки. В production использовать Alembic.
    Вызывать один раз при старте приложения.
    """
    # Импорт моделей для регистрации в metadata
    # noqa: F401 — импорты нужны для side-effect (регистрация в Base.metadata)
    import travel_revenue_ai.models  # noqa: F401

    Base.metadata.create_all(bind=engine)