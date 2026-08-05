# Восстановление

## Перед началом

1. Зафиксировать инцидент и остановить запись в приложение:
   ```bash
   docker compose stop backend
   ```
2. Убедиться, что выбран корректный `.dump`.
3. Сохранить текущий аварийный backup перед перезаписью данных.
4. Использовать версию приложения, совместимую с ревизией миграций в архиве.

## Восстановление PostgreSQL

Полностью пересоздать целевую БД допускается только в согласованном maintenance window:

```bash
docker compose exec -T postgres dropdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres pg_restore \
  --no-owner \
  --no-privileges \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  < "backups/travel-revenue-ai-YYYY-MM-DD.dump"
```

## После restore

1. Проверить текущую ревизию:
   ```bash
   docker compose run --rm migrate alembic current
   ```
2. Если выбранный образ требует более новую схему, выполнить только управляемую миграцию:
   ```bash
   docker compose run --rm migrate alembic upgrade head
   ```
3. Запустить приложение:
   ```bash
   docker compose up -d backend frontend
   ```
4. Подтвердить:
   ```bash
   curl -fsS http://localhost:8000/health/ready
   curl -fsS http://localhost:8080/
   ```

## Критерий успешного восстановления

- `alembic current` соответствует ожидаемой ревизии;
- `/health/ready` отвечает `200`;
- frontend доступен;
- ключевой пилотный сценарий прошёл smoke-check;
- результат restore зафиксирован в журнале инцидента.