# Cued Up backend — Ubuntu server runbook (Docker)

> THIS FILE IS FOR CLAUDE RUNNING ON THE UBUNTU BOX. After `git pull`, copy it
> to the repo root so it's picked up automatically:
>
>     cp deploy/SERVER_CLAUDE.md CLAUDE.md
>
> (Root `CLAUDE.md` is gitignored on purpose — the copy stays local to this
> machine and won't conflict with the dev Mac's version.)

## What this machine is

The production backend host for Cued Up, an iOS app on TestFlight Internal
Testing. The Flask API runs in a **Docker container** (image built from
`server/Dockerfile`, orchestrated by `docker-compose.yml` at the repo root),
stores data in SQLite on a **bind mount** (`server/instance/` on the host),
and is exposed to the internet via an existing Cloudflare Tunnel as
`https://cuedup-api.thenobodyprojects.com`. If this box sleeps or the
container dies, the app dies for every tester. Goals when working here: keep
the container up, keep the database safe, change as little as possible.

Why Docker: the Pipfile pins Python 3.14, which Ubuntu's apt doesn't ship.
The `python:3.14-slim` base image makes the host's Python irrelevant.

Working style: ship-fast mode. Run commands and write files directly rather
than telling the user to do it. Don't add features here — this box is for
deploy/ops only. Never mention AI/Claude/Anthropic in code, commits, or docs.

## Layout

- Repo: `~/movie_tracker` (this file is `deploy/SERVER_CLAUDE.md` inside it)
- Container: `cuedup-api` -> gunicorn on `127.0.0.1:5555` (loopback only)
- Database: `~/movie_tracker/server/instance/watchlist.db` — on the HOST via
  bind mount; survives image rebuilds. SQLite WAL mode (set by app pragmas).
- Secrets: `~/movie_tracker/server/.env` (never committed, never baked into
  the image — `.dockerignore` excludes it; compose injects it at runtime)
- Public ingress: Cloudflare Tunnel (`cloudflared` on the host) maps
  `cuedup-api.thenobodyprojects.com` -> `http://localhost:5555`
- Backups: `~/backups/cuedup/` via `deploy/backup.sh` (host cron, nightly)
- `deploy/cuedup-api.service` is the LEGACY non-Docker systemd unit — ignore
  it unless explicitly asked to run without Docker.

## First-time setup (in order)

### 0. Install Docker

```bash
sudo apt update && sudo apt install -y git sqlite3 curl jq
# Docker Engine + compose plugin (official convenience script):
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in (or `newgrp docker`) so the group applies
docker --version && docker compose version
sudo systemctl enable docker   # containers come back after reboot
```

### 1. Clone and create .env

```bash
cd ~ && git clone <repo-url> movie_tracker
cd movie_tracker/server
cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
OMDB_API_KEY=REPLACE_ME
DATABASE_URL=
WATCHMODE_API_KEY=
APPLE_SHARED_SECRET=
FLASK_APP=app.py
EOF
chmod 600 .env
```

Ask the user for the real `OMDB_API_KEY` (omdbapi.com). `DATABASE_URL` stays
blank (= SQLite). `WATCHMODE_API_KEY` optional (streaming lookup disabled in
V1). `APPLE_SHARED_SECRET` comes from App Store Connect (App Information ->
App-Specific Shared Secret) — until it's set, in-app purchases return 503
and the app's purchase UI stays in "not available yet" mode; everything else
works fine without it.

IMPORTANT: if a `.env` already exists with real secrets, do NOT regenerate
the JWT/SECRET keys — that logs every tester out.

### 2. Build and start

```bash
cd ~/movie_tracker
docker compose up -d --build
docker compose logs -f api   # watch: migrations run, then gunicorn starts
```

The entrypoint runs `flask db upgrade` on every start (idempotent,
single-instance, safe), then launches gunicorn (2 gthread workers x 8
threads). `restart: unless-stopped` + the docker service enabled at boot
means it survives reboots.

### 3. Cloudflare Tunnel ingress

The tunnel for `thenobodyprojects.com` already exists on this host. Add a
hostname:

- Dashboard: Zero Trust -> Networks -> Tunnels -> the tunnel -> Public
  Hostname -> Add: subdomain `cuedup-api`, domain `thenobodyprojects.com`,
  service `HTTP` -> `localhost:5555`.
- Or in `/etc/cloudflared/config.yml`, ABOVE the catch-all 404 rule:

```yaml
  - hostname: cuedup-api.thenobodyprojects.com
    service: http://localhost:5555
```

then `sudo systemctl restart cloudflared`.

### 4. Backups (do not skip)

```bash
chmod +x ~/movie_tracker/deploy/backup.sh
~/movie_tracker/deploy/backup.sh        # run once now, confirm it works
crontab -e
# add:  15 3 * * * $HOME/movie_tracker/deploy/backup.sh >> $HOME/backups/cuedup/backup.log 2>&1
```

