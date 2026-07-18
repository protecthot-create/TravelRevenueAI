"""Базовый класс для всех SQLAlchemy-моделей.

Определяет общие поля и поведение для всех моделей системы.
"""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy.

    Все модели должны наследоваться от этого класса для обеспечения
    единообразия структуры и поведения.
    """

    __abstract__ = True

    # Общие поля для всех моделей
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата создания записи",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Дата последнего обновления записи",
    )