"""Детерминированное выявление повторяющихся сигналов."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DuplicateDetection:
    """Результат проверки сигнала на дубликаты."""

    normalized_text_hash: str | None
    is_duplicate: bool
    reasons: list[str]
    matched_identifiers: list[str]

    def to_metadata(self) -> dict[str, object]:
        """Возвращает JSON-совместимое представление результата."""
        return {
            "normalized_text_hash": self.normalized_text_hash,
            "is_duplicate": self.is_duplicate,
            "reasons": self.reasons,
            "matched_identifiers": self.matched_identifiers,
        }


class DuplicateSignalDetector:
    """Сравнивает сигналы по transport ID и хэшу нормализованного текста.

    Детектор не отбрасывает сигналы и не изменяет Source Framework. Его
    результат является наблюдаемым metadata для последующих спринтов.
    """

    def detect(
        self,
        raw_data: Mapping[str, Any],
        known_signals: Iterable[Mapping[str, Any]] = (),
    ) -> DuplicateDetection:
        """Проверяет ``raw_data`` относительно переданного набора сигналов."""
        channel = self._text(raw_data.get("channel")).casefold()
        fingerprint = self._fingerprint(raw_data)
        reasons: list[str] = []
        matched_identifiers: list[str] = []

        for candidate in known_signals:
            candidate_channel = self._text(candidate.get("channel")).casefold()
            if self._same_transport_message(raw_data, candidate, channel, candidate_channel):
                reasons.append(self._transport_reason(channel))
                matched_identifiers.append(self._identifier(candidate, candidate_channel))
                continue

            candidate_fingerprint = self._fingerprint(candidate)
            if fingerprint and fingerprint == candidate_fingerprint:
                reasons.append("normalized_text_hash")
                matched_identifiers.append(self._identifier(candidate, candidate_channel))

        return DuplicateDetection(
            normalized_text_hash=fingerprint,
            is_duplicate=bool(reasons),
            reasons=self._unique(reasons),
            matched_identifiers=self._unique(matched_identifiers),
        )

    @staticmethod
    def _same_transport_message(
        raw_data: Mapping[str, Any],
        candidate: Mapping[str, Any],
        channel: str,
        candidate_channel: str,
    ) -> bool:
        if channel != candidate_channel:
            return False

        message_id = DuplicateSignalDetector._text(raw_data.get("message_id"))
        candidate_message_id = DuplicateSignalDetector._text(candidate.get("message_id"))
        if not message_id or message_id != candidate_message_id:
            return False

        if channel == "telegram":
            return DuplicateSignalDetector._text(raw_data.get("chat_id")) == (
                DuplicateSignalDetector._text(candidate.get("chat_id"))
            )
        return channel == "email"

    @staticmethod
    def _fingerprint(raw_data: Mapping[str, Any]) -> str | None:
        text = DuplicateSignalDetector._normalized_text(raw_data)
        if not text:
            return None
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalized_text(raw_data: Mapping[str, Any]) -> str:
        preferred = raw_data.get("normalized_text")
        text = preferred if isinstance(preferred, str) else raw_data.get("text")
        if not isinstance(text, str):
            subject = raw_data.get("subject")
            body = raw_data.get("body")
            text = " ".join(part for part in (subject, body) if isinstance(part, str))
        return re.sub(r"\s+", " ", text.casefold()).strip()

    @staticmethod
    def _transport_reason(channel: str) -> str:
        return "telegram_message_id" if channel == "telegram" else "email_message_id"

    @staticmethod
    def _identifier(raw_data: Mapping[str, Any], channel: str) -> str:
        message_id = DuplicateSignalDetector._text(raw_data.get("message_id"))
        if channel == "telegram":
            chat_id = DuplicateSignalDetector._text(raw_data.get("chat_id"))
            return f"telegram:{chat_id}:{message_id}"
        return f"{channel or 'unknown'}:{message_id}"

    @staticmethod
    def _text(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))