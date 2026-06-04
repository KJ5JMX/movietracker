#!/bin/bash
# One-shot deploy: pull latest, install any new deps, run migrations, restart service.
# Run this on the Ubuntu VM after pushing changes to git.
set -euo pipefail

# Adjust if your checkout lives somewhere else.
REPO_DIR="${REPO_DIR:-$HOME/movie_tracker}"
SERVICE_NAME="${SERVICE_NAME:-cuedup-api}"

echo "→ Pulling latest from git..."
cd "$REPO_DIR"
git pull --ff-only

echo "→ Installing dependencies..."
cd "$REPO_DIR/server"
pipenv install --deploy

echo "→ Running database migrations..."
pipenv run flask db upgrade

echo "→ Restarting $SERVICE_NAME..."
sudo systemctl restart "$SERVICE_NAME"

echo "→ Status:"
sudo systemctl status "$SERVICE_NAME" --no-pager --lines=5

echo "✓ Deployed."
