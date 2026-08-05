# Контракты Revenue Intelligence

## Протокольные интерфейсы

Слой использует `Protocol`-контракты вместо зависимости от конкретных реализаций.

| Интерфейс | Метод | Результат |
|---|---|---|
| `OpportunityDetector` | `detect(input_data)` | `list[BusinessOpportunity]` |
| `RevenueEstimator` | `estimate(opportunity, context)` | `RevenueImpact \| None` |
| `UrgencyEstimator` | `estimate(opportunity, context)` | `UrgencyLevel` |
| `ConfidenceEstimator` | `estimate(opportunity, context)` | `ConfidenceLevel` |
| `RecommendationBuilder` | `build(opportunity, context)` | `list[Recommendation]` |
| `OpportunityGrouper` | `group(opportunities, context)` | `list[OpportunityGroup]` |

## Требования к реализациям

Компонент должен:

- принимать только доменные контракты;
- не менять входной `RevenueIntelligenceInput`, контекст или возможность;
- не обращаться к ORM, БД, HTTP или FastAPI;
- возвращать валидный тип результата;
- не запускать LLM без отдельного будущего адаптера.

## Обработка ошибок

Engine изолирует сбой компонента:

- исключение преобразуется в `RevenueIntelligenceError`;
- код ошибки — `component_failure`;
- имя компонента сохраняется в поле `component`;
- остальные детекторы и этапы продолжают работу.

Ошибка не должна содержать traceback, секреты или исходные данные сигнала.

## Null-компоненты

В RC2 применяются `Null*` реализации. Они нужны для безопасной композиции и контрактных тестов:

- детектор возвращает пустой список;
- оценщик выручки возвращает `None`;
- urgency и confidence возвращают низкий уровень;
- builder и grouper возвращают пустые списки.

Null-компоненты не используют сеть, БД и LLM.