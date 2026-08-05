"""Smoke-проверка Docker deployment foundation TravelRevenueAI.

Запуск из корня репозитория:
    python scripts/smoke_deployment.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence


def run(command: Sequence[str]) -> None:
    """Выполняет команду и останавливает smoke-проверку при ошибке."""
    print(f"$ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Команда завершилась с кодом {completed.returncode}: {' '.join(command)}"
        )


def run_backend_health(endpoint: str) -> None:
    """Проверяет endpoint из контейнера backend, не публикуя его наружу."""
    script = (
        "import sys, urllib.request; "
        f"response = urllib.request.urlopen('http://localhost:8000{endpoint}', timeout=10); "
        "print(response.status); "
        "sys.exit(0 if response.status == 200 else 1)"
    )
    run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            script,
        ]
    )


def run_frontend_health(frontend_port: str) -> None:
    """Проверяет, что frontend доступен с хоста."""
    script = (
        "import sys, urllib.request; "
        f"response = urllib.request.urlopen('http://localhost:{frontend_port}/', timeout=10); "
        "print(response.status); "
        "sys.exit(0 if response.status == 200 else 1)"
    )
    run([sys.executable, "-c", script])


def main() -> int:
    """Запускает минимальный production smoke-сценарий."""
    frontend_port = os.environ.get("FRONTEND_PORT", "8080")

    try:
        run(["docker", "compose", "build"])
        run(["docker", "compose", "up", "-d", "postgres"])
        run(["docker", "compose", "run", "--rm", "migrate", "alembic", "upgrade", "head"])
        run(["docker", "compose", "up", "-d", "backend", "frontend"])
        run(["docker", "compose", "ps"])
        run(["docker", "compose", "exec", "-T", "postgres", "pg_isready", "-U", os.environ.get("POSTGRES_USER", "travel_revenue"), "-d", os.environ.get("POSTGRES_DB", "travel_revenue_ai")])
        run(["docker", "compose", "run", "--rm", "migrate", "alembic", "current"])
        run_backend_health("/health/live")
        run_backend_health("/health/ready")
        run_frontend_health(frontend_port)
    except (OSError, RuntimeError) as error:
        print(f"Smoke-проверка не пройдена: {error}", file=sys.stderr)
        return 1

    print("Smoke-проверка deployment foundation пройдена.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())