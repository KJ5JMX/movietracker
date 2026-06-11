#!/bin/sh
# Container entrypoint: migrate, then serve.
set -e

echo "[entrypoint] running database migrations..."
flask db upgrade

echo "[entrypoint] starting gunicorn..."
# Threaded workers: request time is mostly OMDb/iTunes/Open Library network
# wait, and fewer processes = less SQLite write contention.
exec gunicorn \
    --worker-class gthread \
    --workers 2 \
    --threads 8 \
    --timeout 90 \
    --bind 0.0.0.0:5555 \
    --access-logfile - \
    --error-logfile - \
    app:app
