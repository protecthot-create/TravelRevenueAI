# База данных и миграции

## Режимы БД

| Режим | СУБД | Назначение |
|---|---|---|
| Development | SQLite | Локальная разработка |
| Test | SQLite | Изолированные автоматические проверки |
| Production | PostgreSQL 16 | Pilot и production-контур |

Поддержка SQLite сохранена. При `ENVIRONMENT=production` приложение отклоняет SQLite до старта.

## Alembic

Alembic расположен в `backend/alembic/`.

```text
backend/
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 20260718_0001_initial_schema.py
```

Первая миграция создаёт текущую ORM-схему. Изменения схемы БД в production выполняются только через migration-файлы.

## Основные команды

Из директории `backend`:

```bash
alembic current
alembic upgrade head
alembic downgrade -1
alembic history
```

Для создания следующей миграции:

```bash
alembic revision --autogenerate -m "краткое_описание_изменения"
```

Перед применением нужно проверить сгенерированный migration-файл и выполнить тесты.

## Production-порядок

1. Сделать резервную копию PostgreSQL.
2. Развернуть новую версию контейнеров.
3. Выполнить `alembic upgrade head` через сервис `migrate`.
4. Убедиться в `docker compose logs migrate`, что задача завершилась с кодом `0`.
5. Проверить `/health/ready`.

В `docker compose up` шаг 3 выполняется автоматически. Не запускайте SQL вручную в контейнере или в production БД.