"""Сервис оценки сигналов (Revenue Scoring Engine).

Рассчитывает числовую оценку (score) для нормализованных сигналов.
Используется для сравнения сигналов между собой и приоритизации.

Spec: docs/revenue_scoring_engine_spec.md, docs/scoring_rules.md, docs/revenue_score.md

Архитектурные решения:
- Сервис не зависит от FastAPI, работает только с доменными моделями.
- ScoreResult — независимая структура данных, не привязана к ORM.
- Интерфейс ScoringStrategy позволяет подменять алгоритм оценки без изменения сервиса.
- Полная реализация: FullScoringStrategy (Sprint 2.7B).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from travel_revenue_ai.models.signal import Signal, SignalTypeEnum


# =============================================================================
# Константы весов и порогов (раздел 9 спецификации)
# =============================================================================

# Веса компонентов Score (раздел 6.1)
WEIGHT_MONEY: float = 0.35
WEIGHT_URGENCY: float = 0.30
WEIGHT_PROBABILITY: float = 0.25
WEIGHT_CONTROLLABILITY: float = 0.10

# Модификаторы (раздел 5)
MODIFIER_RISK: float = 0.10
MODIFIER_REPEATABLE: float = 0.05
MODIFIER_CONTEXT_MATCH: float = 0.10
MODIFIER_SEASON_PEAK: float = 0.05
MODIFIER_SEASON_LOW: float = -0.10

# Пороги денежного эффекта (раздел 4.1)
THRESHOLD_VERY_HIGH: float = 200_000.0
THRESHOLD_HIGH: float = 100_000.0
THRESHOLD_MEDIUM: float = 50_000.0
THRESHOLD_LOW: float = 15_000.0

# Пороги Score для категорий (раздел 7.1)
SCORE_NOISE_MAX: float = 15.0
SCORE_WEAK_MAX: float = 25.0
SCORE_MEDIUM_MAX: float = 35.0
SCORE_STRONG_MAX: float = 45.0
SCORE_CRITICAL_MIN: float = 46.0

# Пороги для размера агентства (раздел 5.5)
AGENCY_SIZE_SMALL_MODIFIER: float = 0.70  # пороги снижены на 30%
AGENCY_SIZE_MEDIUM_MODIFIER: float = 1.00


# =============================================================================
# Типы и перечисления
# =============================================================================

class PriorityLabel(str, Enum):
    """Метка приоритета сигнала согласно спецификации."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    noise = "noise"


class AgencySize(str, Enum):
    """Размер агентства для адаптации порогов."""

    small = "small"  # 1–3 сотрудника
    medium = "medium"  # 4–10 сотрудников


class Season(str, Enum):
    """Сезон для сезонных модификаторов."""

    peak = "peak"  # пиковый сезон
    normal = "normal"  # обычный сезон
    low = "low"  # низкий сезон


# =============================================================================
# Структуры данных результата
# =============================================================================

@dataclass(frozen=True)
class ScoreBreakdown:
    """Разбивка score по компонентам оценки.

    Attributes:
        money_score: Оценка денежного потенциала (0–40).
        urgency_score: Оценка срочности (0–25).
        probability_score: Оценка вероятности (0–25).
        controllability_score: Оценка управляемости (0–10).
        modifiers_applied: Словарь применённых модификаторов и их значений.
    """

    money_score: int = 0
    urgency_score: int = 0
    probability_score: int = 0
    controllability_score: int = 0
    modifiers_applied: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreResult:
    """Результат оценки сигнала Revenue Scoring Engine.

    Структура соответствует разделу 8 спецификации:
    docs/revenue_scoring_engine_spec.md

    Attributes:
        signal_id: Идентификатор оценённого сигнала.
        score: Финальный числовой score (0–55+).
        priority_label: Метка приоритета для фильтрации и отображения.
        confidence: Уверенность в оценке (0.0 – 1.0).
        reason: Краткое объяснение расчёта.
        breakdown: Разбивка по компонентам оценки.
        signals_passed: Флаг — прошёл ли сигнал порог для передачи в Filtering Engine.
    """

    signal_id: uuid.UUID
    score: float = 0.0
    priority_label: PriorityLabel = PriorityLabel.noise
    confidence: float = 0.0
    reason: str = ""
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    signals_passed: bool = False


