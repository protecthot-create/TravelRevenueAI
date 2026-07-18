"""Сервис фильтрации сигналов (Filtering Engine).

Фильтрует сигналы, прошедшие оценку Revenue Scoring Engine.
Отбирает только те, которые несут денежную ценность, и отбрасывает шум.

Spec: docs/system_architecture.md (секция 4), filtering_rules.md, importance_rules.md

Архитектурные решения:
- Сервис не зависит от FastAPI, работает только с доменными моделями.
- FilterResult — независимая структура данных, не привязана к ORM.
- Интерфейс FilteringStrategy позволяет подменять алгоритм фильтрации.
- Полная реализация: DefaultFilteringStrategy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from travel_revenue_ai.services.revenue_scoring_service import (
    PriorityLabel,
    ScoreResult,
)


# =============================================================================
# Константы порогов фильтрации
# =============================================================================

# Минимальный score для прохождения фильтра (по умолчанию)
DEFAULT_MIN_SCORE: float = 16.0  # выше SCORE_NOISE_MAX (15)

# Минимальный confidence для прохождения фильтра
DEFAULT_MIN_CONFIDENCE: float = 0.3  # 30%

# Максимальное количество сигналов в выходном списке
DEFAULT_MAX_SIGNALS: int = 10

# Порог для определения дубликата по score
# Сигналы с разницей score < этого значения считаются дубликатами
DUPLICATE_SCORE_THRESHOLD: float = 2.0


# =============================================================================
# Типы и перечисления
# =============================================================================

class FilterDecision(str, Enum):
    """Решение фильтра о судьбе сигнала.

    Соответствует разделу 4 system_architecture.md:
    - pass: сигнал прошёл фильтр
    - reject: сигнал отклонён
    - needs_review: требует ручной проверки
    """

    pass_ = "pass"
    reject = "reject"
    needs_review = "needs_review"


class FilterReason(str, Enum):
    """Причина отклонения или прохождения сигнала.

    Используется для объяснения решения фильтра.
    """

    # Причины прохождения
    PASSED_SCORE = "passed_score"
    PASSED_HIGH_PRIORITY = "passed_high_priority"
    PASSED_URGENT = "passed_urgent"
    PASSED_MANUAL_OVERRIDE = "passed_manual_override"

    # Причины отклонения
    REJECTED_LOW_SCORE = "rejected_low_score"
    REJECTED_LOW_CONFIDENCE = "rejected_low_confidence"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_LOW_MONEY_EFFECT = "rejected_low_money_effect"
    REJECTED_VERY_LOW_PROBABILITY = "rejected_very_low_probability"
    REJECTED_LIMIT_EXCEEDED = "rejected_limit_exceeded"


# =============================================================================
# Структуры данных результата
# =============================================================================

@dataclass
class FilterRejection:
    """Причина отклонения сигнала.

    Attributes:
        reason: Код причины отклонения.
        explanation: Человекочитаемое объяснение.
        details: Дополнительные детали (опционально).
    """

    reason: FilterReason
    explanation: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterResult:
    """Результат фильтрации одного сигнала.

    Структура соответствует разделу 4 system_architecture.md:
    - решение: pass / reject / needs_review
    - причина прохождения или отклонения
    - категория отклонения
    - метка конфликтности

    Attributes:
        signal_id: Идентификатор оценённого сигнала.
        decision: Решение фильтра.
        passed: True если сигнал прошёл фильтр.
        rejection: Причина отклонения (если applicable).
        priority_order: Порядок приоритета для сортировки (меньше = важнее).
        is_duplicate: True если сигнал является дубликатом.
        duplicate_of: ID сигнала-оригинала, если is_duplicate=True.
    """

    signal_id: uuid.UUID
    decision: FilterDecision = FilterDecision.reject
    passed: bool = False
    rejection: FilterRejection | None = None
    priority_order: int = 999  # Чем меньше, тем важнее
    is_duplicate: bool = False
    duplicate_of: uuid.UUID | None = None


@dataclass
class FilteringResult:
    """Результат фильтрации списка сигналов.

    Attributes:
        passed_signals: Список прошедших фильтр результатов (отсортирован по приоритету).
        rejected_signals: Список отклонённых результатов.
        total_input: Общее количество входных сигналов.
        total_passed: Количество прошедших.
        total_rejected: Количество отклонённых.
        duplicates_found: Количество найденных дубликатов.
    """

    passed_signals: list[FilterResult] = field(default_factory=list)
    rejected_signals: list[FilterResult] = field(default_factory=list)
    total_input: int = 0
    total_passed: int = 0
    total_rejected: int = 0
    duplicates_found: int = 0


class FilteringStrategy(Protocol):
    """Протокол для стратегий фильтрации.

    Позволяет подменять алгоритм фильтрации без изменения FilteringService.
    """

    def filter(
        self,
        score_results: list[ScoreResult],
        min_score: float,
        min_confidence: float,
        max_signals: int,
    ) -> FilteringResult:
        """Фильтрует список оценённых сигналов.

        Args:
            score_results: Список результатов от Revenue Scoring Engine.
            min_score: Минимальный score для прохождения.
            min_confidence: Минимальный confidence для прохождения.
            max_signals: Максимальное количество сигналов в выходном списке.

        Returns:
            Результат фильтрации с прошедшими и отклонёнными сигналами.
        """
        ...


# =============================================================================
# Полноценная стратегия фильтрации
# =============================================================================

class DefaultFilteringStrategy:
    """Стратегия фильтрации по умолчанию.

    Реализует все правила из filtering_rules.md и importance_rules.md:
    - Фильтрация по минимальному Score
    - Фильтрация по confidence
    - Удаление дубликатов
    - Сортировка по приоритету
    - Ограничение количества
    - Объяснение причин отклонения
    """

    def filter(
        self,
        score_results: list[ScoreResult],
        min_score: float,
        min_confidence: float,
        max_signals: int,
    ) -> FilteringResult:
        """Фильтрует список оценённых сигналов.

        Процесс:
        1. Первичная фильтрация по score и confidence
        2. Удаление дубликатов
        3. Сортировка по приоритету (риски важнее возможностей)
        4. Ограничение количества
        5. Формирование результата с объяснениями
        """
        if not score_results:
            return FilteringResult(total_input=0)

        result = FilteringResult(total_input=len(score_results))
        candidates: list[tuple[ScoreResult, FilterResult]] = []

        # Шаг 1: Первичная фильтрация
        for score_result in score_results:
            filter_result = self._evaluate_signal(
                score_result, min_score, min_confidence
            )

            if filter_result.passed:
                candidates.append((score_result, filter_result))
            else:
                result.rejected_signals.append(filter_result)

        # Шаг 2: Удаление дубликатов
        candidates, duplicates_count = self._remove_duplicates(candidates)
        result.duplicates_found = duplicates_count

        # Шаг 3: Сортировка по приоритету
        candidates = self._sort_by_priority(candidates)

        # Шаг 4: Ограничение количества
        passed = candidates[:max_signals]
        not_passed = candidates[max_signals:]

        # Формируем результаты для прошедших
        for idx, (score_result, filter_result) in enumerate(passed):
            filter_result.priority_order = idx
            result.passed_signals.append(filter_result)

        # Отклоняем не прошедших лимит
        for score_result, _ in not_passed:
            filter_result = FilterResult(
                signal_id=score_result.signal_id,
                decision=FilterDecision.reject,
                passed=False,
                rejection=FilterRejection(
                    reason=FilterReason.REJECTED_LIMIT_EXCEEDED,
                    explanation=(
                        f"Сигнал отклонён: превышен лимит результатов (max={max_signals}). "
                        f"Score={score_result.score:.1f}, Priority={score_result.priority_label.value}"
                    ),
                    details={
                        "score": score_result.score,
                        "priority_label": score_result.priority_label.value,
                    },
                ),
                priority_order=999,
            )
            result.rejected_signals.append(filter_result)

        # Подсчитываем статистику
        result.total_passed = len(result.passed_signals)
        result.total_rejected = len(result.rejected_signals)

        return result

    def _evaluate_signal(
        self,
        score_result: ScoreResult,
        min_score: float,
        min_confidence: float,
    ) -> FilterResult:
        """Оценивает один сигнал по правилам фильтрации.

        Returns:
            FilterResult с решением и объяснением.
        """
        # Проверка 1: Score ниже порога
        if score_result.score < min_score:
            return FilterResult(
                signal_id=score_result.signal_id,
                decision=FilterDecision.reject,
                passed=False,
                rejection=FilterRejection(
                    reason=FilterReason.REJECTED_LOW_SCORE,
                    explanation=(
                        f"Score={score_result.score:.1f} ниже минимального порога={min_score:.1f}"
                    ),
                    details={
                        "score": score_result.score,
                        "min_score": min_score,
                        "priority_label": score_result.priority_label.value,
                    },
                ),
            )

        # Проверка 2: Confidence ниже порога
        if score_result.confidence < min_confidence:
            return FilterResult(
                signal_id=score_result.signal_id,
                decision=FilterDecision.reject,
                passed=False,
                rejection=FilterRejection(
                    reason=FilterReason.REJECTED_LOW_CONFIDENCE,
                    explanation=(
                        f"Confidence={score_result.confidence:.2f} ниже минимального={min_confidence:.2f}. "
                        "Недостаточно данных для уверенной рекомендации."
                    ),
                    details={
                        "confidence": score_result.confidence,
                        "min_confidence": min_confidence,
                    },
                ),
            )

        # Проверка 3: Критический риск всегда проходит
        if score_result.priority_label == PriorityLabel.critical:
            return FilterResult(
                signal_id=score_result.signal_id,
                decision=FilterDecision.pass_,
                passed=True,
                rejection=None,
                priority_order=0,  # Самый высокий приоритет
            )

        # Проверка 4: Высокий приоритет проходит
        if score_result.priority_label == PriorityLabel.high:
            return FilterResult(
                signal_id=score_result.signal_id,
                decision=FilterDecision.pass_,
                passed=True,
                rejection=None,
                priority_order=10,
            )

        # Сигнал прошёл все проверки
        return FilterResult(
            signal_id=score_result.signal_id,
            decision=FilterDecision.pass_,
            passed=True,
            rejection=None,
            priority_order=20,
        )

    def _remove_duplicates(
        self,
        candidates: list[tuple[ScoreResult, FilterResult]],
    ) -> tuple[list[tuple[ScoreResult, FilterResult]], int]:
        """Удаляет дубликаты из списка кандидатов.

        Дубликатами считаются сигналы с близким score.

        Returns:
            Кортеж (отфильтрованный_список, количество_дубликатов).
        """
        if not candidates:
            return [], 0

        unique: list[tuple[ScoreResult, FilterResult]] = []
        duplicates_count = 0

        for score_result, filter_result in candidates:
            is_duplicate = False

            for unique_result, _ in unique:
                # Проверяем близость score
                score_diff = abs(score_result.score - unique_result.score)

                # Если score близки — это дубликат
                if score_diff < DUPLICATE_SCORE_THRESHOLD:
                    is_duplicate = True
                    duplicates_count += 1

                    # Отмечаем в FilterResult
                    filter_result.is_duplicate = True
                    filter_result.duplicate_of = unique_result.signal_id
                    filter_result.decision = FilterDecision.reject
                    filter_result.passed = False
                    filter_result.rejection = FilterRejection(
                        reason=FilterReason.REJECTED_DUPLICATE,
                        explanation=(
                            f"Дубликат сигнала {unique_result.signal_id}. "
                            f"Score отличается на {score_diff:.1f}"
                        ),
                        details={
                            "original_signal_id": str(unique_result.signal_id),
                            "score_diff": score_diff,
                        },
                    )
                    break

            if not is_duplicate:
                unique.append((score_result, filter_result))

        return unique, duplicates_count

    def _sort_by_priority(
        self,
        candidates: list[tuple[ScoreResult, FilterResult]],
    ) -> list[tuple[ScoreResult, FilterResult]]:
        """Сортирует кандидатов по приоритету.

        Правила сортировки (из importance_rules.md):
        1. Риски важнее возможностей при равных деньгах
        2. Чем выше score, тем важнее
        3. Чем короче дедлайн, тем важнее
        """
        def sort_key(item: tuple[ScoreResult, FilterResult]) -> tuple:
            score_result, _ = item

            # Приоритет по priority_label: critical (-1) важнее high (0) и т.д.
            label_order = {
                PriorityLabel.critical: 0,
                PriorityLabel.high: 1,
                PriorityLabel.medium: 2,
                PriorityLabel.low: 3,
                PriorityLabel.noise: 4,
            }
            label_priority = label_order.get(score_result.priority_label, 5)

            # Чем выше score, тем важнее (отрицательный для сортировки по убыванию)
            score_key = -score_result.score

            # Чем выше urgency_score, тем важнее
            urgency_key = -score_result.breakdown.urgency_score

            return (label_priority, score_key, urgency_key)

        return sorted(candidates, key=sort_key)


# =============================================================================
# Сервис фильтрации
# =============================================================================

class FilteringService:
    """Сервис фильтрации сигналов (Filtering Engine).

    Отвечает за отбор сигналов, которые действительно несут денежную ценность.

    Не принимает решений о рекомендациях — только фильтрует и приоритизирует.

    Attributes:
        strategy: Стратегия фильтрации (заменяемая).
        min_score: Минимальный score для прохождения.
        min_confidence: Минимальный confidence для прохождения.
        max_signals: Максимальное количество сигналов в выходном списке.
    """

    def __init__(
        self,
        strategy: FilteringStrategy | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_signals: int = DEFAULT_MAX_SIGNALS,
    ) -> None:
        """Инициализирует сервис с заданными параметрами.

        Args:
            strategy: Стратегия фильтрации. По умолчанию — DefaultFilteringStrategy.
            min_score: Минимальный score для прохождения.
            min_confidence: Минимальный confidence для прохождения.
            max_signals: Максимальное количество сигналов.
        """
        self.strategy = strategy or DefaultFilteringStrategy()
        self.min_score = min_score
        self.min_confidence = min_confidence
        self.max_signals = max_signals

    def filter_signals(self, score_results: list[ScoreResult]) -> FilteringResult:
        """Фильтрует список оценённых сигналов.

        Это основной публичный метод сервиса.
        Вся логика фильтрации делегируется strategy.

        Args:
            score_results: Список результатов от Revenue Scoring Engine.
                Должен содержать уже оценённые сигналы.

        Returns:
            Результат фильтрации с прошедшими и отклонёнными сигналами.
            Прошедшие сигналы отсортированы по приоритету.

        Raises:
            ValueError: Если score_results содержит None.
        """
        if score_results is None:
            raise ValueError("score_results не может быть None")

        return self.strategy.filter(
            score_results=score_results,
            min_score=self.min_score,
            min_confidence=self.min_confidence,
            max_signals=self.max_signals,
        )
