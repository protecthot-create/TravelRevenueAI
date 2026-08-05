# Обновление

## Принцип

Обновление выполняется как контролируемая последовательность: backup → image build → Alembic migration → запуск → smoke checks. Нельзя применять изменения схемы вручную через SQL.

## Порядок

1. Изучить release notes и список Alembic revisions.
2. Создать проверенный backup по [backup.md](backup.md).
3. Подтянуть версию кода или immutable image tag.
4. Проверить конфигурацию:
   ```bash
   docker compose --env-file .env config
   ```
5. Собрать образы:
   ```bash
   docker compose build
   ```
6. Применить миграции отдельным сервисом:
   ```bash
   docker compose run --rm migrate alembic upgrade head
   ```
7. Запустить новую версию:
   ```bash
   docker compose up -d postgres backend frontend
   ```
8. Выполнить smoke checks:
   ```bash
   curl -fsS http://localhost:8000/health/live
   curl -fsS http://localhost:8000/health/ready
   curl -fsS http://localhost:8080/
   docker compose ps
   ```
9. Просмотреть логи:
   ```bash
   docker compose logs --tail=100 backend frontend
   ```

## Критерий готовности

- backend и frontend имеют статус `healthy` / `running`;
- `/health/ready` возвращает `200`;
- Alembic revision совпадает с `head`;
- smoke checks прошли;
- нет необработанных ошибок в логах.

Если любой критерий не выполнен, не продолжать rollout и перейти к [rollback.md](rollback.md).