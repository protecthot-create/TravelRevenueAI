"""Проверки security и observability runtime-инфраструктуры."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from travel_revenue_ai.observability.runtime import (
    HttpMetrics,
    JsonFormatter,
    RequestContextMiddleware,
)
from travel_revenue_ai.security.secrets import (
    ENCRYPTED_SECRET_KEY,
    REDACTED_VALUE,
    SecretService,
    generate_secret_encryption_key,
    redact_sensitive_data,
)


def test_secret_service_encrypts_and_decrypts_credentials() -> None:
    """Credentials не остаются в зашифрованном контейнере в открытом виде."""
    service = SecretService(generate_secret_encryption_key(), require_encryption=True)
    credentials = {"username": "agent@example.test", "password": "super-secret"}

    encrypted = service.encrypt(credentials)

    assert set(encrypted) == {ENCRYPTED_SECRET_KEY}
    assert "super-secret" not in encrypted[ENCRYPTED_SECRET_KEY]
    assert service.decrypt(encrypted) == credentials


def test_secret_service_rejects_plaintext_in_production() -> None:
    """Production-режим не принимает уже сохранённые plaintext credentials."""
    service = SecretService(generate_secret_encryption_key(), require_encryption=True)

    with pytest.raises(ValueError, match="незашифрованные"):
        service.decrypt({"password": "plain-text"})


def test_redact_sensitive_data_handles_nested_structures() -> None:
    """Маскировка рекурсивно очищает вложенные секретные поля."""
    result = redact_sensitive_data(
        {
            "api_key": "key-value",
            "nested": [{"password": "secret"}, {"visible": "ok"}],
            "access-token": "token-value",
        }
    )

    assert result == {
        "api_key": REDACTED_VALUE,
        "nested": [{"password": REDACTED_VALUE}, {"visible": "ok"}],
        "access-token": REDACTED_VALUE,
    }


def test_json_formatter_does_not_emit_password() -> None:
    """Структурированный лог не раскрывает пароль из дополнительного контекста."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="travel_revenue_ai",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Техническая проверка",
        args=(),
        exc_info=None,
    )
    record.password = "should-not-appear"

    payload = json.loads(formatter.format(record))

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "password" not in payload
    assert "should-not-appear" not in serialized


def test_http_metrics_render_prometheus_format() -> None:
    """Метрики содержат безопасные labels и накопленные значения."""
    metrics = HttpMetrics()
    metrics.observe(
        method="GET",
        path='/api/"test"',
        status_code=200,
        duration_seconds=0.125,
    )

    rendered = metrics.render_prometheus()

    assert "travel_revenue_http_requests_total" in rendered
    assert 'path="/api/\\"test\\""' in rendered
    assert "status=\"200\"" in rendered
    assert "travel_revenue_http_request_duration_seconds_sum" in rendered


def test_request_middleware_returns_and_preserves_request_id() -> None:
    """Middleware принимает входящий request id и публикует его в ответе."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware, metrics=HttpMetrics())

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/probe", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"