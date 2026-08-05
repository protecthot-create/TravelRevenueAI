# Откат

## Правило

Rollback образа и rollback базы — разные операции. Автоматически откатывать Alembic migration запрещено: migration может быть необратимой или потерять данные.

## Откат приложения

1. Остановить трафик или включить maintenance mode на внешнем proxy.
2. Вернуть предыдущий проверенный tag образа в production-конфигурации.
3. Запустить предыдущие образы:
   ```bash
   docker compose up -d postgres backend frontend
   ```
4. Проверить:
   ```bash
   curl -fsS http://localhost:8000/health/ready
   curl -fsS http://localhost:8080/
   docker compose logs --tail=100 backend
   ```

## Если новая migration несовместима со старым кодом

1. Остановить backend.
2. Восстановить PostgreSQL из backup, созданного перед upgrade, по [restore.md](restore.md).
3. Запустить предыдущую версию приложения.
4. Подтвердить readiness и пилотный сценарий.
5. Зафиксировать причину и revision, на которой произошёл сбой.

## Alembic downgrade

`alembic downgrade` разрешён только после review конкретной migration, проверки её downgrade-пути и наличия backup. По умолчанию предпочтительнее restore проверенного backup.

## Критерий успешного rollback

- восстановлена согласованная пара: версия приложения + ревизия БД;
- `/health/ready` возвращает `200`;
- frontend доступен;
- причиной сбоя и точкой восстановления можно управлять из журналов и тегов образов.