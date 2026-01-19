FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency files first (layer cached if deps unchanged)
COPY pyproject.toml uv.lock ./

# Install dependencies (cached layer when deps unchanged)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code (only this layer rebuilds on code changes)
COPY . .

# Install the project itself (fast - deps already installed)
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/data /app/backups /app/staticfiles

RUN uv run python manage.py collectstatic --noinput

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
