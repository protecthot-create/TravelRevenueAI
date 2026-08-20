"""Типизированные ошибки read-only сервиса утренних брифов."""

from __future__ import annotations


class MorningBriefReadError(Exception):
    """Базовая ошибка чтения persisted MorningBrief."""


class MorningBriefReadNotFoundError(MorningBriefReadError):
    """Бриф не найден или недоступен из-за ownership-проверки."""


class MorningBriefReadIntegrityError(MorningBriefReadError):
    """Persisted aggregate ссылается на неполные или противоречивые данные."""


class MorningBriefReadPersistenceError(MorningBriefReadError):
    """Хранилище не смогло выполнить read-запрос."""