The script uses host `sqlite3 .backup` against the bind-mounted DB file —
safe while the container runs. A plain `cp` of a live WAL database is NOT a
safe backup.

### 5. Keep the box awake

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

If it's a desktop install, also disable suspend in the GUI power settings.

## Verify the deployment

```bash
# 1. Container healthy + API up locally
docker compose ps                      # state: running (healthy)
curl -s localhost:5555/ | jq .         # {"message": "Movie Tracker backend is running!"}

# 2. Public URL end to end
curl -s https://cuedup-api.thenobodyprojects.com/ | jq .

# 3. Full auth round-trip
curl -s -X POST localhost:5555/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"smoketest_delete_me","password":"smoketest123"}' | jq .
TOKEN=$(curl -s -X POST localhost:5555/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"smoketest_delete_me","password":"smoketest123"}' | jq -r .access_token)
curl -s localhost:5555/watchlist/ -H "Authorization: Bearer $TOKEN" | jq .   # []
curl -s "localhost:5555/movies/search?q=inception" -H "Authorization: Bearer $TOKEN" | jq '.[0]'
curl -s -X DELETE localhost:5555/auth/me -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"password":"smoketest123"}' | jq .

# 4. WAL mode on (run on the HOST against the bind-mounted file)
sqlite3 ~/movie_tracker/server/instance/watchlist.db 'PRAGMA journal_mode;'  # wal
```

All four pass -> tell the user the backend is live; TestFlight builds reach
it automatically (the app's release config points at the public URL).

## Routine operations

```bash
# Deploy latest code (pull, rebuild, restart; migrations run on start):
~/movie_tracker/deploy/deploy.sh

# Logs:
docker compose -f ~/movie_tracker/docker-compose.yml logs -f api

# Restart without rebuild:
docker compose -f ~/movie_tracker/docker-compose.yml restart api

# Shell inside the container:
docker compose -f ~/movie_tracker/docker-compose.yml exec api sh

# Comp a tester as Pro:
docker compose -f ~/movie_tracker/docker-compose.yml exec api python grant_pro.py <username>

# DB peek (host):
sqlite3 ~/movie_tracker/server/instance/watchlist.db \
  'SELECT id, username, pro_status, privacy_mode FROM users;'

# Restore a backup (container MUST be stopped first):
cd ~/movie_tracker && docker compose stop api
gunzip -k ~/backups/cuedup/watchlist-<stamp>.db.gz
cp ~/backups/cuedup/watchlist-<stamp>.db server/instance/watchlist.db
rm -f server/instance/watchlist.db-wal server/instance/watchlist.db-shm
docker compose start api
```

## Troubleshooting

- **Container won't start / restart loop:** `docker compose logs api`. Usual
  suspects: missing/malformed `server/.env`, migration failure (back up the
  DB before touching migration state), port 5555 already taken by a stray
  process (`sudo lsof -i :5555`).
- **Public URL 502/530:** tunnel can't reach the container. Check
  `systemctl status cloudflared`, then `curl localhost:5555/` on the host.
- **Public URL 404 but localhost works:** ingress rule ordering — the
  hostname rule must come before the catch-all in config.yml.
- **`database is locked`:** shouldn't happen (WAL + busy_timeout are set by
  the app). If it does, make sure nothing on the HOST holds a write
  transaction (a stray `sqlite3` shell counts).
- **Permissions on instance/:** the container runs as root by default, so
  host files it creates are root-owned. If host-side scripts can't read the
  DB, `sudo chown -R $USER server/instance` (backup.sh reads, doesn't write).
- **OMDb errors / empty search:** key invalid or 1000/day quota exhausted.
- **429 from /auth/login during testing:** in-process rate limiter (15
  attempts / 5 min per IP and per username). Wait or restart the container.
- **/iap/verify-receipt returns 503:** `APPLE_SHARED_SECRET` not set in
  `.env`. Expected until App Store Connect setup is done.

## Server-relevant behavior notes (as of 2026-06-10)

- SQLite pragmas (WAL, busy_timeout=5000, foreign_keys=ON) set by an engine
  hook in `server/app.py` — no manual DB config.
- Account deletion (`DELETE /auth/me`) cleans up all dependent rows. FK
  enforcement is ON; ad-hoc `DELETE FROM users` in a sqlite shell will fail
  unless dependents go first — use the API.
- `privacy_mode='private'` users are excluded from friends' discovery feeds.
- Subscriptions: `POST /iap/verify-receipt` verifies an App Store receipt
  with Apple and flips `pro_status` to paid/trial; `/auth/me` lazily
  downgrades lapsed subscribers. One Apple subscription links to exactly one
  account (409 otherwise). Comp users are never downgraded.
- The discovery feed and hosting Movie Night are Pro-gated (402 with
  `code: pro_required`). Testers get comped via `grant_pro.py`.
