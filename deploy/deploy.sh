#!/bin/bash
# One-shot deploy: pull latest, rebuild the container, restart it.
# Migrations run automatically inside the container's entrypoint.
# Run this on the Ubuntu box after pushing changes to git.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/movie_tracker}"

echo "→ Pulling latest from git..."
cd "$REPO_DIR"
git pull --ff-only

echo "→ Building image..."
docker compose build

echo "→ Restarting container (runs migrations on start)..."
docker compose up -d

echo "→ Status:"
docker compose ps
echo "→ Recent logs:"
docker compose logs --tail=20 api

echo "✓ Deployed."
