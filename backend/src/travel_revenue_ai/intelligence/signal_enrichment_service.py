"""Сервис обогащения Signal структурированными rule-based признаками."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import date
from time import perf_counter
from typing import Any

from travel_revenue_ai.intelligence.context import SignalContext, SignalPriority
from travel_revenue_ai.intelligence.duplicate_detector import DuplicateSignalDetector
from travel_revenue_ai.intelligence.entity_extractor import EntityExtractor, ExtractedEntities
from travel_revenue_ai.intelligence.priority_estimator import SignalPriorityEstimator
from travel_revenue_ai.observability.feature_flags import FeatureFlagService
from travel_revenue_ai.observability.metrics import MetricsService

logger = logging.getLogger(__name__)


class SignalEnrichmentService:
    """Собирает единый Intelligence Layer поверх raw_data.

    Сервис не изменяет переданный ``raw_data`` и не сохраняет данные в БД.
    Вызывающая сторона сама решает, когда и куда записать возвращённый JSON.
    """

    def __init__(
        self,
        *,
        entity_extractor: EntityExtractor | None = None,
        duplicate_detector: DuplicateSignalDetector | None = None,
        priority_estimator: SignalPriorityEstimator | None = None,
        feature_flag_service: FeatureFlagService | None = None,
        metrics_service: MetricsService | None = None,
    ) -> None:
        """Инициализирует rule-based компоненты и необязательные observability-зависимости."""
        self._entity_extractor = entity_extractor or EntityExtractor()
        self._duplicate_detector = duplicate_detector or DuplicateSignalDetector()
        self._priority_estimator = priority_estimator or SignalPriorityEstimator()
        self._feature_flags = feature_flag_service or FeatureFlagService()
        self._metrics = metrics_service or MetricsService()

    def enrich(
        self,
        raw_data: Mapping[str, Any],
        *,
        known_signals: Iterable[Mapping[str, Any]] = (),
        reference_date: date | None = None,
    ) -> dict[str, Any]:
        """Возвращает копию raw_data с ``metadata.intelligence``.

        Исходный словарь и его вложенные значения не мутируются. Ранее
        существующие ``metadata`` сохраняются без изменений.
        """
        started_at = perf_counter()
        try:
            enriched = deepcopy(dict(raw_data))
            if not self._feature_flags.is_enabled("intelligence_enabled"):
                logger.info("intelligence_enrichment_skipped intelligence_enabled=false")
                return enriched

            text = self._source_text(raw_data)
            entities = self._extract_entities(text, reference_date)
            duplicates = self._detect_duplicates(raw_data, known_signals)
            priority = self._estimate_priority(
                text=text,
                entities=entities,
                reference_date=reference_date,
            )
            context = SignalContext(
                countries=entities.countries,
                cities=entities.cities,
                operators=entities.operators,
                airlines=entities.airlines,
                hotels=entities.hotels,
                directions=entities.directions,
                currencies=entities.currencies,
                discounts=entities.discounts,
                dates=entities.dates,
                deadline=entities.deadline,
                priority=priority,
                entities=entities.to_dict(),
                language=entities.language,
                duplicates=duplicates,
            )

            metadata = enriched.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            else:
                metadata = deepcopy(metadata)
            metadata["intelligence"] = context.to_metadata()
            enriched["metadata"] = metadata

            logger.info(
                "signal_enriched entities_found=%s duplicates_found=%s",
                self._entity_count(entities),
                self._duplicate_count(duplicates),
            )
            return enriched
        except Exception:
            self._metrics.increment("enrichment_errors")
            logger.exception("signal_enrichment_failed")
            raise
        finally:
            duration_ms = int((perf_counter() - started_at) * 1000)
            self._metrics.record_duration_ms("enrichment_duration_ms", duration_ms)

    def _extract_entities(
        self,
        text: str,
        reference_date: date | None,
    ) -> ExtractedEntities:
        """Выполняет entity extraction либо создаёт совместимый пустой результат."""
        if self._feature_flags.is_enabled("entity_extraction_enabled"):
            return self._entity_extractor.extract(text, reference_date=reference_date)

        return ExtractedEntities(
            countries=[],
            cities=[],
            operators=[],
            airlines=[],
            hotels=[],
            directions=[],
            currencies=[],
            discounts=[],
            dates=[],
            deadline=None,
            language="unknown",
        )

    def _detect_duplicates(
        self,
        raw_data: Mapping[str, Any],
        known_signals: Iterable[Mapping[str, Any]],
    ) -> dict[str, object]:
        """Выполняет duplicate detection только при включённом флаге."""
        if not self._feature_flags.is_enabled("duplicate_detection_enabled"):
            return {}

        return self._duplicate_detector.detect(raw_data, known_signals).to_metadata()

    def _estimate_priority(
        self,
        *,
        text: str,
        entities: ExtractedEntities,
        reference_date: date | None,
    ) -> SignalPriority:
        """Оценивает приоритет только при включённом флаге."""
        if not self._feature_flags.is_enabled("intelligence_priority_enabled"):
            return SignalPriority.LOW

        return self._priority_estimator.estimate(
            text=text,
            discounts=entities.discounts,
            deadline=entities.deadline,
            operators=entities.operators,
            reference_date=reference_date,
        )

    @staticmethod
    def _entity_count(entities: ExtractedEntities) -> int:
        """Считает найденные сущности без записи исходного текста в лог."""
        return sum(
            len(values)
            for values in (
                entities.countries,
                entities.cities,
                entities.operators,
                entities.airlines,
                entities.hotels,
                entities.currencies,
                entities.discounts,
                entities.dates,
            )
        )

    @staticmethod
    def _duplicate_count(duplicates: Mapping[str, object]) -> int:
        """Возвращает число дублей из JSON metadata detector-а."""
        duplicate_items = duplicates.get("duplicates")
        return len(duplicate_items) if isinstance(duplicate_items, list) else 0

    @staticmethod
    def _source_text(raw_data: Mapping[str, Any]) -> str:
        """Выбирает текст, не меняя исходные поля источника."""
        for key in ("normalized_text", "text"):
            value = raw_data.get(key)
            if isinstance(value, str) and value.strip():
                return value

        return " ".join(
            value.strip()
            for key in ("subject", "body")
            if isinstance((value := raw_data.get(key)), str) and value.strip()
        )