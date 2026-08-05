# Интеграция Revenue Intelligence с Pipeline

## Назначение

Revenue Intelligence подключён к существующему Pipeline как изолированное необязательное расширение.

Цель интеграции — выполнять дополнительный анализ сигналов без изменения действующего процесса формирования Decision Cards и Morning Brief. Новая ветка не заменяет существующие сервисы и не влияет на их входные или выходные контракты.

## Архитектура

Базовый Pipeline сохраняет прежнюю последовательность:

```text
Signal
  → SignalEnrichmentService
  → RevenueScoringService
  → FilteringService
  → DecisionCardService
  → MorningBriefService
```

При включённом Revenue Intelligence параллельно после enrichment запускается дополнительная ветка:

```text
Signal
  → SignalEnrichmentService
  ├→ RevenueIntelligenceEngine (необязательная изолированная ветка)
  └→ RevenueScoringService
      → FilteringService
      → DecisionCardService
      → MorningBriefService
```

`RevenueIntelligenceEngine` возвращает список `RevenueIntelligenceResult` через
`PipelineResult.revenue_intelligence_results`. Эти результаты не используются для
построения Decision Cards и не передаются в `MorningBriefService`.

### Границы компонентов

- `PipelineService` зависит только от необязательного `RevenueIntelligenceEngine`.
- `PipelineService` не импортирует и не создаёт `RuleBasedOpportunityDetector`,
  `RuleBasedRevenueEstimator`, `RuleBasedRecommendationBuilder` или
  `RuleBasedOpportunityRanker`.
- Создание конкретных RuleBased-компонентов находится в composition root:
  `travel_revenue_ai.composition`.
- Существующий публичный метод
  `PipelineService.generate_morning_brief(signals)` по-прежнему возвращает
  `MorningBriefResult`.

## Feature flag

Revenue Intelligence управляется настройкой:

```env
REVENUE_INTELLIGENCE_ENABLED=false
```

Поле `Settings.revenue_intelligence_enabled` имеет значение `False` по умолчанию.
Флаг считывается при создании `Settings` и передаётся в composition root.

| Значение | Поведение |
|---|---|
| `false` | Engine не создаётся и не передаётся в Pipeline. Дополнительная ветка не выполняется. |
| `true` | Composition root создаёт `RevenueIntelligenceEngine` с RuleBased-реализациями и внедряет его в Pipeline. |

Для изменения режима в запущенном процессе требуется применить новое значение
конфигурации и пересоздать приложение (обычно — выполнить штатный restart
процесса).

## Dependency Injection

Сборка зависимостей выполняется только в `travel_revenue_ai.composition`:

```text
Settings
  → build_revenue_intelligence_engine()
  → build_pipeline_service()
  → PipelineService(revenue_intelligence_engine=...)
```

`build_revenue_intelligence_engine()` возвращает:

- `None`, если `revenue_intelligence_enabled=false`;
- `RevenueIntelligenceEngine` с RuleBased-компонентами, если
  `revenue_intelligence_enabled=true`.

Для тестов или альтернативной реализации Engine можно передать напрямую в
конструктор `PipelineService`. Это позволяет проверить дополнительную ветку без
связывания Pipeline с конкретной реализацией.

## Flow при `flag=false`

1. Composition root читает `Settings.revenue_intelligence_enabled`.
2. `build_revenue_intelligence_engine()` возвращает `None`.
3. `PipelineService` получает `revenue_intelligence_engine=None`.
4. `PipelineService.run()` выполняет enrichment и прежний основной Pipeline.
5. `_run_revenue_intelligence()` сразу возвращает `None`.
6. Scoring, filtering, Decision Cards и Morning Brief выполняются по старому пути.
7. `PipelineResult.revenue_intelligence_results` имеет значение `None`.

Следствие: RuleBased-компоненты Revenue Intelligence не создаются, а существующее
поведение Pipeline сохраняется.

## Flow при `flag=true`

1. Composition root создаёт `RevenueIntelligenceEngine`.
2. В Engine внедряются RuleBased detector, estimator, recommendation builder и
   ranker.
3. `PipelineService.run()` выполняет enrichment сигналов.
4. Для каждого сигнала формируется `RevenueIntelligenceInput`.
5. Engine обрабатывает вход и добавляет результат в
   `PipelineResult.revenue_intelligence_results`.
6. Основная цепочка scoring → filtering → Decision Cards → Morning Brief
   выполняется независимо и без использования результатов Engine.
7. Метод `generate_morning_brief()` возвращает только прежний
   `MorningBriefResult`.

## Обработка ошибок

Revenue Intelligence — best-effort расширение.

- Ошибка обработки одного сигнала внутри `RevenueIntelligenceEngine` перехватывается
  в `_run_revenue_intelligence()`.
- Ошибка записывается в лог с `signal_id`.
- Обработка следующих сигналов продолжается.
- Сбой дополнительной ветки не прерывает scoring, filtering, создание Decision
  Cards или Morning Brief.
- При сбое всех обработок список
  `PipelineResult.revenue_intelligence_results` будет пустым (`[]`), а
  `morning_brief` останется доступен.
- Ошибки основного Pipeline не подавляются этой интеграцией и обрабатываются по
  прежним правилам.

## Обратная совместимость

Интеграция сохраняет следующие инварианты:

1. При `flag=false` Pipeline не получает Engine и исполняет прежний путь.
2. `generate_morning_brief()` не меняет возвращаемый тип:
   `MorningBriefResult`.
3. Decision Cards строятся только из результатов существующих scoring и filtering
   сервисов.
4. `MorningBriefService` получает прежний набор Decision Cards.
5. Результаты Revenue Intelligence доступны только через новый метод
   `PipelineService.run()` и поле
   `PipelineResult.revenue_intelligence_results`.
6. Существующие вызывающие стороны, использующие
   `generate_morning_brief()`, не обязаны менять код.

## Ограничения текущей интеграции

- Revenue Intelligence не меняет score, фильтрацию, Decision Cards и Morning Brief.
- Результаты Engine пока не сохраняются в БД и не публикуются отдельным API.
- Нет runtime-переключения флага без применения обновлённой конфигурации и
  перезапуска приложения.
- Ошибка Engine логируется, но не создаёт отдельный доменный статус или метрику
  ошибки Revenue Intelligence.
- Дополнительная обработка выполняется синхронно для каждого сигнала; при большом
  объёме сигналов это увеличивает длительность Pipeline.
- RuleBased-реализации создаются только для включённого флага. Внешние или
  асинхронные реализации Engine должны соблюдать контракт
  `RevenueIntelligenceEngine`.

## Rollback

Rollback выполняется без изменения схемы данных и без удаления кода:

1. Установить `REVENUE_INTELLIGENCE_ENABLED=false`.
2. Применить конфигурацию и штатно перезапустить приложение.
3. Убедиться, что composition root передаёт в `PipelineService`
   `revenue_intelligence_engine=None`.
4. Pipeline продолжит выполнять только прежний поток и возвращать обычный
   `MorningBriefResult`.

Это отключает дополнительную ветку и возвращает поведение к legacy-режиму.