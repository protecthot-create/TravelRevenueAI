# Архитектура развёртывания TravelRevenueAI RC1

## Состав сервисов

```text
Пользователь
    │
    ├── :80 ──► frontend (Nginx, статические файлы React)
    │                 │ /api/*
    │                 ▼
    └────────────► backend (FastAPI/Uvicorn, :8000)
                       │
                       │ SQLAlchemy + Alembic
                       ▼
                  postgres (PostgreSQL 16)
                       │
                  volume: postgres_data
```

## Docker-сеть

Все контейнеры находятся в изолированной bridge-сети `travel_revenue_ai_network`.

| Сервис | Доступ извне | Назначение |
|---|---:|---|
| `frontend` | `80` | Публикация интерфейса и reverse proxy `/api/` к backend |
| `backend` | `8000` | API, startup validation, health endpoints |
| `postgres` | нет по умолчанию | Production БД, хранение данных в volume |

PostgreSQL не публикует порт на хост. Доступ к нему имеет только backend внутри Docker-сети.

## Жизненный цикл backend

1. Контейнер ждёт успешный healthcheck PostgreSQL.
2. Выполняется `alembic upgrade head`.
3. Uvicorn запускает FastAPI.
4. Lifespan FastAPI выполняет startup validation: БД, SourceManager, scheduler, feature flags и metrics.
5. Docker healthcheck запрашивает `GET /health/ready`.

При неуспехе миграции или startup validation backend не считается готовым и перезапускается в соответствии с restart policy.

## Хранение

- `postgres_data` — именованный Docker volume PostgreSQL.
- `backend_data` — том для SQLite-development режима и локальных runtime-файлов backend.
- Исходный код и секреты не хранятся в контейнерных volume.

## Границы RC1

Инфраструктура не меняет бизнес-правила, scoring, filtering, decision cards, morning brief, intelligence layer, knowledge base, pipeline, feature flags, observability, dashboard UI и реализации источников/провайдеров. Она добавляет только способы запуска, миграции, конфигурацию и проверки готовности.