"""PostgreSQL integration-тесты успеха и атомарности persisted MorningBrief.

Тесты намеренно не используют SQLite. Для запуска требуется переменная
``CS2_TEST_DATABASE_URL`` с URL базы ``travel_revenue_ai_cs2_test``.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from travel_revenue_ai.models.action import Action
from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.repositories.morning_brief_repository import MorningBriefRepository
from travel_revenue_ai.schemas.decision_card_feedback import DecisionCardFeedbackState
from travel_revenue_ai.schemas.persisted_morning_brief import PersistedMorningBriefRequest
from travel_revenue_ai.services.decision_card_feedback_service import (
    DecisionCardFeedbackNotFoundError,
    DecisionCardFeedbackService,
)
from travel_revenue_ai.services.morning_brief_service import MorningBriefService
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    PersistenceError,
    PipelineExecutionError,
)
from travel_revenue_ai.services.persisted_morning_brief_service import (
    PersistedMorningBriefService,
)
from travel_revenue_ai.services.pipeline_service import PipelineService


@pytest.fixture()
def postgres_engine() -> Iterator[Engine]:
    """Подключает тест только к заранее подготовленной PostgreSQL CS2-базе."""
    database_url = os.environ.get("CS2_TEST_DATABASE_URL", "")
    if "travel_revenue_ai_cs2_test" not in database_url:
        pytest.skip(
            "Нужен CS2_TEST_DATABASE_URL для PostgreSQL БД "
            "travel_revenue_ai_cs2_test"
        )

    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
        version = connection.scalar(text("SHOW server_version"))
    assert database_name == "travel_revenue_ai_cs2_test"
    assert str(version).startswith("16.")
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    """Изолирует тест уникальным agency и удаляет только его данные."""
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _create_agency_and_signals(session: Session) -> tuple[Agency, list[Signal]]:
    """Создаёт минимальный независимый набор persisted input."""
    agency = Agency()
    session.add(agency)
    session.flush()

    signals = [
        Signal(
            agency_id=agency.agency_id,
            source_id=None,
            signal_type=signal_type,
            status="new",
            raw_data={
                "title": title,
                "summary": f"Сигнал {title}",
                "money_effect": str(money_effect),
                "probability": 0.8,
                "urgency": urgency,
                "deadline": "сегодня",
                "what_to_do": "Выполнить действие",
                "why_it_matters": "Проверка persisted aggregate",
            },
        )
        for title, signal_type, money_effect, urgency in (
            ("Раннее бронирование", "opportunity", Decimal("85000.00"), 2.0),
            ("Риск роста цен", "risk", Decimal("-60000.00"), 8.0),
            ("Рыночный тренд", "market", Decimal("25000.00"), 2.0),
        )
    ]
    session.add_all(signals)
    session.commit()
    return agency, signals


def _cleanup_agency(session: Session, agency_id: uuid.UUID) -> None:
    """Удаляет данные теста в FK-безопасном порядке."""
    parameters = {"agency_id": agency_id}
    for statement in (
        "DELETE FROM morning_briefs WHERE agency_id = :agency_id",
        "DELETE FROM decision_cards WHERE agency_id = :agency_id",
        "DELETE FROM signals WHERE agency_id = :agency_id",
        "DELETE FROM agencies WHERE agency_id = :agency_id",
    ):
        session.execute(text(statement), parameters)
    session.commit()


def _service(session: Session, pipeline: object) -> PersistedMorningBriefService:
    """Создаёт use case с контролируемой pipeline dependency."""
    return PersistedMorningBriefService(
        session=session,
        pipeline_service=pipeline,  # type: ignore[arg-type]
    )


def _request(agency: Agency, signals: list[Signal], suffix: str) -> PersistedMorningBriefRequest:
    """Строит уникальную persisted-команду."""
    return PersistedMorningBriefRequest(
        agency_id=agency.agency_id,
        brief_date=date(2026, 7, 23),
        signal_ids=tuple(signal.signal_id for signal in signals),
        idempotency_key=f"rc3-cs2-{suffix}-{uuid.uuid4()}",
    )


class _MutatingPipeline:
    """Запускает реальный pipeline после мутации runtime Signal-copy."""

    def __init__(self) -> None:
        self.commit_called = False
        self._delegate = PipelineService(
            morning_brief_service=MorningBriefService(default_date=date(2026, 7, 23))
        )

    def run(self, signals: list[Signal]) -> object:
        signals[0].raw_data["enriched"] = True
        return self._delegate.run(signals)


class _FailingPipeline:
    """Имитирует отказ до начала write phase."""

    def run(self, signals: list[Signal]) -> object:
        raise RuntimeError("контролируемый pipeline failure")


class _FailingBriefRepository:
    """Падает строго после flush DecisionCards и до сохранения MorningBrief."""

    def __init__(self, delegate: MorningBriefRepository) -> None:
        self._delegate = delegate
        self._cards_flushed = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def flush(self) -> None:
        self._delegate.flush()
        if self._cards_flushed:
            raise RuntimeError("контролируемая ошибка repository")
        self._cards_flushed = True


def _assert_no_aggregate_rows(session: Session, agency_id: uuid.UUID) -> None:
    """Подтверждает отсутствие всех побочных persisted сущностей."""
    assert not session.scalars(
        select(DecisionCard).where(DecisionCard.agency_id == agency_id)
    ).all()
    assert not session.scalars(
        select(MorningBrief).where(MorningBrief.agency_id == agency_id)
    ).all()
    assert not session.scalars(
        select(Action).join(Signal).where(Signal.agency_id == agency_id)
    ).all()


def test_persisted_morning_brief_success_persists_snapshot_order_and_detached_signals(
    db_session: Session,
) -> None:
    """PostgreSQL сохраняет полный aggregate одним commit без мутации Signal."""
    agency, signals = _create_agency_and_signals(db_session)
    original_raw_data = [dict(signal.raw_data) for signal in signals]
    pipeline = _MutatingPipeline()
    service = _service(db_session, pipeline)

    try:
        result = service.generate(_request(agency, signals, "success"))
        db_session.expire_all()

        brief = db_session.scalar(
            select(MorningBrief).where(MorningBrief.brief_id == result.brief_id)
        )
        cards = db_session.scalars(
            select(DecisionCard)
            .where(DecisionCard.agency_id == agency.agency_id)
            .order_by(DecisionCard.created_at, DecisionCard.decision_card_id)
        ).all()
        persisted_signals = db_session.scalars(
            select(Signal)
            .where(Signal.agency_id == agency.agency_id)
            .order_by(Signal.signal_id)
        ).all()

        assert brief is not None
        assert len(cards) == 3
        assert len(
            db_session.scalars(
                select(MorningBrief).where(MorningBrief.agency_id == agency.agency_id)
            ).all()
        ) == 1
        assert tuple(uuid.UUID(card_id) for card_id in brief.top_opportunity_card_ids) == (
            result.opportunity_card_ids
        )
        assert tuple(uuid.UUID(card_id) for card_id in brief.top_risk_card_ids) == (
            result.risk_card_ids
        )
        assert brief.main_decision_card_id == result.main_decision_card_id
        assert brief.main_action_snapshot is not None
        main_card = next(
            card
            for card in cards
            if card.decision_card_id == brief.main_decision_card_id
        )
        assert "decision_card_id" not in brief.main_action_snapshot
        assert brief.main_action_snapshot["title"] == main_card.title
        assert brief.opportunities_snapshot
        assert brief.risks_snapshot
        assert brief.market_insights_snapshot
        assert not db_session.scalars(
            select(Action).join(Signal).where(Signal.agency_id == agency.agency_id)
        ).all()
        expected_raw_data_by_signal_id = {
            signal.signal_id: raw_data
            for signal, raw_data in zip(signals, original_raw_data)
        }
        assert {
            signal.signal_id: signal.raw_data for signal in persisted_signals
        } == expected_raw_data_by_signal_id
        assert all("enriched" not in signal.raw_data for signal in persisted_signals)
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_persisted_morning_brief_rolls_back_cards_when_brief_repository_fails(
    db_session: Session,
) -> None:
    """Ошибка после flush карточек не оставляет orphan DecisionCard в PostgreSQL."""
    agency, signals = _create_agency_and_signals(db_session)
    original_raw_data = [dict(signal.raw_data) for signal in signals]
    pipeline = _MutatingPipeline()

    repository = _FailingBriefRepository(MorningBriefRepository(db_session))
    service = PersistedMorningBriefService(
        session=db_session,
        pipeline_service=pipeline,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    try:
        with pytest.raises(PersistenceError):
            service.generate(_request(agency, signals, "rollback"))

        db_session.expire_all()
        _assert_no_aggregate_rows(db_session, agency.agency_id)
        persisted_signals = db_session.scalars(
            select(Signal).where(Signal.agency_id == agency.agency_id)
        ).all()
        assert len(persisted_signals) == len(signals)
        assert all("enriched" not in signal.raw_data for signal in persisted_signals)
        assert sorted((signal.raw_data for signal in persisted_signals), key=str) == sorted(
            original_raw_data, key=str
        )
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_persisted_morning_brief_pipeline_failure_writes_nothing(
    db_session: Session,
) -> None:
    """Pipeline exception до write phase не выполняет успешный commit aggregate."""
    agency, signals = _create_agency_and_signals(db_session)
    original_raw_data = [dict(signal.raw_data) for signal in signals]
    service = _service(db_session, _FailingPipeline())

    try:
        with pytest.raises(PipelineExecutionError):
            service.generate(_request(agency, signals, "pipeline-failure"))

        db_session.expire_all()
        _assert_no_aggregate_rows(db_session, agency.agency_id)
        persisted_signals = db_session.scalars(
            select(Signal).where(Signal.agency_id == agency.agency_id)
        ).all()
        assert len(persisted_signals) == len(signals)
        assert sorted((signal.raw_data for signal in persisted_signals), key=str) == sorted(
            original_raw_data, key=str
        )
    finally:
        _cleanup_agency(db_session, agency.agency_id)


@pytest.mark.parametrize(
    ("feedback_state", "expected_status"),
    [
        (DecisionCardFeedbackState.accepted, "active"),
        (DecisionCardFeedbackState.dismissed, "dismissed"),
        (DecisionCardFeedbackState.completed, "done"),
    ],
)
def test_decision_card_feedback_service_updates_only_lifecycle_fields(
    db_session: Session,
    feedback_state: DecisionCardFeedbackState,
    expected_status: str,
) -> None:
    """Feedback MVP меняет только lifecycle-поля и не трогает persisted snapshots."""
    agency, signals = _create_agency_and_signals(db_session)
    brief_service = _service(db_session, _MutatingPipeline())
    feedback_service = DecisionCardFeedbackService(db_session)

    try:
        result = brief_service.generate(_request(agency, signals, f"feedback-{feedback_state.value}"))
        decision_card_id = result.opportunity_card_ids[0]

        original_card = db_session.scalar(
            select(DecisionCard).where(DecisionCard.decision_card_id == decision_card_id)
        )
        assert original_card is not None
        original_snapshot = {
            "title": original_card.title,
            "summary": original_card.summary,
            "why_it_matters": original_card.why_it_matters,
            "what_to_do": original_card.what_to_do,
            "deadline": original_card.deadline,
            "money_effect_raw": original_card.money_effect_raw,
            "currency": original_card.currency,
            "money_effect_display": original_card.money_effect_display,
            "score": original_card.score,
            "confidence": original_card.confidence,
            "priority": original_card.priority,
            "reasoning": original_card.reasoning,
            "score_breakdown": dict(original_card.score_breakdown),
            "audit_metadata": dict(original_card.audit_metadata),
        }

        feedback_result = feedback_service.apply_feedback(
            decision_card_id=decision_card_id,
            feedback_state=feedback_state,
        )

        db_session.expire_all()
        updated_card = db_session.scalar(
            select(DecisionCard).where(DecisionCard.decision_card_id == decision_card_id)
        )
        assert updated_card is not None
        assert feedback_result.decision_card_id == decision_card_id
        assert feedback_result.status == expected_status
        assert feedback_result.feedback_state == feedback_state.value
        assert updated_card.status == expected_status
        assert updated_card.feedback_state == feedback_state.value
        assert {
            "title": updated_card.title,
            "summary": updated_card.summary,
            "why_it_matters": updated_card.why_it_matters,
            "what_to_do": updated_card.what_to_do,
            "deadline": updated_card.deadline,
            "money_effect_raw": updated_card.money_effect_raw,
            "currency": updated_card.currency,
            "money_effect_display": updated_card.money_effect_display,
            "score": updated_card.score,
            "confidence": updated_card.confidence,
            "priority": updated_card.priority,
            "reasoning": updated_card.reasoning,
            "score_breakdown": dict(updated_card.score_breakdown),
            "audit_metadata": dict(updated_card.audit_metadata),
        } == original_snapshot
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_decision_card_feedback_service_raises_not_found_without_writes(
    db_session: Session,
) -> None:
    """Неизвестная карточка даёт not found и не создаёт побочных persisted строк."""
    agency, signals = _create_agency_and_signals(db_session)
    brief_service = _service(db_session, _MutatingPipeline())
    feedback_service = DecisionCardFeedbackService(db_session)

    try:
        brief_service.generate(_request(agency, signals, "feedback-not-found"))
        existing_cards = db_session.scalars(
            select(DecisionCard).where(DecisionCard.agency_id == agency.agency_id)
        ).all()
        assert existing_cards

        with pytest.raises(DecisionCardFeedbackNotFoundError):
            feedback_service.apply_feedback(
                decision_card_id=uuid.uuid4(),
                feedback_state=DecisionCardFeedbackState.accepted,
            )

        db_session.expire_all()
        persisted_cards = db_session.scalars(
            select(DecisionCard).where(DecisionCard.agency_id == agency.agency_id)
        ).all()
        assert len(persisted_cards) == len(existing_cards)
        assert all(card.feedback_state == "pending" for card in persisted_cards)
    finally:
        _cleanup_agency(db_session, agency.agency_id)
