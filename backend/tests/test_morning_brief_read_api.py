"""Изолированные API-тесты read-only persisted MorningBrief CS7."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from travel_revenue_ai.api.v1 import morning_brief
from travel_revenue_ai.composition import build_morning_brief_read_service
from travel_revenue_ai.database import get_db
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief, MorningBriefStatusEnum
from travel_revenue_ai.services.morning_brief_read_errors import (
    MorningBriefReadIntegrityError,
    MorningBriefReadNotFoundError,
)
from travel_revenue_ai.services.morning_brief_read_service import (
    MorningBriefHistoryItem,
    MorningBriefReadResult,
    MorningBriefReadService,
)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Создаёт изолированное API-приложение без startup-проверок и реальной БД."""
    test_app = FastAPI()
    test_app.include_router(morning_brief.router, prefix="/api/v1")
    test_app.include_router(morning_brief.morning_brief_history_router, prefix="/api/v1")

    def override_get_db() -> Iterator[object]:
        yield object()

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        yield test_client


def _card(*, agency_id: uuid.UUID, label: str, card_type: str) -> DecisionCard:
    """Создаёт ORM-снимок persisted DecisionCard без обращения к хранилищу."""
    return DecisionCard(
        decision_card_id=uuid.uuid4(),
        agency_id=agency_id,
        signal_id=uuid.uuid4(),
        card_type=card_type,
        title=f"Карточка {label}",
        summary=f"Краткое описание {label}",
        why_it_matters=f"Причина {label}",
        what_to_do=f"Действие {label}",
        deadline="сегодня",
        money_effect_raw=Decimal("1000.00"),
        currency="RUB",
        money_effect_display="+1 000 ₽",
        score=85.0,
        confidence=0.9,
        priority="high",
        status="active",
        feedback_state="pending",
        reasoning="Проверочный snapshot",
        score_breakdown={},
        audit_metadata={},
    )


def _brief(
    *,
    agency_id: uuid.UUID,
    brief_date: date = date(2026, 8, 19),
    opportunity_card_ids: list[uuid.UUID] | None = None,
    risk_card_ids: list[uuid.UUID] | None = None,
    market_card_ids: list[uuid.UUID] | None = None,
    main_decision_card_id: uuid.UUID | None = None,
) -> MorningBrief:
    """Создаёт ORM-снимок persisted MorningBrief для публичного read-контракта."""
    return MorningBrief(
        brief_id=uuid.uuid4(),
        agency_id=agency_id,
        date=brief_date,
        generated_at=datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc),
        status=MorningBriefStatusEnum.draft,
        main_decision_card_id=main_decision_card_id,
        top_opportunity_card_ids=[str(card_id) for card_id in opportunity_card_ids or []],
        top_risk_card_ids=[str(card_id) for card_id in risk_card_ids or []],
        market_insight_card_ids=[str(card_id) for card_id in market_card_ids or []],
        opportunities_snapshot={},
        risks_snapshot={},
        market_insights_snapshot={},
        main_action_snapshot={} if main_decision_card_id is not None else None,
        summary_text="Краткий persisted бриф",
        summary_snapshot={},
        statistics_snapshot={},
        input_signal_ids=[],
        idempotency_key=f"read-api-{uuid.uuid4()}",
        feature_flags_snapshot={},
    )


def test_read_service_composition_uses_request_session() -> None:
    """Composition root создаёт реальный read-сервис на переданной request-сессии."""
    session = object()

    service = build_morning_brief_read_service(session)  # type: ignore[arg-type]

    assert isinstance(service, MorningBriefReadService)
    assert service.repository.session is session


