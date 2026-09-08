FROM python:3.10-slim

# Install system dependencies (tzdata enables TZ=America/Santiago)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official Astral binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/app/src \
    TZ=America/Santiago

# Copy project metadata files first for optimal layer caching
COPY pyproject.toml .python-version README.md ./

# Install project dependencies
RUN uv pip install --system -r pyproject.toml

# Copy project code and data
COPY main.py ./
COPY src/ ./src/
COPY skills/ ./skills/
COPY data/ ./data/

# Install package in editable/development mode
RUN uv pip install --system -e .

# Run AuraBot backend
CMD ["python", "main.py"]
