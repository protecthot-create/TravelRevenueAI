"""Runtime-логирование, request correlation и HTTP-метрики."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from threading import Lock
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from travel_revenue_ai.security.secrets import redact_sensitive_data

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("travel_revenue_ai")


class JsonFormatter(logging.Formatter):
    """Сериализует журнал в JSON и исключает случайную утечку секретов."""

    def format(self, record: logging.LogRecord) -> str:
        """Формирует одну безопасную структурированную запись."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }
        for key in ("method", "path", "status_code", "duration_ms", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(redact_sensitive_data(payload), ensure_ascii=False, default=str)


def configure_logging(log_level: str) -> None:
    """Настраивает stdout JSON-логирование один раз для всего приложения."""
    package_logger = logging.getLogger("travel_revenue_ai")
    package_logger.setLevel(log_level.upper())
    package_logger.propagate = False

    if any(getattr(handler, "_travel_revenue_handler", False) for handler in package_logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler._travel_revenue_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    package_logger.addHandler(handler)


class HttpMetrics:
    """Потокобезопасный минимум HTTP-метрик в формате Prometheus exposition."""

    def __init__(self) -> None:
        """Инициализирует накопители запросов и длительностей."""
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)

    def observe(self, *, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        """Запоминает завершённый HTTP-запрос."""
        with self._lock:
            self._requests[(method, path, status_code)] += 1
            self._duration_seconds[(method, path)] += duration_seconds

    def render_prometheus(self) -> str:
        """Возвращает метрики в text exposition format Prometheus."""
        lines = [
            "# HELP travel_revenue_http_requests_total Общее количество HTTP-запросов.",
            "# TYPE travel_revenue_http_requests_total counter",
        ]
        with self._lock:
            for (method, path, status_code), count in sorted(self._requests.items()):
                labels = _labels(method=method, path=path, status=str(status_code))
                lines.append(f"travel_revenue_http_requests_total{labels} {count}")

            lines.extend(
                [
                    "# HELP travel_revenue_http_request_duration_seconds_sum Суммарная длительность HTTP-запросов.",
                    "# TYPE travel_revenue_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, path), duration in sorted(self._duration_seconds.items()):
                labels = _labels(method=method, path=path)
                lines.append(f"travel_revenue_http_request_duration_seconds_sum{labels} {duration:.9f}")

        return "\n".join(lines) + "\n"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Добавляет request id, метрики и одну итоговую structured log запись."""

    def __init__(self, app: FastAPI, metrics: HttpMetrics) -> None:
        """Принимает общий накопитель метрик приложения."""
        super().__init__(app)
        self._metrics = metrics

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Обрабатывает запрос, не записывая тело и заголовки с секретами."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = time.perf_counter() - started_at
            self._record(request, status_code=500, duration_seconds=duration_seconds)
            raise
        else:
            duration_seconds = time.perf_counter() - started_at
            response.headers["X-Request-ID"] = request_id
            self._record(
                request,
                status_code=response.status_code,
                duration_seconds=duration_seconds,
            )
            return response
        finally:
            request_id_context.reset(token)

    def _record(self, request: Request, *, status_code: int, duration_seconds: float) -> None:
        """Сохраняет метрики и итоговую запись без query string."""
        path = request.url.path
        self._metrics.observe(
            method=request.method,
            path=path,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )
        logger.info(
            "HTTP-запрос завершён",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )


def install_observability(app: FastAPI, *, log_level: str) -> HttpMetrics:
    """Подключает единые logging, correlation и metrics к FastAPI-приложению."""
    configure_logging(log_level)
    metrics = HttpMetrics()
    app.add_middleware(RequestContextMiddleware, metrics=metrics)

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """Отдаёт технические метрики для Prometheus scraper."""
        return Response(
            content=metrics.render_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return metrics


def _labels(**values: str) -> str:
    """Экранирует labels согласно Prometheus text exposition format."""
    rendered = ",".join(
        f'{key}="{_escape_label_value(value)}"'
        for key, value in sorted(values.items())
    )
    return "{" + rendered + "}"


def _escape_label_value(value: str) -> str:
    """Экранирует обратный слеш и двойные кавычки в значении label."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
