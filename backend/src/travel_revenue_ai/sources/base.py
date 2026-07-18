"""Базовый контракт адаптера источника данных."""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from travel_revenue_ai.models.signal import Signal


class BaseSourceAdapter(ABC):
    """Абстрактный источник сырых сигналов.

    Конкретный адаптер отвечает только за получение данных внешней системы и
    преобразование их в объекты ``Signal``. Он не сохраняет сигналы в БД и не
    запускает последующие этапы конвейера.
    """

    adapter_name: str

    def __init__(
        self,
        *,
        adapter_name: str,
        agency_id: UUID,
        source_id: UUID | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Инициализирует адаптер контекстом агентства и источника."""
        normalized_name = adapter_name.strip()
        if not normalized_name:
            raise ValueError("adapter_name не может быть пустым")

        self.adapter_name = normalized_name
        self.agency_id = agency_id
        self.source_id = source_id
        self.config = dict(config or {})

    @abstractmethod
    def collect_signals(self) -> list[Signal]:
        """Собирает сырые сигналы и возвращает их без сохранения в БД.

        Каждый возвращённый сигнал обязан относиться к ``agency_id`` и
        ``source_id`` адаптера, иметь статус ``new`` и непустой ``raw_data``.
        """
        raise NotImplementedError