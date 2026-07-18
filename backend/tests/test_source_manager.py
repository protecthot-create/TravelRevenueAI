"""Тесты контрактов Source Adapter Framework."""

from uuid import UUID, uuid4

import pytest

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.sources import BaseSourceAdapter, SourceManager


class StubAdapter(BaseSourceAdapter):
    """Тестовый адаптер без внешней интеграции."""

    def __init__(
        self,
        *,
        adapter_name: str,
        agency_id: UUID,
        source_id: UUID | None,
        signals: list[Signal] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(
            adapter_name=adapter_name,
            agency_id=agency_id,
            source_id=source_id,
        )
        self._signals = signals or []
        self._error = error

    def collect_signals(self) -> list[Signal]:
        """Возвращает преднастроенный результат для теста."""
        if self._error is not None:
            raise self._error
        return self._signals


def make_signal(agency_id: UUID, source_id: UUID | None) -> Signal:
    """Создаёт корректный сырой сигнал."""
    return Signal(
        agency_id=agency_id,
        source_id=source_id,
        signal_type=SignalTypeEnum.market,
        status=SignalStatusEnum.new,
        raw_data={"event": "test"},
    )


def test_collect_returns_signals_and_metadata() -> None:
    """Менеджер возвращает сигналы и метаданные успешного сбора."""
    agency_id = uuid4()
    source_id = uuid4()
    adapter = StubAdapter(
        adapter_name="stub",
        agency_id=agency_id,
        source_id=source_id,
        signals=[make_signal(agency_id, source_id)],
    )
    manager = SourceManager([adapter])

    result = manager.collect("stub")

    assert result.is_successful
    assert len(result.signals) == 1
    assert result.metadata.adapter_name == "stub"
    assert result.metadata.agency_id == agency_id
    assert result.metadata.source_id == source_id


def test_collect_converts_adapter_error_to_result() -> None:
    """Ошибка одного адаптера не выбрасывается за пределы source-layer."""
    adapter = StubAdapter(
        adapter_name="broken",
        agency_id=uuid4(),
        source_id=uuid4(),
        error=RuntimeError("Источник временно недоступен"),
    )

    result = SourceManager([adapter]).collect("broken")

    assert not result.is_successful
    assert result.signals == []
    assert result.error == "Источник временно недоступен"


def test_collect_all_isolates_adapter_errors() -> None:
    """Сбой одного источника не отменяет сбор у остальных адаптеров."""
    agency_id = uuid4()
    source_id = uuid4()
    manager = SourceManager(
        [
            StubAdapter(
                adapter_name="success",
                agency_id=agency_id,
                source_id=source_id,
                signals=[make_signal(agency_id, source_id)],
            ),
            StubAdapter(
                adapter_name="broken",
                agency_id=agency_id,
                source_id=uuid4(),
                error=RuntimeError("Источник временно недоступен"),
            ),
        ]
    )

    results = manager.collect_all()

    assert [result.metadata.adapter_name for result in results] == ["success", "broken"]
    assert results[0].is_successful
    assert not results[1].is_successful


def test_collect_rejects_signal_for_another_agency() -> None:
    """Менеджер помечает ошибкой нарушение agency boundary."""
    adapter_agency_id = uuid4()
    adapter = StubAdapter(
        adapter_name="invalid",
        agency_id=adapter_agency_id,
        source_id=uuid4(),
        signals=[make_signal(uuid4(), None)],
    )

    result = SourceManager([adapter]).collect("invalid")

    assert not result.is_successful
    assert result.error == "Сигнал содержит agency_id другого агентства"


def test_register_rejects_duplicate_adapter_name() -> None:
    """Реестр не допускает неявную замену зарегистрированного адаптера."""
    agency_id = uuid4()
    manager = SourceManager()
    manager.register(
        StubAdapter(adapter_name="duplicate", agency_id=agency_id, source_id=uuid4())
    )

    with pytest.raises(ValueError, match="уже зарегистрирован"):
        manager.register(
            StubAdapter(adapter_name="duplicate", agency_id=agency_id, source_id=uuid4())
        )