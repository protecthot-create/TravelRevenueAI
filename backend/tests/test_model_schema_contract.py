"""Контрактные тесты ORM-метаданных без подключения к базе данных."""

from sqlalchemy import DateTime

from travel_revenue_ai.models.action import Action
from travel_revenue_ai.models.agency import Agency
from travel_revenue_ai.models.data_source import DataSource
from travel_revenue_ai.models.decision_card import DecisionCard
from travel_revenue_ai.models.morning_brief import MorningBrief
from travel_revenue_ai.models.signal import Signal


TIMESTAMP_MODELS = (Signal, DataSource, DecisionCard, MorningBrief)
MODELS_WITHOUT_AUDIT_TIMESTAMPS = (Agency, Action)


def test_timestamp_mixin_is_applied_only_to_models_with_timestamp_columns() -> None:
    """Audit-timestamps не должны появляться у всех ORM-моделей неявно."""
    for model in TIMESTAMP_MODELS:
        assert {"created_at", "updated_at"} <= set(model.__table__.columns.keys())

    for model in MODELS_WITHOUT_AUDIT_TIMESTAMPS:
        assert "created_at" not in model.__table__.columns
        assert "updated_at" not in model.__table__.columns


def test_timestamp_columns_keep_postgresql_orm_contract() -> None:
    """Mixin сохраняет тип, server default и ORM-update callback timestamps."""
    for model in TIMESTAMP_MODELS:
        created_at = model.__table__.c.created_at
        updated_at = model.__table__.c.updated_at

        assert isinstance(created_at.type, DateTime)
        assert isinstance(updated_at.type, DateTime)
        assert created_at.type.timezone is True
        assert updated_at.type.timezone is True
        assert created_at.nullable is False
        assert updated_at.nullable is False
        assert created_at.server_default is not None
        assert updated_at.server_default is not None
        assert updated_at.onupdate is not None


def test_business_timestamps_remain_model_specific() -> None:
    """Бизнес-временные поля не заменяются audit-timestamps."""
    assert "generated_at" in DecisionCard.__table__.columns
    assert "generated_at" in MorningBrief.__table__.columns
    assert "last_sync" in DataSource.__table__.columns