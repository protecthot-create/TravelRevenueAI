"""Smoke-test полного backend pipeline.

Email-подобный Signal -> Enrichment -> Scoring -> Filtering -> Decision Cards ->
Morning Brief.
"""

from __future__ import annotations

import sys
import traceback
from datetime import date
from uuid import UUID


sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(name: str) -> None:
    """Выводит заголовок секции smoke-test."""
    print(f"\n=== {name} ===", flush=True)


def main() -> int:
    """Выполняет полный pipeline без подключения внешних провайдеров."""
    try:
        section("ИМПОРТЫ")

        from travel_revenue_ai.models import Signal, SignalStatusEnum, SignalTypeEnum
        from travel_revenue_ai.services.morning_brief_service import (
            MorningBriefService,
        )
        from travel_revenue_ai.services.pipeline_service import PipelineService

        print("models: OK", flush=True)
        print("pipeline services: OK", flush=True)

        section("ПОЛНЫЙ PIPELINE")

        signal = Signal(
            agency_id=UUID("22222222-2222-2222-2222-222222222222"),
            source_id=UUID("33333333-3333-3333-3333-333333333333"),
            signal_type=SignalTypeEnum.opportunity,
            status=SignalStatusEnum.normalized,
            raw_data={
                "channel": "email",
                "message_id": "<smoke-turkey@example.test>",
                "subject": "Coral Travel: скидка 25% на Турцию",
                "body": "Срочно! Акция действует до 20 июля.",
                "title": "Раннее бронирование Турция",
                "money_effect": 85_000,
                "urgency": 48,
                "probability": 0.72,
                "confidence": 0.9,
                "controllability": 1.0,
                "risk": False,
                "repeatable": True,
                "context_match": True,
                "season": "peak",
                "summary": "Спрос растёт, окно действия короткое",
                "source_name": "smoke_email",
                "metadata": {"source_marker": "smoke_email"},
            },
        )
        print("email-like signal: OK", flush=True)

        pipeline = PipelineService(
            morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18))
        )
        brief = pipeline.generate_morning_brief([signal])

        intelligence = signal.raw_data["metadata"]["intelligence"]
        assert intelligence, "Intelligence metadata не была добавлена"
        assert signal.signal_type == SignalTypeEnum.opportunity
        assert signal.status == SignalStatusEnum.normalized
        assert brief.total_cards_processed == 1, (
            "Сигнал не прошёл Filtering или не создал Decision Card"
        )
        assert brief.opportunities_count == 1, (
            "Decision Card возможности не попала в Morning Brief"
        )

        print(
            f"enrichment: OK | priority={intelligence['priority']}",
            flush=True,
        )
        print(
            f"filtering + decision card: OK | cards={brief.total_cards_processed}",
            flush=True,
        )
        print(
            f"morning brief: OK | opportunities={brief.opportunities_count} | "
            f"risks={brief.risks_count}",
            flush=True,
        )
        if brief.summary:
            print(f"main action: {brief.summary.main_action_body}", flush=True)

        section("DONE")
        print("SMOKE_TEST_OK", flush=True)
        return 0

    except Exception as error:
        section("ERROR")
        print(f"{type(error).__name__}: {error}", flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())