class ScoringStrategy(Protocol):
    """Протокол для стратегий оценки сигналов.

    Позволяет подменять алгоритм scoring без изменения RevenueScoringService.
    Реализации: StubScoringStrategy (тестовая), FullScoringStrategy (рабочая).
    """

    def calculate(self, signal: Signal) -> ScoreResult:
        """Оценивает сигнал и возвращает ScoreResult.

        Args:
            signal: Нормализованный сигнал для оценки.

        Returns:
            Результат оценки с заполненными полями.
        """
        ...


# =============================================================================
# Полноценная стратегия оценки (Sprint 2.7B)
# =============================================================================

class FullScoringStrategy:
    """Полноценная стратегия оценки сигналов по спецификации.

    Реализует все компоненты Revenue Scoring Engine:
    - Money Score (раздел 4.1)
    - Urgency Score (раздел 4.2)
    - Probability Score (раздел 4.3)
    - Controllability Score (раздел 4.4)
    - Модификаторы (раздел 5)
    - Финальный Score (раздел 6)
    - Priority Label (раздел 7)
    - Confidence (раздел 8)
    - signals_passed (раздел 8)

    Spec: docs/revenue_scoring_engine_spec.md
    """

    # -------------------------------------------------------------------------
    # Вспомогательные методы: извлечение данных из raw_data
    # -------------------------------------------------------------------------

    def _get_money_effect(self, signal: Signal) -> float:
        """Извлекает денежный эффект из raw_data.

        Для рисков берём модуль (отрицательное значение обрабатывается отдельно).
        """
        raw = signal.raw_data
        value = raw.get("money_effect", 0.0)
        return float(value) if value is not None else 0.0

    def _get_urgency_hours(self, signal: Signal) -> float | None:
        """Извлекает срочность в часах из raw_data.

        Returns:
            Количество часов до дедлайна или None если не задано.
        """
        raw = signal.raw_data
        urgency = raw.get("urgency")
        if urgency is not None:
            return float(urgency)

        # Вычисляем из deadline если есть
        deadline = raw.get("deadline")
        if deadline:
            if isinstance(deadline, str):
                try:
                    dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                except ValueError:
                    return None
            elif isinstance(deadline, datetime):
                dt = deadline
            else:
                return None

            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = dt - now
            hours = delta.total_seconds() / 3600.0
            return max(0.0, hours)

        return None

    def _get_probability(self, signal: Signal) -> float:
        """Извлекает вероятность реализации из raw_data (0.0–1.0)."""
        raw = signal.raw_data
        value = raw.get("probability", 0.5)
        return float(value) if value is not None else 0.5

    def _get_controllability(self, signal: Signal) -> float:
        """Извлекает управляемость из raw_data (0.0–1.0)."""
        raw = signal.raw_data
        value = raw.get("controllability", 0.5)
        return float(value) if value is not None else 0.5

    def _calculate_confidence(self, signal: Signal) -> float:
        """Рассчитывает confidence на основе входных данных.

        Использует:
        - confidence из нормализованных данных;
        - полноту ключевых полей.
        """
        raw = signal.raw_data
        base_confidence = raw.get("confidence", 0.5)
        try:
            base_confidence = float(base_confidence) if base_confidence is not None else 0.5
        except (TypeError, ValueError):
            base_confidence = 0.5

        required_fields = ("money_effect", "probability", "controllability")
        present_fields = sum(1 for field_name in required_fields if raw.get(field_name) is not None)

        if raw.get("urgency") is not None or raw.get("deadline") is not None:
            present_fields += 1

        completeness = present_fields / 4.0
        return max(0.0, min(1.0, (base_confidence + completeness) / 2.0))

    def _get_agency_size(self, signal: Signal) -> AgencySize:
        """Извлекает размер агентства из raw_data."""
        raw = signal.raw_data
        size = raw.get("agency_size", "medium")
        try:
            return AgencySize(size)
        except ValueError:
            return AgencySize.medium

    def _get_season(self, signal: Signal) -> Season:
        """Извлекает текущий сезон из raw_data."""
        raw = signal.raw_data
        season = raw.get("season", "normal")
        try:
            return Season(season)
        except ValueError:
            return Season.normal

    def _is_repeatable(self, signal: Signal) -> bool:
        """Проверяет, является ли действие повторяемым."""
        raw = signal.raw_data
        return bool(raw.get("repeatable", False))

    def _is_context_match(self, signal: Signal) -> bool:
        """Проверяет соответствие сигнала специализации агентства."""
        raw = signal.raw_data
        specialization = raw.get("specialization", "")
        signal_specialization = raw.get("signal_specialization", "")
        if specialization and signal_specialization:
            return specialization.lower() == signal_specialization.lower()
        return False

    # -------------------------------------------------------------------------
    # Расчёт базовых score
    # -------------------------------------------------------------------------

    def _calculate_money_score(self, money_effect: float, is_risk: bool, agency_size: AgencySize) -> int:
        """Рассчитывает оценку денежного потенциала (0–40).

        Args:
            money_effect: Денежный эффект в рублях.
            is_risk: True если сигнал — риск.
            agency_size: Размер агентства для адаптации порогов.
        """
        # Адаптируем пороги под размер агентства
        modifier = AGENCY_SIZE_SMALL_MODIFIER if agency_size == AgencySize.small else AGENCY_SIZE_MEDIUM_MODIFIER

        thresholds = {
            "very_high": THRESHOLD_VERY_HIGH * modifier,
            "high": THRESHOLD_HIGH * modifier,
            "medium": THRESHOLD_MEDIUM * modifier,
            "low": THRESHOLD_LOW * modifier,
        }

        abs_effect = abs(money_effect)

        if abs_effect > thresholds["very_high"]:
            base = 40
        elif abs_effect >= thresholds["high"]:
            base = 30
        elif abs_effect >= thresholds["medium"]:
            base = 20
        elif abs_effect >= thresholds["low"]:
            base = 10
        else:
            base = 5

        # Риски получают повышенную оценку (раздел 4.1 спецификации)
        if is_risk and base < 40:
            # Повышаем на один уровень, но не выше 40
            if base == 5:
                return 10
            elif base == 10:
                return 20
            elif base == 20:
                return 30
            elif base == 30:
                return 40

        return base

    def _calculate_urgency_score(self, urgency_hours: float | None) -> int:
        """Рассчитывает оценку срочности (0–25).

        Args:
            urgency_hours: Часы до дедлайна или None.
        """
        if urgency_hours is None:
            return 5  # Низкая срочность по умолчанию

        if urgency_hours < 24:
            return 25
        elif urgency_hours <= 48:
            return 20
        elif urgency_hours <= 168:  # 7 дней
            return 15
        elif urgency_hours <= 336:  # 14 дней (1–2 недели)
            return 10
        else:
            return 5

    def _calculate_probability_score(self, probability: float) -> int:
        """Рассчитывает оценку вероятности (0–25).

        Args:
            probability: Вероятность реализации (0.0–1.0).
        """
        if probability > 0.90:
            return 25
        elif probability >= 0.70:
            return 20
        elif probability >= 0.50:
            return 15
        elif probability >= 0.30:
            return 10
        else:
            return 5

    def _calculate_controllability_score(self, controllability: float) -> int:
        """Рассчитывает оценку управляемости (0–10).

        Args:
            controllability: Управляемость (0.0–1.0).
        """
        if controllability >= 0.90:
            return 10
        elif controllability >= 0.60:
            return 7
        elif controllability >= 0.30:
            return 4
        else:
            return 1

    # -------------------------------------------------------------------------
    # Расчёт финального score
    # -------------------------------------------------------------------------

    def _calculate_base_score(
        self,
        money_score: int,
        urgency_score: int,
        probability_score: int,
        controllability_score: int,
    ) -> float:
        """Рассчитывает базовый score по формуле из раздела 6.1.

        Base Score = (Money × 0.35) + (Urgency × 0.30) + (Probability × 0.25) + (Controllability × 0.10)
        """
        return (
            money_score * WEIGHT_MONEY
            + urgency_score * WEIGHT_URGENCY
            + probability_score * WEIGHT_PROBABILITY
            + controllability_score * WEIGHT_CONTROLLABILITY
        )

    def _apply_modifiers(
        self,
        base_score: float,
        signal_type: SignalTypeEnum,
        is_repeatable: bool,
        is_context_match: bool,
        season: Season,
    ) -> tuple[float, dict[str, float]]:
        """Применяет модификаторы к базовому score.

        Returns:
            Кортеж (финальный_score, словарь_модификаторов).
        """
        modifiers: dict[str, float] = {}

        # Модификатор риска: +10%
        if signal_type == SignalTypeEnum.risk:
            modifiers["risk"] = MODIFIER_RISK

        # Модификатор повторяемости: +5%
        if is_repeatable:
            modifiers["repeatable"] = MODIFIER_REPEATABLE

        # Модификатор контекста: +10%
        if is_context_match:
            modifiers["context_match"] = MODIFIER_CONTEXT_MATCH

        # Модификатор сезона
        if season == Season.peak:
            modifiers["season_peak"] = MODIFIER_SEASON_PEAK
        elif season == Season.low:
            modifiers["season_low"] = MODIFIER_SEASON_LOW

        # Суммируем модификаторы и применяем как мультипликативный фактор
        total_modifier = sum(modifiers.values())
        final_score = base_score * (1 + total_modifier)

        return final_score, modifiers

    def _determine_priority_label(self, score: float) -> PriorityLabel:
        """Определяет метку приоритета на основе финального score (раздел 7.1)."""
        if score >= SCORE_CRITICAL_MIN:
            return PriorityLabel.critical
        if score > SCORE_STRONG_MAX:
            return PriorityLabel.high
        if score > SCORE_MEDIUM_MAX:
            return PriorityLabel.medium
        if score > SCORE_NOISE_MAX:
            return PriorityLabel.low
        return PriorityLabel.noise

    def _build_reason(
        self,
        money_score: int,
        urgency_score: int,
        probability_score: int,
        controllability_score: int,
        base_score: float,
        final_score: float,
        modifiers: dict[str, float],
        signal_type: SignalTypeEnum,
    ) -> str:
        """Формирует краткое объяснение расчёта."""
        type_name = "риск" if signal_type == SignalTypeEnum.risk else "возможность"
        if signal_type == SignalTypeEnum.market:
            type_name = "рыночный сигнал"
        elif signal_type == SignalTypeEnum.operational:
            type_name = "операционное улучшение"

        modifier_parts = []
        if "risk" in modifiers:
            modifier_parts.append("бонус риска +10%")
        if "repeatable" in modifiers:
            modifier_parts.append("повторяемость +5%")
        if "context_match" in modifiers:
            modifier_parts.append("соответствие специализации +10%")
        if "season_peak" in modifiers:
            modifier_parts.append("пиковый сезон +5%")
        if "season_low" in modifiers:
            modifier_parts.append("низкий сезон -10%")

        modifier_str = f" | Модификаторы: {', '.join(modifier_parts)}" if modifier_parts else ""

        return (
            f"Базовый score: {base_score:.1f} → Финальный: {final_score:.1f}. "
            f"Компоненты: деньги={money_score}, срочность={urgency_score}, "
            f"вероятность={probability_score}, управляемость={controllability_score}."
            f"{modifier_str}"
        )

    # -------------------------------------------------------------------------
    # Публичный метод оценки
    # -------------------------------------------------------------------------

    def calculate(self, signal: Signal) -> ScoreResult:
        """Оценивает сигнал и возвращает полный ScoreResult.

        Это единственный публичный метод стратегии.
        """
        # Извлекаем данные
        money_effect = self._get_money_effect(signal)
        urgency_hours = self._get_urgency_hours(signal)
        probability = self._get_probability(signal)
        controllability = self._get_controllability(signal)
        confidence = self._calculate_confidence(signal)
        agency_size = self._get_agency_size(signal)
        season = self._get_season(signal)
        is_repeatable_flag = self._is_repeatable(signal)
        is_context_match_flag = self._is_context_match(signal)

        # Рассчитываем базовые score
        is_risk = signal.signal_type == SignalTypeEnum.risk
        money_score = self._calculate_money_score(money_effect, is_risk, agency_size)
        urgency_score = self._calculate_urgency_score(urgency_hours)
        probability_score = self._calculate_probability_score(probability)
        controllability_score = self._calculate_controllability_score(controllability)

        # Базовый и финальный score
        base_score = self._calculate_base_score(
            money_score, urgency_score, probability_score, controllability_score
        )
        final_score, modifiers = self._apply_modifiers(
            base_score,
            signal.signal_type,
            is_repeatable_flag,
            is_context_match_flag,
            season,
        )

        # Priority label и signals_passed
        priority_label = self._determine_priority_label(final_score)
        signals_passed = final_score > SCORE_NOISE_MAX

        # Формируем reason
        reason = self._build_reason(
            money_score,
            urgency_score,
            probability_score,
            controllability_score,
            base_score,
            final_score,
            modifiers,
            signal.signal_type,
        )

        return ScoreResult(
            signal_id=signal.signal_id,
            score=round(final_score, 2),
            priority_label=priority_label,
            confidence=round(confidence, 2),
            reason=reason,
            breakdown=ScoreBreakdown(
                money_score=money_score,
                urgency_score=urgency_score,
                probability_score=probability_score,
                controllability_score=controllability_score,
                modifiers_applied=modifiers,
            ),
            signals_passed=signals_passed,
        )


