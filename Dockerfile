FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 mcp

USER mcp

ENTRYPOINT ["python", "-m", "open_google_mcp"]
