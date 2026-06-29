FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY src ./src

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health').read()"

CMD [".venv/bin/python", "-m", "uvicorn", "src.api.rest.app:app", "--host", "0.0.0.0", "--port", "8001"]
