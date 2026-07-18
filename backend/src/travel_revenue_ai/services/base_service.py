"""Базовый класс для всех сервисов Travel Revenue AI.

Предоставляет общую инфраструктуру:
- работа с SQLAlchemy-сессией;
- единый интерфейс CRUD-операций;
- повторно используемые методы для доменных сервисов.

Принципы:
- Сервис не зависит от FastAPI.
- Сервис получает db: Session извне и хранит ее внутри.
- Наследники задают конкретную ORM-модель и имя первичного ключа.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from travel_revenue_ai.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)

logger = logging.getLogger(__name__)


class BaseService(Generic[ModelType]):
    """Базовый сервис для работы с ORM-моделями."""

    model_class: type[ModelType]
    pk_field_name: str = "id"

    def __init__(self, db: Session, model_class: type[ModelType], pk_field_name: str) -> None:
        """Сохраняет сессию и параметры модели.

        Args:
            db: Активная сессия SQLAlchemy.
            model_class: ORM-модель, с которой работает сервис.
            pk_field_name: Имя поля первичного ключа в модели.
        """
        self.db = db
        self.model_class = model_class
        self.pk_field_name = pk_field_name

    def _commit(self) -> None:
        """Фиксирует транзакцию или откатывает её при ошибке БД."""
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "Не удалось зафиксировать транзакцию для модели %s",
                self.model_class.__name__,
            )
            raise

    def create(self, data: dict[str, Any]) -> ModelType:
        """Создаёт новую запись и сразу сохраняет ее в БД."""
        instance = self.model_class(**data)
        self.db.add(instance)
        self._commit()
        self.db.refresh(instance)
        return instance

    def get_by_id(self, record_id: uuid.UUID) -> ModelType | None:
        """Возвращает запись по первичному ключу."""
        pk_column = getattr(self.model_class, self.pk_field_name)
        return self.db.query(self.model_class).filter(pk_column == record_id).first()

    def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        statement: Select[Any] | None = None,
    ) -> list[ModelType]:
        """Возвращает список записей с пагинацией."""
        if statement is not None:
            return list(self.db.execute(statement.offset(skip).limit(limit)).scalars().all())

        return (
            self.db.query(self.model_class)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, instance: ModelType, data: dict[str, Any]) -> ModelType:
        """Обновляет запись и сохраняет изменения."""
        for field, value in data.items():
            if hasattr(instance, field):
                setattr(instance, field, value)

        self._commit()
        self.db.refresh(instance)
        return instance

    def delete(self, instance: ModelType) -> None:
        """Удаляет запись из базы данных."""
        self.db.delete(instance)
        self._commit()
