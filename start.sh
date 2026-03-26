#!/bin/sh
set -e

DB_WAIT_HOST="${DB_HOST:-}"
DB_WAIT_PORT="${DB_PORT:-3306}"

if [ -z "$DB_WAIT_HOST" ] && [ -n "${DATABASE_URL:-}" ]; then
    DB_WAIT_HOST=$(echo "$DATABASE_URL" | sed -nE 's|^[a-zA-Z0-9+]+://[^@]+@([^:/?]+).*|\1|p')
    PARSED_DB_PORT=$(echo "$DATABASE_URL" | sed -nE 's|^[a-zA-Z0-9+]+://[^@]+@[^:/?]+:([0-9]+).*|\1|p')
    if [ -n "$PARSED_DB_PORT" ]; then
        DB_WAIT_PORT="$PARSED_DB_PORT"
    fi
fi

# Wait for MySQL to be ready
if [ -n "$DB_WAIT_HOST" ]; then
    echo "Waiting for MySQL at $DB_WAIT_HOST:$DB_WAIT_PORT..."
    until nc -z "$DB_WAIT_HOST" "$DB_WAIT_PORT"; do
        echo "MySQL not ready, sleeping 3s..."
        sleep 3
    done
    echo "MySQL is ready!"
else
    echo "No DB host found in DB_HOST or DATABASE_URL. Skipping MySQL wait."
fi

# Run schema migrations (production-safe)
echo "Applying Aerich migrations..."

# Ensure migrations path exists and is writable for first-time boot.
mkdir -p /app/migrations

# First deploy: initialize DB only when no migration files exist yet.
if ! find /app/migrations -type f -name "*.py" ! -name "__init__.py" -print -quit | grep -q .; then
    echo "No migration files found. Running aerich init-db..."
    aerich init-db
fi

echo "Running aerich upgrade..."
aerich upgrade
echo "Aerich migration step completed."

# Start FastAPI
echo "Starting FastAPI..."
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-3}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS"
