# Развёртывание TravelRevenueAI RC1

## Предварительные требования

- Docker Engine с Docker Compose v2;
- доступный порт `8080` на хосте или заданный `FRONTEND_PORT`;
- заполненный `.env` в корне репозитория.

## Подготовка ENV

```bash
cp .env.example .env
```

Заполните значения без кавычек и не добавляйте `.env` в Git:

- `POSTGRES_PASSWORD` — пароль PostgreSQL;
- `SECRET_ENCRYPTION_KEY` — ключ Fernet;
- `CORS_ORIGINS` — публичный origin frontend, без `*` в production.

Ключ шифрования можно создать командой:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Запуск

Из корня проекта:

```bash
docker compose up --build
```

Compose выполняет миграции отдельным одноразовым сервисом `migrate`. Backend стартует только после успешной миграции и готовности PostgreSQL.

После старта:

- frontend: `http://localhost:8080`;
- backend health: `http://localhost:8000/health`;
- readiness: `http://localhost:8000/health/ready`;
- liveness: `http://localhost:8000/health/live`.

> Порт backend не опубликован наружу в стандартном compose-файле. Для диагностики используйте `docker compose exec backend` или временный override-файл, а внешний доступ идёт через frontend `/api/`.

## Проверка статуса

```bash
docker compose ps
docker compose logs migrate
docker compose logs backend
docker compose logs frontend
```

Ожидается:

- `migrate` — статус `exited (0)`;
- `postgres`, `backend`, `frontend` — `running` и `healthy`.

## Остановка

Остановить сервисы без удаления данных:

```bash
docker compose down
```

Остановить сервисы и удалить production-данные:

```bash
docker compose down -v
```

Вторая команда удаляет `postgres_data` без возможности восстановления без резервной копии.