"""Дедупликация email-сообщений по Message-ID."""

from __future__ import annotations

from threading import Lock


class EmailDeduplicationService:
    """Хранит идентификаторы писем, уже принятых email ingestion-слоем.

    Сервис отвечает только за дедупликацию. Он не нормализует письма, не
    классифицирует их и не содержит бизнес-логики обработки сигналов.
    """

    def __init__(self) -> None:
        """Инициализирует потокобезопасное хранилище идентификаторов."""
        self._processed_message_ids: set[str] = set()
        self._lock = Lock()

    def is_duplicate(self, *, message_id: str) -> bool:
        """Проверяет, было ли письмо с Message-ID ранее принято к обработке."""
        normalized_message_id = self._normalize_message_id(message_id)
        with self._lock:
            return normalized_message_id in self._processed_message_ids

    def mark_processed(self, *, message_id: str) -> None:
        """Помечает Message-ID как принятое к обработке."""
        normalized_message_id = self._normalize_message_id(message_id)
        with self._lock:
            self._processed_message_ids.add(normalized_message_id)

    def forget(self, *, message_id: str) -> None:
        """Снимает временную отметку, если письмо не удалось преобразовать."""
        normalized_message_id = self._normalize_message_id(message_id)
        with self._lock:
            self._processed_message_ids.discard(normalized_message_id)

    def should_process(self, *, message_id: str) -> bool:
        """Атомарно проверяет и помечает письмо для обработки.

        Возвращает ``True`` только один раз для каждого Message-ID.
        """
        normalized_message_id = self._normalize_message_id(message_id)
        with self._lock:
            if normalized_message_id in self._processed_message_ids:
                return False
            self._processed_message_ids.add(normalized_message_id)
            return True

    @staticmethod
    def _normalize_message_id(message_id: str) -> str:
        """Нормализует Message-ID для устойчивого сравнения."""
        normalized_message_id = message_id.strip().casefold()
        if not normalized_message_id:
            raise ValueError("Message-ID не может быть пустым.")
        return normalized_message_id