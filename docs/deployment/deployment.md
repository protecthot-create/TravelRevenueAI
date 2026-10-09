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
- `VITE_CLERK_PUBLISHABLE_KEY` — publishable key для Clerk UI;
- `CLERK_ISSUER` и один из `CLERK_JWT_KEY` / `CLERK_SECRET_KEY` — проверка
  Clerk session token в backend.

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
- SPA sign-in route: `http://localhost:8080/sign-in`;
- внешний API за nginx: `http://localhost:8080/api/v1`.

> Порт backend не опубликован наружу в стандартном compose-файле. Для диагностики используйте `docker compose exec backend` или временный override-файл, а внешний доступ идёт через frontend `/api/`.

## Проверка статуса

```bash
docker compose ps
docker compose logs migrate
docker compose logs backend
docker compose logs frontend
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
```

Ожидается:

- `migrate` — статус `exited (0)`;
- `postgres`, `backend`, `frontend` — `running` и `healthy`.
- Alembic `current` совпадает с `heads`;
- `/` и `/sign-in` на frontend возвращают `200`;
- защищённый `/api/v1` endpoint без Bearer token возвращает `401`,
  `authentication_required` и `WWW-Authenticate: Bearer`.

Эти автоматические smoke-проверки подтверждают PostgreSQL, миграции, backend,
scheduler, nginx proxy и auth boundary, но не заменяют пользовательский Clerk
E2E. Sign-in, onboarding, tenant, persisted Morning Brief, feedback и сохранение
состояния после reload проверяются вручную в браузере с локально заданными Clerk
ключами и реальными входными signals. Секреты и session token в отчёт не копируются.

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
