"""API-тесты persisted MorningBrief на канонической PostgreSQL CS2-базе."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from travel_revenue_ai.database import get_db
from travel_revenue_ai.main import app
from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.models.signal import Signal
from travel_revenue_ai.services.persisted_morning_brief_errors import (
    InvalidPersistedMorningBriefRequest,
    PipelineExecutionError,
)


@pytest.fixture()
def postgres_engine() -> Iterator[Engine]:
    """Подключает тесты только к подготовленной PostgreSQL CS2-базе."""
    database_url = os.environ.get("CS2_TEST_DATABASE_URL", "")
    if "travel_revenue_ai_cs2_test" not in database_url:
        pytest.skip("Нужен CS2_TEST_DATABASE_URL для PostgreSQL CS2-базы")

    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == (
            "travel_revenue_ai_cs2_test"
        )
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    """Создаёт независимую DB-сессию для одного HTTP-теста."""
    session = sessionmaker(
        bind=postgres_engine,
        expire_on_commit=False,
        future=True,
    )()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    """Переопределяет API DB dependency реальной PostgreSQL-сессией."""

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_agency_and_signals(session: Session) -> tuple[Agency, list[Signal]]:
    """Создаёт три сигнала для opportunity/risk/market persisted snapshots."""
    agency = Agency()
    session.add(agency)
    session.flush()
    signals = [
        Signal(
            agency_id=agency.agency_id,
            signal_type=signal_type,
            status="new",
            raw_data={
                "title": title,
                "summary": f"Сигнал {title}",
                "money_effect": str(money_effect),
                "probability": 0.8,
                "urgency": urgency,
                "controllability": 1.0,
                "what_to_do": "Выполнить действие",
                "why_it_matters": "Проверка API persisted aggregate",
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
    """Удаляет только данные текущего API-теста в FK-безопасном порядке."""
    for statement in (
        "DELETE FROM morning_briefs WHERE agency_id = :agency_id",
        "DELETE FROM decision_cards WHERE agency_id = :agency_id",
        "DELETE FROM signals WHERE agency_id = :agency_id",
        "DELETE FROM agencies WHERE agency_id = :agency_id",
    ):
        session.execute(text(statement), {"agency_id": agency_id})
    session.commit()


def _payload(
    agency: Agency,
    signals: list[Signal],
    *,
    brief_date: str = "2026-07-31",
    idempotency_key: str | None = None,
) -> dict[str, object]:
    """Строит валидную публичную команду persisted endpoint."""
    return {
        "agency_id": str(agency.agency_id),
        "brief_date": brief_date,
        "signal_ids": [str(signal.signal_id) for signal in signals],
        "idempotency_key": idempotency_key or f"api-cs3-{uuid.uuid4()}",
        "trigger_type": "manual",
        "request_id": "request-api-test",
    }


def test_persisted_endpoint_creates_rows_snapshots_and_keeps_section_order(
    client: TestClient,
    db_session: Session,
) -> None:
    """HTTP API сохраняет aggregate, snapshots и возвращает section-aware порядок."""
    agency, signals = _create_agency_and_signals(db_session)
    try:
        response = client.post("/api/v1/morning-brief/persisted", json=_payload(agency, signals))

        assert response.status_code == 201
        body = response.json()
        assert body["brief_date"] == "2026-07-31"
        assert body["replayed"] is False
        assert [group["category"] for group in body["decision_card_groups"]] == [
            "opportunities",
            "risks",
            "market_insights",
        ]
        returned_card_ids = [
            card_id
            for group in body["decision_card_groups"]
            for card_id in group["decision_card_ids"]
        ]
        assert body["main_decision_card_id"] in returned_card_ids

        db_session.expire_all()
        brief = db_session.scalar(
            select(MorningBrief).where(MorningBrief.brief_id == uuid.UUID(body["brief_id"]))
        )
        cards = db_session.scalars(
            select(DecisionCard).where(DecisionCard.agency_id == agency.agency_id)
        ).all()
        assert brief is not None
        assert len(cards) == 3
        assert brief.main_action_snapshot is not None
        assert brief.opportunities_snapshot
        assert brief.risks_snapshot
        assert brief.market_insights_snapshot
        assert [str(card_id) for card_id in brief.top_opportunity_card_ids] == (
            body["decision_card_groups"][0]["decision_card_ids"]
        )
        assert [str(card_id) for card_id in brief.top_risk_card_ids] == (
            body["decision_card_groups"][1]["decision_card_ids"]
        )
        assert [str(card_id) for card_id in brief.market_insight_card_ids] == (
            body["decision_card_groups"][2]["decision_card_ids"]
        )
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_persisted_endpoint_replays_identical_idempotency_command(
    client: TestClient,
    db_session: Session,
) -> None:
    """Повтор валидной semantic-команды возвращает тот же brief с replayed=true."""
    agency, signals = _create_agency_and_signals(db_session)
    try:
        payload = _payload(agency, signals)
        first = client.post("/api/v1/morning-brief/persisted", json=payload)
        replay = client.post("/api/v1/morning-brief/persisted", json=payload)

        assert first.status_code == 201
        assert replay.status_code == 201
        assert replay.json()["brief_id"] == first.json()["brief_id"]
        assert replay.json()["replayed"] is True
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_decision_card_feedback_endpoint_updates_only_lifecycle_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    """Feedback endpoint меняет только lifecycle-поля persisted карточки."""
    agency, signals = _create_agency_and_signals(db_session)
    try:
        create_response = client.post(
            "/api/v1/morning-brief/persisted",
            json=_payload(agency, signals),
        )
        assert create_response.status_code == 201
        decision_card_id = uuid.UUID(
            create_response.json()["decision_card_groups"][0]["decision_card_ids"][0]
        )

        original_card = db_session.scalar(
            select(DecisionCard).where(DecisionCard.decision_card_id == decision_card_id)
        )
        assert original_card is not None
        original_snapshot = {
            "title": original_card.title,
            "summary": original_card.summary,
            "what_to_do": original_card.what_to_do,
            "why_it_matters": original_card.why_it_matters,
            "deadline": original_card.deadline,
            "money_effect_raw": original_card.money_effect_raw,
            "score": original_card.score,
            "confidence": original_card.confidence,
            "priority": original_card.priority,
            "reasoning": original_card.reasoning,
            "score_breakdown": dict(original_card.score_breakdown),
            "audit_metadata": dict(original_card.audit_metadata),
        }

        feedback_response = client.post(
            f"/api/v1/decision-cards/{decision_card_id}/feedback",
            json={"feedback_state": "accepted"},
        )

        assert feedback_response.status_code == 200
        assert feedback_response.json()["decision_card_id"] == str(decision_card_id)
        assert feedback_response.json()["status"] == "active"
        assert feedback_response.json()["feedback_state"] == "accepted"

        db_session.expire_all()
        updated_card = db_session.scalar(
            select(DecisionCard).where(DecisionCard.decision_card_id == decision_card_id)
        )
        assert updated_card is not None
        assert updated_card.status == "active"
        assert updated_card.feedback_state == "accepted"
        assert {
            "title": updated_card.title,
            "summary": updated_card.summary,
            "what_to_do": updated_card.what_to_do,
            "why_it_matters": updated_card.why_it_matters,
            "deadline": updated_card.deadline,
            "money_effect_raw": updated_card.money_effect_raw,
            "score": updated_card.score,
            "confidence": updated_card.confidence,
            "priority": updated_card.priority,
            "reasoning": updated_card.reasoning,
            "score_breakdown": dict(updated_card.score_breakdown),
            "audit_metadata": dict(updated_card.audit_metadata),
        } == original_snapshot
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_decision_card_feedback_endpoint_returns_404_for_unknown_card(
    client: TestClient,
) -> None:
    """Неизвестная карточка получает стабильный 404 without domain leak."""
    response = client.post(
        f"/api/v1/decision-cards/{uuid.uuid4()}/feedback",
        json={"feedback_state": "accepted"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "decision_card_not_found"


def test_decision_card_feedback_endpoint_rejects_invalid_dto_value(
    client: TestClient,
) -> None:
    """HTTP-слой валидирует только DTO enum для feedback_state."""
    response = client.post(
        f"/api/v1/decision-cards/{uuid.uuid4()}/feedback",
        json={"feedback_state": "invalid"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("mutate", "expected_status", "expected_detail"),
    [
        (
            lambda payload, signals: payload.update(
                {"signal_ids": [str(signals[0].signal_id), str(signals[0].signal_id)]}
            ),
            400,
            "duplicate_signal_ids",
        ),
        (
            lambda payload, signals: payload.update({"signal_ids": [str(uuid.uuid4())]}),
            404,
            "signal_not_found",
        ),
    ],
)
def test_persisted_endpoint_maps_input_and_missing_signal_errors(
    client: TestClient,
    db_session: Session,
    mutate: object,
    expected_status: int,
    expected_detail: str,
) -> None:
    """DTO-valid commands получают стабильные 400/404 application mappings."""
    agency, signals = _create_agency_and_signals(db_session)
    try:
        payload = _payload(agency, signals)
        mutate(payload, signals)  # type: ignore[operator]
        response = client.post("/api/v1/morning-brief/persisted", json=payload)
        assert response.status_code == expected_status
        assert response.json()["detail"] == expected_detail
    finally:
        _cleanup_agency(db_session, agency.agency_id)


def test_persisted_endpoint_maps_ownership_idempotency_and_date_conflicts(
    client: TestClient,
    db_session: Session,
) -> None:
    """Ownership, semantic-idempotency и business-date конфликты возвращают 409."""
    agency, signals = _create_agency_and_signals(db_session)
    other_agency, other_signals = _create_agency_and_signals(db_session)
    try:
        ownership_payload = _payload(agency, [other_signals[0]])
        ownership = client.post("/api/v1/morning-brief/persisted", json=ownership_payload)
        assert ownership.status_code == 409

        payload = _payload(agency, signals)
        created = client.post("/api/v1/morning-brief/persisted", json=payload)
        assert created.status_code == 201

        conflicting_payload = dict(payload)
        conflicting_payload["signal_ids"] = [
            str(signals[1].signal_id),
            str(signals[0].signal_id),
            str(signals[2].signal_id),
        ]
        idempotency_conflict = client.post(
            "/api/v1/morning-brief/persisted",
            json=conflicting_payload,
        )
        assert idempotency_conflict.status_code == 409

        date_conflict = client.post(
            "/api/v1/morning-brief/persisted",
            json=_payload(agency, signals, idempotency_key=f"other-key-{uuid.uuid4()}"),
        )
        assert date_conflict.status_code == 409
    finally:
        _cleanup_agency(db_session, other_agency.agency_id)
        _cleanup_agency(db_session, agency.agency_id)


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            InvalidPersistedMorningBriefRequest("контролируемый typed 422"),
            422,
            "persisted_brief_contract_rejected",
        ),
        (
            PipelineExecutionError("контролируемый typed 503"),
            503,
            "persisted_brief_unavailable",
        ),
    ],
)
def test_persisted_endpoint_maps_typed_application_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    """API не раскрывает typed exception и выдаёт стабильный 422/503."""
    from travel_revenue_ai.api.v1 import morning_brief

    class FailingService:
        def generate(self, request: object) -> object:
            raise error

    monkeypatch.setattr(
        morning_brief,
        "build_persisted_morning_brief_service",
        lambda session: FailingService(),
    )
    response = client.post(
        "/api/v1/morning-brief/persisted",
        json={
            "agency_id": str(uuid.uuid4()),
            "brief_date": "2026-07-31",
            "signal_ids": [str(uuid.uuid4())],
            "idempotency_key": "typed-error",
            "trigger_type": "manual",
        },
    )
    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


def test_preview_endpoint_remains_available(client: TestClient) -> None:
    """Существующий transient preview endpoint остаётся доступным."""
    response = client.post("/api/v1/morning-brief/generate", json=[])
    assert response.status_code == 200