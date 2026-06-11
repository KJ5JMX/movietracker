# Cued Up — Backend

The Flask API that powers **Cued Up**, an iOS app for tracking what you want
to watch, read, and listen to — and picking what to watch together on Movie
Night. The mobile app lives in a separate repo (`CuedUp`, React Native).

## What the API does

- JWT-authenticated accounts with friend codes (no emails required to connect)
- Cross-media watchlists: movies and TV via OMDb, songs via iTunes Search,
  books via Open Library
- Friends, recommendations, and shared reviews
- Movie Night: combine participants' want-to-watch lists, filter by runtime
  and mood, roll top candidates, record the pick and everyone's ratings
- Discovery feed (Pro): transparent, friend-driven sections — no algorithmic
  ranking, every item says who it came from
- Streaming availability via Watchmode, cached 30 days (disabled for V1)

## Tech

- Python / Flask, SQLAlchemy + Flask-Migrate (Alembic), Flask-JWT-Extended
- SQLite in WAL mode (Postgres-ready via `DATABASE_URL`)
- gunicorn + systemd on Ubuntu, exposed over HTTPS through a Cloudflare Tunnel

## Layout

```
movie_tracker/
├── server/            # Flask app, blueprints, models, migrations
└── deploy/            # systemd unit, deploy script, backup script,
                       # SERVER_CLAUDE.md (server setup runbook)
```

## Running locally

```bash
cd server
pipenv install
# create .env with SECRET_KEY, JWT_SECRET_KEY, OMDB_API_KEY
pipenv run flask db upgrade
pipenv run python app.py   # http://localhost:5555
```

## Deploying

See `deploy/SERVER_CLAUDE.md` for the full server runbook (setup, verify,
backups, troubleshooting). Routine deploys are `deploy/deploy.sh`.
