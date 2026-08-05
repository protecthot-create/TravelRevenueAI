# Opportunity Ranking Engine

## Назначение

`RuleBasedOpportunityRanker` — детерминированный компонент Revenue Intelligence Layer для оценки, сортировки и выбора бизнес-возможностей.

Он отвечает на вопрос: **какие уже найденные возможности следует показать первыми**.

Компонент не ищет возможности, не строит рекомендации, не обращается к сети и не выполняет runtime-интеграцию.

## Место в Revenue Intelligence Layer

```text
BusinessOpportunity
+ RevenueImpact
+ Recommendation
↓
RuleBasedOpportunityRanker
↓
OpportunityScore
↓
Stable Sorting and Tie-Break
↓
OpportunityRankingResult
├─ ranked_opportunities
└─ selected_opportunities
```

## Входные данные

Публичный метод:

```python
ranker.rank(
    opportunities,
    revenue_impacts=None,
    recommendations=None,
    context=None,
    limit=5,
)
```

- `opportunities` — последовательность `BusinessOpportunity`;
- `revenue_impacts` — необязательное сопоставление `UUID → RevenueImpact`;
- `recommendations` — необязательное сопоставление `UUID → Sequence[Recommendation]`;
- `context` — зарезервированный контекст Revenue Intelligence;
- `limit` — положительный размер TOP-N. Значение меньше `1` вызывает `ValueError`.

Если для возможности не переданы отдельные `RevenueImpact` или рекомендации, используются её собственные `revenue_impact` и `recommended_actions`.

## Выходной контракт

Метод возвращает `OpportunityRankingResult`:

- `ranked_opportunities` — полный стабильный список успешно оценённых кандидатов;
- `selected_opportunities` — первые `min(limit, число_кандидатов)` элементов;
- `total_candidates` — число входных возможностей, включая изолированно обработанные ошибки;
- `selection_limit` — фактически запрошенный limit;
- `processing_metadata` — техническая информация о стратегии;
- `errors` — безопасные ошибки кандидатов, которые не удалось оценить.

### RankedOpportunity

Каждый результат содержит:

- глубокую копию исходной `BusinessOpportunity`;
- `OpportunityScore`;
- позицию `rank`, начиная с `1`;
- глубокие копии применённых рекомендаций;
- глубокую копию `RevenueImpact`, если он доступен;
- текст `selection_reason`, объясняющий попадание или непопадание в TOP-N.

Входные объекты `BusinessOpportunity`, `RevenueImpact` и `Recommendation` не изменяются.

## Частичные оценки

Все частичные оценки и `final_score` лежат в диапазоне `0..100`.

| Поле | Источник | Правило |
|---|---|---|
| `revenue_score` | `RevenueImpact.amount_max` | 0 при отсутствии суммы; 10/30/50/70/100 по подтверждённому верхнему диапазону |
| `urgency_score` | `UrgencyLevel` | low=10, medium=40, high=70, critical=100 |
| `confidence_score` | `ConfidenceLevel` | low=20, medium=55, high=85 |
| `relevance_score` | тип возможности, evidence, entities | базовая релевантность типа плюс ограниченные бонусы за доказательства и сущности |
| `deadline_score` | ближайший дедлайн рекомендации | 25 без дедлайна; 100 до 24 часов, 75 до 72 часов, 50 до недели, 30 позднее |
| `recommendation_priority_score` | рекомендации | 25 без рекомендаций; максимум приоритета плюс ограниченный бонус за количество |

### Финансовые данные

`RevenueImpact` используется только как подтверждённый входной факт.

- При отсутствии `RevenueImpact` оценка выручки равна `0`.
- При пустом денежном диапазоне (`amount_max=None`) оценка равна `0`.
- Валюта не конвертируется: неизвестная валюта не создаёт выдуманных денежных значений.
- Неполные финансовые данные не должны приводить к исключению.

## Правила final_score

Итоговая оценка рассчитывается детерминированно:

```text
final_score =
    revenue_score × 0.30
  + urgency_score × 0.20
  + confidence_score × 0.15
  + relevance_score × 0.10
  + deadline_score × 0.10
  + recommendation_priority_score × 0.15
```

Результат округляется до двух знаков после запятой.

`explanation` перечисляет все частичные оценки и кратко указывает источник каждого вклада. Это делает ранжирование объяснимым без раскрытия сырых сигналов.

## TOP-N и стабильная сортировка

После оценки кандидаты сортируются по следующим ключам:

1. `final_score` — по убыванию;
2. `urgency_score` — по убыванию;
3. `confidence_score` — по убыванию;
4. ближайший дедлайн — от раннего к позднему;
5. строковое представление UUID — по возрастанию.

Последний ключ делает порядок воспроизводимым, когда все предыдущие параметры совпадают.

`selected_opportunities` — срез первых N элементов полного `ranked_opportunities`. Если limit больше числа оценённых возможностей, выбираются все доступные.

## Дедлайны и отсутствующие данные

- Отсутствие дедлайна допускается и даёт консервативный `deadline_score=25`.
- Просроченный дедлайн предсказуемо трактуется как срочный.
- Naive datetime интерпретируется как UTC.
- Timezone-aware datetime приводится к UTC.
- Это исключает ошибку сравнения naive и aware datetime.

## Обработка ошибок

Ошибка оценки одной возможности не останавливает обработку остальных.

Для такого кандидата добавляется `RevenueIntelligenceError` с:

- компонентом `RuleBasedOpportunityRanker`;
- кодом `COMPONENT_FAILURE`;
- общим безопасным сообщением.

В сообщение ошибки не включаются полный сигнал, `raw_data` или другие потенциально чувствительные данные.

## Границы ответственности

Ranking Engine:

- оценивает уже сформированные возможности;
- выбирает TOP-N;
- формирует объяснимые оценки и безопасные ошибки;
- не меняет входные данные;
- не использует LLM, CRM, БД, сеть и внешние API.

Ranking Engine не:

- обнаруживает новые сигналы;
- вычисляет `RevenueImpact` из первичных данных;
- строит Decision Cards;
- формирует Morning Brief;
- вызывает Pipeline;
- импортирует FastAPI, SQLAlchemy или database layer.

## Текущий статус и ограничения

На текущем этапе Ranking Engine **не подключён** к:

- Pipeline;
- Decision Cards;
- Morning Brief;
- runtime-интеграции.

Это намеренное ограничение RC2.5: компонент проверяется изолированно через публичный контракт.

Оценка является rule-based и не выполняет конвертацию валют, прогнозирование, пользовательскую калибровку весов или хранение обратной связи. Эти возможности относятся к будущим отдельным этапам и не реализуются данным компонентом.