def test_get_persisted_morning_brief_returns_cards_in_persisted_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detail GET возвращает DTO и сохранённый порядок карточек каждой секции."""
    agency_id = uuid.uuid4()
    first_opportunity = _card(agency_id=agency_id, label="возможность 1", card_type="opportunity")
    second_opportunity = _card(agency_id=agency_id, label="возможность 2", card_type="opportunity")
    risk = _card(agency_id=agency_id, label="риск", card_type="risk")
    market = _card(agency_id=agency_id, label="рынок", card_type="market_insight")
    brief = _brief(
        agency_id=agency_id,
        opportunity_card_ids=[second_opportunity.decision_card_id, first_opportunity.decision_card_id],
        risk_card_ids=[risk.decision_card_id],
        market_card_ids=[market.decision_card_id],
        main_decision_card_id=risk.decision_card_id,
    )
    result = MorningBriefReadResult(
        brief=brief,
        opportunity_cards=(second_opportunity, first_opportunity),
        risk_cards=(risk,),
        market_insight_cards=(market,),
        main_decision_card=risk,
    )
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    class ReadServiceStub:
        def __init__(self, *, session: object) -> None:
            self.session = session

        def get_brief(self, *, brief_id: uuid.UUID, agency_id: uuid.UUID) -> MorningBriefReadResult:
            calls.append((brief_id, agency_id))
            return result

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(f"/api/v1/morning-brief/{brief.brief_id}?agency_id={agency_id}")

    assert response.status_code == 200
    body = response.json()
    assert calls == [(brief.brief_id, agency_id)]
    assert body["brief_id"] == str(brief.brief_id)
    assert body["agency_id"] == str(agency_id)
    assert body["main_decision_card"]["decision_card_id"] == str(risk.decision_card_id)
    assert [card["decision_card_id"] for card in body["opportunity_cards"]] == [
        str(second_opportunity.decision_card_id),
        str(first_opportunity.decision_card_id),
    ]
    assert [card["decision_card_id"] for card in body["risk_cards"]] == [str(risk.decision_card_id)]
    assert [card["decision_card_id"] for card in body["market_insight_cards"]] == [
        str(market.decision_card_id)
    ]



def test_list_persisted_morning_brief_history_returns_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """History GET возвращает metadata-only DTO без DecisionCard в ответе."""
    expected_agency_id = uuid.uuid4()
    brief = _brief(agency_id=expected_agency_id)
    item = MorningBriefHistoryItem(
        brief=brief,
        opportunity_count=2,
        risk_count=1,
        market_insight_count=3,
        total_card_count=6,
    )

    class ReadServiceStub:
        def __init__(self, *, session: object) -> None:
            self.session = session

        def list_history(
            self,
            *,
            agency_id: uuid.UUID,
            limit: int,
            offset: int,
        ) -> tuple[MorningBriefHistoryItem, ...]:
            assert (agency_id, limit, offset) == (expected_agency_id, 20, 0)
            return (item,)

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(f"/api/v1/agencies/{expected_agency_id}/morning-briefs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "brief_id": str(brief.brief_id),
            "brief_date": "2026-08-19",
            "generated_at": "2026-08-19T08:00:00Z",
            "status": "draft",
            "summary_text": "Краткий persisted бриф",
            "opportunity_count": 2,
            "risk_count": 1,
            "market_insight_count": 3,
            "total_card_count": 6,
        }
    ]


def test_get_persisted_morning_brief_returns_404_for_unknown_brief(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Неизвестный persisted бриф не раскрывает внутреннюю причину ошибки через API."""
    requested_brief_id = uuid.uuid4()
    requested_agency_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    class ReadServiceStub:
        def __init__(self, *, session: object) -> None:
            self.session = session

        def get_brief(self, *, brief_id: uuid.UUID, agency_id: uuid.UUID) -> MorningBriefReadResult:
            calls.append((brief_id, agency_id))
            raise MorningBriefReadNotFoundError("Неизвестный persisted бриф")

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(
        f"/api/v1/morning-brief/{requested_brief_id}?agency_id={requested_agency_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "morning_brief_not_found"
    assert calls == [(requested_brief_id, requested_agency_id)]


def test_get_persisted_morning_brief_maps_integrity_error_to_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нарушение целостности persisted aggregate возвращает стабильный HTTP-код."""

    class ReadServiceStub:
        def __init__(self, *, session: object) -> None:
            self.session = session

        def get_brief(self, *, brief_id: uuid.UUID, agency_id: uuid.UUID) -> MorningBriefReadResult:
            raise MorningBriefReadIntegrityError("Отсутствует сохранённая DecisionCard")

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(f"/api/v1/morning-brief/{uuid.uuid4()}?agency_id={uuid.uuid4()}")

    assert response.status_code == 409
    assert response.json()["detail"] == "morning_brief_integrity_error"



def test_get_persisted_morning_brief_returns_404_for_wrong_agency_ownership(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Реальная ownership-проверка сервиса скрывает чужой бриф тем же HTTP-ответом."""
    owner_agency_id = uuid.uuid4()
    requested_agency_id = uuid.uuid4()
    brief = _brief(agency_id=owner_agency_id)

    class RepositoryStub:
        def get_brief_by_id(self, brief_id: uuid.UUID) -> MorningBrief:
            assert brief_id == brief.brief_id
            return brief

    class ReadServiceStub(MorningBriefReadService):
        def __init__(self, *, session: object) -> None:
            super().__init__(repository=RepositoryStub())

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(
        f"/api/v1/morning-brief/{brief.brief_id}?agency_id={requested_agency_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "morning_brief_not_found"


def test_list_persisted_morning_brief_history_passes_pagination(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """History GET передаёт limit и offset read-сервису и возвращает страницу."""
    expected_agency_id = uuid.uuid4()
    page_brief = _brief(agency_id=expected_agency_id, brief_date=date(2026, 8, 19))
    page_item = MorningBriefHistoryItem(
        brief=page_brief,
        opportunity_count=0,
        risk_count=0,
        market_insight_count=0,
        total_card_count=0,
    )
    calls: list[tuple[uuid.UUID, int, int]] = []

    class ReadServiceStub:
        def __init__(self, *, session: object) -> None:
            self.session = session

        def list_history(
            self,
            *,
            agency_id: uuid.UUID,
            limit: int,
            offset: int,
        ) -> tuple[MorningBriefHistoryItem, ...]:
            calls.append((agency_id, limit, offset))
            return (page_item,)

    monkeypatch.setattr(
        morning_brief,
        "build_morning_brief_read_service",
        lambda session: ReadServiceStub(session=session),
    )

    response = client.get(
        f"/api/v1/agencies/{expected_agency_id}/morning-briefs?limit=1&offset=1"
    )

    assert response.status_code == 200
    assert calls == [(expected_agency_id, 1, 1)]
    assert response.json()[0]["brief_id"] == str(page_brief.brief_id)
