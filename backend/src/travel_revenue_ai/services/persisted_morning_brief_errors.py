"""Типизированные ошибки persisted use case утреннего брифа."""

from __future__ import annotations

from uuid import UUID


class PersistedMorningBriefError(Exception):
    """Базовая ошибка persisted use case."""


class InvalidPersistedMorningBriefRequest(PersistedMorningBriefError):
    """Некорректный запрос на создание persisted брифа."""


class DuplicateSignalIdsError(InvalidPersistedMorningBriefRequest):
    """Во входном запросе повторяются идентификаторы сигналов."""


class SignalNotFoundError(PersistedMorningBriefError):
    """Не все запрошенные сигналы существуют."""

    def __init__(self, signal_ids: list[UUID]) -> None:
        self.signal_ids = signal_ids
        super().__init__(f"Не найдены сигналы: {', '.join(map(str, signal_ids))}")


class SignalAgencyOwnershipError(PersistedMorningBriefError):
    """Запрошенный сигнал не принадлежит агентству."""


class IdempotencyConflictError(PersistedMorningBriefError):
    """Один ключ идемпотентности использован с другим semantic payload."""


class BusinessDateConflictError(PersistedMorningBriefError):
    """Для агентства уже существует бриф на указанную дату."""


class PipelineExecutionError(PersistedMorningBriefError):
    """Pipeline не смог сформировать runtime бриф."""


class PersistedMorningBriefMappingError(PersistedMorningBriefError):
    """Runtime результат нельзя безопасно представить в persistence-модели."""


class NumericDecisionCardMappingError(PersistedMorningBriefMappingError):
    """Денежный эффект карточки не представим в Numeric(14, 2)."""


class PersistenceError(PersistedMorningBriefError):
    """Persisted aggregate не удалось сохранить атомарно."""