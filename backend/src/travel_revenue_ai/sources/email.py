"""Адаптер получения сырых сигналов из email-источника."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum
from travel_revenue_ai.services.email_deduplication_service import EmailDeduplicationService
from travel_revenue_ai.services.email_ingestion_metrics import EmailIngestionMetrics
from travel_revenue_ai.services.email_normalizer_service import EmailNormalizerService
from travel_revenue_ai.services.email_signal_classifier import EmailSignalClassifier
from travel_revenue_ai.sources.base import BaseSourceAdapter
from travel_revenue_ai.sources.mock_email_provider import MockEmailProvider
from travel_revenue_ai.sources.provider_contracts import EmailMessage, EmailProvider

logger = logging.getLogger(__name__)


class EmailSourceAdapter(BaseSourceAdapter):
    """Преобразует письма провайдера в новые сырые сигналы.

    Адаптер ограничен ingestion-слоем: он не сохраняет сигналы в БД и не
    запускает обработку PipelineService.
    """

    def __init__(
        self,
        *,
        agency_id: UUID,
        source_id: UUID | None,
        provider: EmailProvider | None = None,
        normalizer: EmailNormalizerService | None = None,
        classifier: EmailSignalClassifier | None = None,
        deduplication_service: EmailDeduplicationService | None = None,
        metrics: EmailIngestionMetrics | None = None,
        config: dict[str, Any] | None = None,
        adapter_name: str = "email",
    ) -> None:
        """Инициализирует адаптер и его инфраструктурные зависимости."""
        super().__init__(
            adapter_name=adapter_name,
            agency_id=agency_id,
            source_id=source_id,
            config=config,
        )
        self._provider = provider or MockEmailProvider()
        self._normalizer = normalizer or EmailNormalizerService()
        self._classifier = classifier or EmailSignalClassifier()
        self._deduplication_service = deduplication_service or EmailDeduplicationService()
        self._metrics = metrics or EmailIngestionMetrics()

    @property
    def metrics(self) -> EmailIngestionMetrics:
        """Возвращает счётчики текущего экземпляра email ingestion."""
        return self._metrics

    def collect_signals(self) -> list[Signal]:
        """Собирает уникальные письма и создаёт новые ``Signal``.

        Ошибка чтения провайдера журналируется и передаётся выше, сохраняя
        существующую модель обработки ошибок через SourceManager.
        """
        try:
            messages = self._provider.fetch_messages()
        except Exception:
            self._metrics.increment("emails_failed")
            logger.exception(
                "email_read_failed",
                extra={"event": "email_read_failed", "adapter_name": self.adapter_name},
            )
            raise

        signals: list[Signal] = []
        for message in messages:
            self._metrics.increment("emails_received")
            logger.info(
                "email_received",
                extra={
                    "event": "email_received",
                    "adapter_name": self.adapter_name,
                    "message_id": self._safe_message_id(message),
                },
            )

            try:
                if not self._deduplication_service.should_process(message_id=message.message_id):
                    self._metrics.increment("emails_skipped")
                    logger.info(
                        "email_duplicated",
                        extra={
                            "event": "email_duplicated",
                            "adapter_name": self.adapter_name,
                            "message_id": message.message_id,
                        },
                    )
                    continue
            except ValueError:
                self._metrics.increment("emails_skipped")
                logger.warning(
                    "email_skipped",
                    extra={
                        "event": "email_skipped",
                        "adapter_name": self.adapter_name,
                        "reason": "invalid_message_id",
                    },
                )
                continue

            try:
                signal = self._to_signal(message)
            except Exception:
                self._deduplication_service.forget(message_id=message.message_id)
                self._metrics.increment("emails_failed")
                logger.exception(
                    "email_classification_failed",
                    extra={
                        "event": "email_classification_failed",
                        "adapter_name": self.adapter_name,
                        "message_id": message.message_id,
                    },
                )
                continue

            signals.append(signal)
            self._metrics.increment("emails_processed")
            self._metrics.increment("signals_created")
            logger.info(
                "email_processed",
                extra={
                    "event": "email_processed",
                    "adapter_name": self.adapter_name,
                    "message_id": message.message_id,
                },
            )

        return signals

    def _to_signal(self, message: EmailMessage) -> Signal:
        """Нормализует, классифицирует и преобразует письмо в объект Signal."""
        normalized_text = self._normalizer.normalize(
            subject=message.subject,
            body=message.body,
        )
        signal_type = self._classifier.classify(normalized_text)

        return Signal(
            agency_id=self.agency_id,
            source_id=self.source_id,
            signal_type=signal_type,
            status=SignalStatusEnum.new,
            raw_data={
                "channel": "email",
                "message_id": message.message_id,
                "from": message.sender,
                "to": message.recipient,
                "subject": message.subject,
                "body": message.body,
                "normalized_text": normalized_text,
                "received_at": message.received_at.isoformat(),
            },
        )

    @staticmethod
    def _safe_message_id(message: EmailMessage) -> str | None:
        """Возвращает технический идентификатор без содержимого письма."""
        message_id = getattr(message, "message_id", None)
        return message_id if isinstance(message_id, str) and message_id else None