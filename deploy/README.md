# Deploying the backend

The single source of truth is [`SERVER_CLAUDE.md`](SERVER_CLAUDE.md) — the
Docker-based runbook for the Ubuntu box (setup, verification, backups,
troubleshooting, routine deploys). On the server, copy it to the repo root as
`CLAUDE.md` so Claude Code picks it up automatically:

```bash
cp deploy/SERVER_CLAUDE.md CLAUDE.md
```

Quick reference:

```bash
~/movie_tracker/deploy/deploy.sh      # deploy latest (pull, rebuild, restart)
docker compose logs -f api            # tail logs (run from the repo root)
~/movie_tracker/deploy/backup.sh      # nightly via cron; safe to run manually
```

Note on the mobile app: no config flipping is needed. `CuedUp/src/config.ts`
auto-selects the backend — release/TestFlight builds always use the public
URL, dev builds through Metro use the local Flask server.

`cuedup-api.service` is the legacy non-Docker systemd unit, kept only as a
fallback. Ignore it unless deliberately running without Docker.
