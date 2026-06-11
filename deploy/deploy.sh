#!/bin/bash
# One-shot deploy: pull latest, rebuild the container, restart it.
# Migrations run automatically inside the container's entrypoint.
# Run this on the Ubuntu box after pushing changes to git.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/movie_tracker}"

echo "→ Pulling latest from git..."
cd "$REPO_DIR"
git pull --ff-only

echo "→ Building image and (re)starting container (migrations run on start)..."
# `up --build --wait` rebuilds the image, recreates the container if the image
# changed, runs it detached, and blocks until the healthcheck passes. Compose
# v5 removed the `-d` flag; `--wait` implies detached and is what replaces it.
docker compose up --build --wait

echo "→ Status:"
docker compose ps
echo "→ Recent logs:"
docker compose logs --tail=20 api

echo "✓ Deployed."
