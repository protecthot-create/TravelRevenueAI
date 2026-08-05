FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml ./
RUN pip install --upgrade pip

COPY --chown=appuser:appuser . .
RUN pip install .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "travel_revenue_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]