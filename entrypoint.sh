#!/bin/bash
set -e

echo "=== Pi-hole Checkpoint Starting ==="

# Run migrations
echo "[1/3] Running database migrations..."
python manage.py migrate --noinput

# Function to start scheduler
start_scheduler() {
    python manage.py runapscheduler &
    SCHEDULER_PID=$!
    echo "Scheduler started with PID: $SCHEDULER_PID"
}

# Start scheduler
echo "[2/3] Starting backup scheduler..."
start_scheduler

# Monitor and restart scheduler if it dies
monitor_scheduler() {
    while true; do
        sleep 30
        if ! kill -0 $SCHEDULER_PID 2>/dev/null; then
            echo "WARNING: Scheduler process died, restarting..."
            start_scheduler
        fi
    done
}

# Start monitor in background
monitor_scheduler &
MONITOR_PID=$!

# Trap signals to clean up
cleanup() {
    echo "Shutting down..."
    kill $MONITOR_PID 2>/dev/null || true
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
