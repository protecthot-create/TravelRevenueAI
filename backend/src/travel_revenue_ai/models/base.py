"""Базовый класс для всех SQLAlchemy-моделей.

Определяет общее поведение для всех моделей системы.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy.

    Все модели должны наследоваться от этого класса для обеспечения
    единообразия структуры и поведения.
    """

    __abstract__ = True