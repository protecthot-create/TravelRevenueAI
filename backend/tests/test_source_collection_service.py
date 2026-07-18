"""Unit-тесты SourceCollectionService без БД, сети и внешних провайдеров."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.services.source_collection_service import SourceCollectionService
from travel_revenue_ai.sources.base import BaseSourceAdapter
from travel_revenue_ai.sources.manager import SourceManager


@dataclass
class FakeMorningBriefResult:
    """Минимальный заменитель результата pipeline для unit-тестов."""

    marker: str = "brief"


class StubAdapter(BaseSourceAdapter):
    """Адаптер с заранее заданными сигналами или ошибкой."""

    def __init__(
        self,
        *,
        adapter_name: str,
        agency_id: UUID,
        source_id: UUID,
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
        """Возвращает преднастроенные данные без внешнего вызова."""
        if self._error is not None:
            raise self._error
        return self._signals


class FakeSignalService:
    """Сохраняет сигналы в памяти и по запросу имитирует ошибку БД."""

    def __init__(self, failing_raw_data: dict[str, object] | None = None) -> None:
        self.failing_raw_data = failing_raw_data
        self.saved_signals: list[Signal] = []

    def create_signal(
        self,
        *,
        agency_id: UUID,
        source_id: UUID | None,
        signal_type: SignalTypeEnum,
        raw_data: dict[str, object],
    ) -> Signal:
        """Создаёт in-memory сигнал с новым идентификатором."""
        if raw_data == self.failing_raw_data:
            raise RuntimeError("Не удалось сохранить сигнал")

        signal = Signal(
            agency_id=agency_id,
            source_id=source_id,
            signal_type=signal_type,
            status=SignalStatusEnum.new,
            raw_data=raw_data,
        )
        self.saved_signals.append(signal)
        return signal


class FakePipelineService:
    """Фиксирует вход pipeline и возвращает преднастроенный бриф."""

    def __init__(self, result: FakeMorningBriefResult) -> None:
        self.result = result
        self.received_signals: list[Signal] | None = None

    def generate_morning_brief(self, signals: list[Signal]) -> FakeMorningBriefResult:
        """Сохраняет переданные сигналы без запуска реального pipeline."""
        self.received_signals = signals
        return self.result


def make_signal(
    agency_id: UUID,
    source_id: UUID,
    *,
    marker: str,
) -> Signal:
    """Создаёт корректный собранный сигнал."""
    return Signal(
        agency_id=agency_id,
        source_id=source_id,
        signal_type=SignalTypeEnum.market,
        status=SignalStatusEnum.new,
        raw_data={
            "marker": marker,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def test_collects_saves_and_generates_brief() -> None:
    """Оркестратор собирает, сохраняет и передаёт сохранённые сигналы в pipeline."""
    agency_id = uuid4()
    email_source_id = uuid4()
    telegram_source_id = uuid4()
    email_signal = make_signal(agency_id, email_source_id, marker="email")
    telegram_signal = make_signal(agency_id, telegram_source_id, marker="telegram")
    source_manager = SourceManager(
        [
            StubAdapter(
                adapter_name="email",
                agency_id=agency_id,
                source_id=email_source_id,
                signals=[email_signal],
            ),
            StubAdapter(
                adapter_name="telegram",
                agency_id=agency_id,
                source_id=telegram_source_id,
                signals=[telegram_signal],
            ),
        ]
    )
    signal_service = FakeSignalService()
    brief = FakeMorningBriefResult()
    pipeline_service = FakePipelineService(brief)
    service = SourceCollectionService(
        source_manager=source_manager,
        signal_service=signal_service,  # type: ignore[arg-type]
        pipeline_service=pipeline_service,  # type: ignore[arg-type]
    )

    result = service.collect_and_generate_morning_brief()

    assert result.collected_count == 2
    assert result.saved_count == 2
    assert result.errors_count == 0
    assert result.morning_brief is brief
    assert pipeline_service.received_signals == signal_service.saved_signals
    assert pipeline_service.received_signals is not None
    assert pipeline_service.received_signals != [email_signal, telegram_signal]


def test_registers_email_and_telegram_adapters() -> None:
    """Конструктор регистрирует переданные Email и Telegram адаптеры."""
    agency_id = uuid4()
    email_source_id = uuid4()
    telegram_source_id = uuid4()
    source_manager = SourceManager()
    service = SourceCollectionService(
        source_manager=source_manager,
        signal_service=FakeSignalService(),  # type: ignore[arg-type]
        pipeline_service=FakePipelineService(FakeMorningBriefResult()),  # type: ignore[arg-type]
        email_source_adapter=StubAdapter(
            adapter_name="email",
            agency_id=agency_id,
            source_id=email_source_id,
        ),  # type: ignore[arg-type]
        telegram_source_adapter=StubAdapter(
            adapter_name="telegram",
            agency_id=agency_id,
            source_id=telegram_source_id,
        ),  # type: ignore[arg-type]
    )

    assert service.source_manager.adapter_names == ("email", "telegram")


def test_isolates_source_and_save_errors() -> None:
    """Ошибка источника или одного сохранения не отменяет остальные сигналы."""
    agency_id = uuid4()
    successful_source_id = uuid4()
    failed_source_id = uuid4()
    failed_signal = make_signal(agency_id, successful_source_id, marker="failed-save")
    saved_signal = make_signal(agency_id, successful_source_id, marker="saved")
    source_manager = SourceManager(
        [
            StubAdapter(
                adapter_name="working",
                agency_id=agency_id,
                source_id=successful_source_id,
                signals=[failed_signal, saved_signal],
            ),
            StubAdapter(
                adapter_name="broken",
                agency_id=agency_id,
                source_id=failed_source_id,
                error=RuntimeError("Источник недоступен"),
            ),
        ]
    )
    signal_service = FakeSignalService(failing_raw_data=failed_signal.raw_data)
    pipeline_service = FakePipelineService(FakeMorningBriefResult())
    service = SourceCollectionService(
        source_manager=source_manager,
        signal_service=signal_service,  # type: ignore[arg-type]
        pipeline_service=pipeline_service,  # type: ignore[arg-type]
    )

    result = service.collect_and_generate_morning_brief()

    assert result.collected_count == 2
    assert result.saved_count == 1
    assert result.errors_count == 2
    assert pipeline_service.received_signals == signal_service.saved_signals