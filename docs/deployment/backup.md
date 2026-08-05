# Резервное копирование

## Scope

В production резервируется PostgreSQL. SQLite используется только в development и не является production-источником данных.

## Ежедневный backup

Запускать с production-хоста или доверенного backup worker:

```bash
docker compose exec -T postgres pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  -U "$POSTGRES_USER" \
  "$POSTGRES_DB" \
  > "backups/travel-revenue-ai-$(date +%F).dump"
```

Проверить архив:

```bash
pg_restore --list "backups/travel-revenue-ai-YYYY-MM-DD.dump"
```

## Политика хранения

- ежедневные архивы: минимум 14 дней;
- еженедельные: минимум 8 недель;
- ежемесячные: минимум 12 месяцев;
- отдельная зашифрованная копия — вне production-хоста;
- backup должен быть проверен тестовым restore не реже одного раза в месяц.

## Безопасность

- Не хранить пароли БД, дампы и ключи в Git.
- Ограничить доступ к каталогу backup.
- Передавать архивы во внешнее хранилище только по защищённому каналу.
- Фиксировать дату, размер, checksum и результат проверки каждого backup.

## Перед upgrade

Перед применением новой migration создать отдельный backup и не удалять его до успешной smoke-проверки новой версии.