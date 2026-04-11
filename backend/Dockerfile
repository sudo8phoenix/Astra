# Multi-stage Dockerfile for AI Assistant Backend

ARG PYTHON_VERSION=3.12
ARG PYTHON_MAJOR_MINOR=3.12

# =========================================================================
# STAGE 1: BUILDER - Install dependencies
# =========================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm as builder

ARG PYTHON_MAJOR_MINOR

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Docker runtime requirements
COPY requirements.docker.txt .

# Install Python dependencies in builder image
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.docker.txt

# =========================================================================
# STAGE 2: RUNTIME - Lightweight production image
# =========================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG PYTHON_MAJOR_MINOR

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages and binaries from builder
COPY --from=builder /usr/local/lib/python${PYTHON_MAJOR_MINOR}/site-packages /usr/local/lib/python${PYTHON_MAJOR_MINOR}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY ./app /app/app
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
