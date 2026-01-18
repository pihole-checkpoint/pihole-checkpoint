#!/bin/bash
set -e

echo "=== Pi-hole Checkpoint Starting ==="

# Run migrations
echo "[1/3] Running database migrations..."
python manage.py migrate --noinput

# Start scheduler in background
echo "[2/3] Starting backup scheduler..."
python manage.py runapscheduler &
SCHEDULER_PID=$!
echo "Scheduler started with PID: $SCHEDULER_PID"

# Trap signals to clean up scheduler
cleanup() {
    echo "Shutting down..."
    kill $SCHEDULER_PID 2>/dev/null || true
    wait $SCHEDULER_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start Gunicorn (foreground)
echo "[3/3] Starting web server..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --access-logfile - \
    --error-logfile -
