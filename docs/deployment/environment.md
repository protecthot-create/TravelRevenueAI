# Переменные окружения

Корневой `.env.example` содержит безопасный шаблон. Настоящий `.env` — локальный или инфраструктурный секрет и не должен попадать в Git.

## Общие переменные

| Переменная | Обязательна | Назначение |
|---|---:|---|
| `ENVIRONMENT` | да | `development`, `test` или `production` |
| `DATABASE_URL` | да для production | URL SQLAlchemy |
| `SECRET_ENCRYPTION_KEY` | да для production | Ключ Fernet для credentials источников |
| `CORS_ORIGINS` | да для production | JSON-массив разрешённых origin |
| `LOG_LEVEL` | нет | Уровень логирования, по умолчанию `INFO` |
| `MORNING_BRIEF_RUN_TIME` | нет | Время `HH:MM`, по умолчанию `08:00` |
| `MORNING_BRIEF_TIMEZONE` | нет | Часовой пояс, по умолчанию `Europe/Moscow` |
| `FRONTEND_PORT` | нет | Внешний порт frontend, по умолчанию `8080` |

## Development

Development использует SQLite без Docker PostgreSQL:

```env
ENVIRONMENT=development
DATABASE_URL=sqlite:///./travel_revenue_ai.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]
```

`SECRET_ENCRYPTION_KEY` рекомендуется задавать и в development, если тестируются зашифрованные credentials.

## Test

Тесты должны использовать изолированную SQLite БД:

```env
ENVIRONMENT=test
DATABASE_URL=sqlite:///./test_travel_revenue_ai.db
DEBUG=false
CORS_ORIGINS=["http://testserver"]
```

Не направляйте `DATABASE_URL` test-профиля на production PostgreSQL.

## Production

Production использует PostgreSQL и включает строгую проверку конфигурации:

```env
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://travel_revenue:<password>@postgres:5432/travel_revenue_ai
SECRET_ENCRYPTION_KEY=<fernet-key>
CORS_ORIGINS=["https://travel.example.com"]
DEBUG=false
```

В production запрещены:

- SQLite;
- пустой `SECRET_ENCRYPTION_KEY`;
- wildcard `*` в `CORS_ORIGINS`;
- пароли, ключи и токены внутри исходного кода или Dockerfile.

## Переменные Docker PostgreSQL

| Переменная | Назначение |
|---|---|
| `POSTGRES_DB` | Имя базы, по умолчанию `travel_revenue_ai` |
| `POSTGRES_USER` | Пользователь БД, по умолчанию `travel_revenue` |
| `POSTGRES_PASSWORD` | Обязательный пароль PostgreSQL |

Compose строит `DATABASE_URL` из этих значений внутри Docker-сети.