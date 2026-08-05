# Архитектура Revenue Intelligence

## Назначение

`revenue_intelligence` — изолированный доменный слой для будущего поиска возможностей, рисков и рекомендаций. В RC2 он не подключён к runtime-потоку приложения и не изменяет существующий Pipeline.

## Состав

- `models.py` — Pydantic-модели домена;
- `contracts.py` — независимые входной и выходной контракты;
- `interfaces.py` — Protocol-интерфейсы расширения;
- `engine.py` — оркестратор компонентов через dependency injection;
- `*_estimator.py`, `opportunity_detector.py`, `recommendation_builder.py`, `opportunity_grouping.py` — null-реализации.

## Границы

Слой не зависит от:

- FastAPI и HTTP;
- SQLAlchemy, БД и миграций;
- `Pipeline`;
- планировщика;
- LLM, сети и внешних API.

`RevenueIntelligenceInput.from_signal()` создаёт snapshot входного сигнала через глубокое копирование `raw_data`. Engine получает уже изолированный контракт и не пишет в ORM-сущность Signal.

## Оркестрация

`RevenueIntelligenceEngine` принимает реализации компонентов в конструкторе:

1. detectors создают `BusinessOpportunity`;
2. estimators обогащают каждую возможность;
3. builder создаёт рекомендации;
4. grouper объединяет возможности.

Компонент может завершиться с исключением: Engine добавит структурированную запись в `RevenueIntelligenceResult.errors` и продолжит обработку остальных компонентов.

## Текущее состояние RC2

В пакете присутствует только архитектурный каркас. Null-компоненты не применяют бизнес-правила и возвращают нейтральные результаты.