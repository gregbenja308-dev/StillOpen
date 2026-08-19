FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY fixtures ./fixtures

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --all-extras --no-dev

EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn stillopen_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
