"""Сервис для работы с сигналами (Signal).

Реализует бизнес-логику и CRUD-операции для модели Signal.
Не зависит от FastAPI — работает только с SQLAlchemy.

Spec: docs/data_model.md, docs/system_architecture.md
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.services.base_service import BaseService


class SignalService(BaseService[Signal]):
    """Сервис для управления сигналами.

    Наследует базовые CRUD-операции от BaseService
    и расширяет их специфичными для Signal методами.

    Attributes:
        db: Активная сессия SQLAlchemy.
    """

    def __init__(self, db: Session) -> None:
        """Инициализирует сервис с сессией БД.

        Args:
            db: Активная сессия SQLAlchemy.
        """
        super().__init__(db, model_class=Signal, pk_field_name="signal_id")

    # -------------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------------

    def create_signal(
        self,
        *,
        agency_id: uuid.UUID,
        source_id: uuid.UUID,
        signal_type: SignalTypeEnum,
        raw_data: dict[str, Any],
    ) -> Signal:
        """Создаёт новый сигнал.

        Args:
            agency_id: Идентификатор агентства-владельца.
            source_id: Идентификатор источника данных.
            signal_type: Тип сигнала.
            raw_data: Сырые данные сигнала.

        Returns:
            Созданный экземпляр Signal.
        """
        data = {
            "agency_id": agency_id,
            "source_id": source_id,
            "signal_type": signal_type,
            "raw_data": raw_data,
            "status": SignalStatusEnum.new,
        }
        return self.create(data)

    # -------------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------------

    def get_signal(self, signal_id: uuid.UUID) -> Signal | None:
        """Возвращает сигнал по ID.

        Args:
            signal_id: UUID сигнала.

        Returns:
            Найденный сигнал или None.
        """
        return self.get_by_id(signal_id)

    def list_signals(
        self,
        *,
        agency_id: uuid.UUID | None = None,
        signal_type: SignalTypeEnum | None = None,
        status: SignalStatusEnum | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Signal]:
        """Возвращает список сигналов с фильтрацией.

        Args:
            agency_id: Фильтр по агентству (опционально).
            signal_type: Фильтр по типу сигнала (опционально).
            status: Фильтр по статусу (опционально).
            skip: Смещение для пагинации.
            limit: Лимит записей.

        Returns:
            Список сигналов, соответствующих фильтрам.
        """
        query = self.db.query(Signal)

        if agency_id is not None:
            query = query.filter(Signal.agency_id == agency_id)

        if signal_type is not None:
            query = query.filter(Signal.signal_type == signal_type)

        if status is not None:
            query = query.filter(Signal.status == status)

        return query.order_by(Signal.created_at.desc()).offset(skip).limit(limit).all()

    # -------------------------------------------------------------------------
    # UPDATE
    # -------------------------------------------------------------------------

    def update_status(
        self,
        signal: Signal,
        new_status: SignalStatusEnum,
    ) -> Signal:
        """Обновляет статус сигнала.

        Args:
            signal: Существующий сигнал.
            new_status: Новый статус.

        Returns:
            Обновлённый сигнал.
        """
        return self.update(signal, {"status": new_status})

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------

    def delete_signal(self, signal: Signal) -> None:
        """Удаляет сигнал.

        Args:
            signal: Сигнал для удаления.
        """
        self.delete(signal)