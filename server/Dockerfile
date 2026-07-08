# Cued Up backend. Build context = server/ directory.
#
# The base image provides Python 3.14 (matching the Pipfile pin) regardless of
# what the host Ubuntu ships — that's the main reason this app is containerized.
FROM python:3.14-slim

# sqlite3 CLI is handy for debugging inside the container; curl for healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies from the lockfile, system-wide (no venv inside a container).
RUN pip install --no-cache-dir pipenv
COPY Pipfile Pipfile.lock ./
RUN pipenv install --system --deploy && pip uninstall -y pipenv

# Streaming availability provider (free/unofficial JustWatch bridge). Installed
# outside the Pipfile lock on purpose: it keeps `pipenv --deploy` valid without a
# relock. Depends only on httpx, already installed above.
#
# PINNED to ==0.13 on purpose. Newer releases dropped Python 3.10 and changed
# prepare_search_request()'s signature; unpinned, the container silently pulled a
# newer, incompatible version and every lookup failed. Bump this only alongside a
# matching code change in streaming_lookup.py.
RUN pip install --no-cache-dir "simple-justwatch-python-api==0.13"

COPY . .

ENV FLASK_APP=app.py \
    PYTHONUNBUFFERED=1

# SQLite lives in /app/instance — docker-compose bind-mounts this to the host
# so the database survives image rebuilds.
VOLUME /app/instance

EXPOSE 5555

# Migrations run on every start; they're idempotent and this is a
# single-instance deployment, so there's no migration race to worry about.
ENTRYPOINT ["./entrypoint.sh"]
