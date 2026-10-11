FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install python dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies for matplotlib, postgres, healthcheck, and timezone data
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libfreetype6 \
    libpng16-16 \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create unprivileged system group and user (UID 1000, GID 1000)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Create mount points and configure ownership
RUN mkdir -p /app/data /app/custom_templates && \
    chown -R appuser:appgroup /app

# Copy application source code and test suite with unprivileged ownership
COPY --chown=appuser:appgroup app /app/app
COPY --chown=appuser:appgroup tests /app/tests

# Metadata labels
LABEL org.opencontainers.image.title="TeslaMate Digest" \
      org.opencontainers.image.description="Automated personal email digests & analytics for TeslaMate" \
      org.opencontainers.image.licenses="MIT"

# Drop privileges to non-root user
USER appuser:appgroup

EXPOSE 8660

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8660/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8660"]
