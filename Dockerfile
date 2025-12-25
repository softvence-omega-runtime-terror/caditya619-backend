# ============================
# Stage 1: Builder
# ============================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies required to build wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmariadb-dev-compat \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Build wheels (faster + reproducible)
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir -r requirements.txt -w /wheels


# ============================
# Stage 2: Runtime
# ============================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime-only system deps (no build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb-dev-compat \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copy application code
COPY . .

# Create media directory
RUN mkdir -p /app/media

# Create non-root user
RUN useradd --create-home --shell /bin/bash quikle \
    && chown -R quikle:quikle /app

USER quikle

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