class RevenueScoringService:
    """Сервис оценки сигналов (Revenue Scoring Engine).

    Отвечает на вопрос: «Насколько важен этот сигнал для денег агентства?»

    Не принимает решений о фильтрации — только оценивает.
    Решение о показе принимает Filtering Engine.

    Attributes:
        strategy: Стратегия расчёта score (заменяемая).
    """

    def __init__(self, strategy: ScoringStrategy | None = None) -> None:
        """Инициализирует сервис с заданной стратегией оценки.

        Args:
            strategy: Стратегия расчёта score. По умолчанию — FullScoringStrategy.
        """
        self.strategy = strategy or FullScoringStrategy()

    def score_signal(self, signal: Signal) -> ScoreResult:
        """Оценивает один сигнал и возвращает ScoreResult.

        Это единственный публичный метод сервиса.
        Вся логика оценки делегируется strategy.

        Args:
            signal: Нормализованный сигнал для оценки.
                Должен иметь status == normalized (проверяется вызывающим кодом).

        Returns:
            Результат оценки с заполненными полями score, priority_label, breakdown.

        Raises:
            ValueError: Если signal не содержит обязательных полей.
        """
        if signal is None:
            raise ValueError("signal не может быть None")

        # Делегируем расчёт стратегии
        result = self.strategy.calculate(signal)

        return result

    def score_signals(self, signals: list[Signal]) -> list[ScoreResult]:
        """Оценивает пакет сигналов.

        Args:
            signals: Список нормализованных сигналов.

        Returns:
            Список результатов оценки в том же порядке.
        """
        return [self.score_signal(signal) for signal in signals]