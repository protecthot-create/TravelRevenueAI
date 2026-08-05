"""DTO persisted use case утреннего брифа."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class BriefTriggerType(str, Enum):
    """Источник запуска формирования брифа."""

    manual = "manual"
    scheduled = "scheduled"
    system = "system"


@dataclass(frozen=True)
class PersistedMorningBriefRequest:
    """Команда на создание исторического утреннего брифа."""

    agency_id: uuid.UUID
    brief_date: date
    signal_ids: tuple[uuid.UUID, ...]
    idempotency_key: str
    trigger_type: BriefTriggerType = BriefTriggerType.manual
    request_id: str | None = None
    scheduler_job_id: str | None = None

    def fingerprint(self) -> str:
        """Возвращает детерминированный fingerprint семантики запроса.

        Порядок signal_ids является частью контракта: он сохраняется в snapshot
        и влияет на replay одного idempotency key.
        """
        payload = {
            "agency_id": str(self.agency_id),
            "brief_date": self.brief_date.isoformat(),
            "signal_ids": [str(signal_id) for signal_id in self.signal_ids],
            "trigger_type": self.trigger_type.value,
        }
        canonical_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MorningBriefExecutionContext:
    """Неизменяемый контекст одного запуска persisted use case."""

    execution_id: str
    started_at: datetime
    completed_at: datetime | None = None
    engine_version: str | None = None
    scoring_version: str | None = None
    filtering_version: str | None = None
    feature_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistedMorningBriefResult:
    """Результат создания или идемпотентного replay persisted брифа."""

    brief_id: uuid.UUID
    agency_id: uuid.UUID
    brief_date: date
    opportunity_card_ids: tuple[uuid.UUID, ...]
    risk_card_ids: tuple[uuid.UUID, ...]
    market_insight_card_ids: tuple[uuid.UUID, ...]
    main_decision_card_id: uuid.UUID | None
    replayed: bool