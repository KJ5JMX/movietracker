# Bardo — Backend Runbook

> Live deployment doc + current state for the Bardo backend. Read `BackCLAUDE.md` (backend
> deep dive, may lag) and `CuedUp/CLAUDE.md` (mobile onboarding, kept current) for full
> architecture. `AGENTS.md` here is a mirror of this file; update both together.

## Current state (2026-08-10 · v2.0)

**Where things stand:** the 2026-08 free/pro rework shipped. **Free is capped** (250 titles,
3 collections, 4 hosted Movie Nights/month — 402 `limit_reached`), **Pro uncaps** and adds
public Discovery (`/feed/public` + `privacy_mode="public"`, 402 `pro_required`), the Pro
avatar shop, and **plot coins** (new `cosmetics_routes.py`: `/coins` balance + lazy Pro
grants of 3-at-signup/1-a-month, `/pro-avatars` catalog + buy, `/coins/gift` → 30-day friend
trial; every movement logged in `coin_ledger`). IAP verifies both the Pro sub
(`/iap/verify-receipt`) and consumable coin packs (`/iap/verify-coins`,
`cuedup.coins.{1,3,5}`). The friend Discovery feed (`/feed/`) is **free now**. TMDB fills in
backdrops, budget/revenue, and TV season/episode data (`TMDB_API_KEY`, degrades gracefully);
per-episode watched tracking landed. Book club chat is ungated with reactions + spoiler
flags. "Movie of the Week" is now "Movie Week" in copy. Profile API serves stats + banner;
social routes serve public/friend profile summaries. Admin panel: broadcast announcements +
**pro-avatar upload/manage** (art stored base64 in DB, served as PNGs). App Store Connect
info is filled out and the shared secret reportedly re-added to the box `.env` (not
verifiable from the repo). **Migration head: `f7a2b3c4d5e6`** (new since last note:
discussion spoiler/reactions, group backdrop cache, watchlist backdrop, **pro coin economy**,
episodes watched, profile banner). In progress: Pro avatar art/catalog.

The backend is **deployed and live** on the Ubuntu box in Docker, reached over the
Cloudflare Tunnel at `https://cuedup-api.thenobodyprojects.com`. The runbook below
is the original bring-up procedure and still accurate; this section is the now.

- **Deploy flow:** push to git, then on the box `cd ~/movie_tracker && bash
  deploy/deploy.sh` (pulls, `docker compose up --build --wait`; the container
  entrypoint runs `flask db upgrade` on start, so migrations apply automatically).
  SQLite lives on the host at `server/instance/` (volume-mounted, survives rebuilds).
- **Admin panel** at `/admin` (festival curation) is gated by **Cloudflare Access**:
  Zero Trust → Access → Applications → self-hosted app on
  `cuedup-api.thenobodyprojects.com`, **path `admin`**, One-time-PIN login, Allow
  policy for the admin email. Flask double-checks the injected
  `Cf-Access-Authenticated-User-Email` against `ADMIN_EMAILS` in `server/.env`.
  If `/admin/api/*` calls 403, the Access app path isn't covering them (must be
  `admin`, prefix-matches subpaths).
- **New since build 7** (see `CuedUp/CLAUDE.md` §0 for the full list): Bardo
  Movie Fest (Movie of the Week + battles + admin panel), crowdsourced
  where-to-watch reports, points/achievements/flair gamification, per-category
  notifications. New blueprints: `streaming_routes`, `festival_routes`,
  `gamification_routes`. New tables: `streaming_availability_reports`,
  `movies_of_week`, `movie_of_week_completions`, `battles`, `battle_votes`,
  `user_achievements`, `user_flair`; new `users` columns `points`,
  `flair_selected`, `show_flair`, `notification_settings`. Migration head:
  `a1b2c3d4e5f6`.
- **`server/.env` now needs:** `ADMIN_EMAILS` (comma-separated; the festival
  curator). Optional `ADMIN_TOKEN` for local curl. APNs keys still optional
  (push no-ops without them); achievement/festival pushes ride `push.notify`.
- **iOS:** v2.0 (build 1) — free/pro rework, coins, Discovery/profile redo (see
  `CuedUp/CLAUDE.md` for the app side).
- **Admin broadcast:** `POST /admin/api/notify/broadcast` (audience all/pro/free) sends a
  custom announcement via `push.notify` (category `announcements`: pushes + stores an
  in-app notification, not user-mutable).
- **Pro gating:** caps → 402 `limit_reached` (`watchlist` 250, `groups` 3, `night` 4 hosted
  nights/month); Pro-only → 402 `pro_required` (`/feed/public`, going public). `/feed/` and
  `/night/preview` are open to all.
- **IAP:** `iap_routes.py` verifies the Pro sub (`cuedup.pro.{monthly,yearly}`) and coin
  packs (`cuedup.coins.{1,3,5}`, credited idempotently via `coin_ledger`). 503 until
  `APPLE_SHARED_SECRET` is set on the box. Remaining launch check: sandbox-test a sub AND a
  coin pack on a real device.
- **`server/.env` optional keys:** `TMDB_API_KEY` (backdrops/financials/TV data; null fields
  without it), `APPLE_SHARED_SECRET` (IAP), APNs keys (push no-ops without them).
- **Android:** sideloadable debug-signed APK builds via `android/ &&
  ./gradlew assembleRelease`. Keep `@react-native-async-storage/async-storage`
  pinned to `1.24.0` (v3 needs an unpublished `storage-android` artifact).
- Reference docs: `MOVIE_FEST_BACKLOG.md`, `ACHIEVEMENTS_SPEC.md`,
  `server/FESTIVAL_SETUP.md`.

## Goal

Get the backend running on the Ubuntu box and the iOS app onto **TestFlight Internal
Testing** ASAP. Apple Developer account was purchased 2026-06-03.

## Machine layout

- **Dev Mac (macOS):** builds and uploads the iOS app. Runs Metro for local dev.
- **"iMac" running Ubuntu Linux:** the production backend host. Stays awake/online or
  the app dies for everyone (SQLite lives on this box). Disable sleep on it.
- **Public URL:** Cloudflare Tunnel on `thenobodyprojects.com` (already set up) exposes
  the backend over HTTPS. HTTPS is mandatory because iOS ATS is locked
  (`NSAllowsArbitraryLoads = false`).

## Decided values

- **Bundle ID:** `com.thenobodyprojects.cuedup`
- **Backend public URL:** `https://cuedup-api.thenobodyprojects.com`
- **TestFlight track:** Internal to date; public App Store submission is the next milestone.
- **App config:** `CuedUp/src/config.ts` auto-selects backend by build type (`__DEV__` →
  local, release → public URL; `FORCE_BACKEND` overrides).
  `ITSAppUsesNonExemptEncryption=false` skips the export prompt.

## Runbook

### 1. Backend on the Ubuntu box

The existing `deploy/` folder (systemd unit + deploy.sh) is correct for Ubuntu. Follow
`deploy/README.md` steps 1-6. Specifics:

- Fill the two placeholders in `deploy/cuedup-api.service`: `REPLACE_WITH_VM_USER` and
  the venv path from `pipenv --venv`.
- `.env` secrets: `openssl rand -hex 32` for `SECRET_KEY`, a different one for
  `JWT_SECRET_KEY`, plus your `OMDB_API_KEY`. Leave `DATABASE_URL` blank to use SQLite.
- Confirm `pipenv install --deploy` succeeds with Python 3.13 (Pipfile pins it).
- Service binds to `127.0.0.1:5555` (correct — the tunnel reaches it over loopback).
- `pipenv run flask db upgrade` to create/migrate the DB.

### 2. Cloudflare Tunnel ingress

Add a public hostname to the existing `thenobodyprojects.com` tunnel:

- Zero Trust dashboard -> Networks -> Tunnels -> your tunnel -> Public Hostname -> Add:
  subdomain `cuedup-api`, domain `thenobodyprojects.com`, service `HTTP` ->
  `localhost:5555`.
- Or config.yml-based: add ingress rule `hostname: cuedup-api.thenobodyprojects.com` ->
  `service: http://localhost:5555`, then restart cloudflared.
- Verify: `curl https://cuedup-api.thenobodyprojects.com/` returns the
  "Movie Tracker backend is running!" JSON.
- If you use a different subdomain, update `PUBLIC_BACKEND` in `CuedUp/src/config.ts`.

### 3. Xcode signing + upload (on the dev Mac)

- Open `CuedUp/ios/CuedUp.xcworkspace` (the workspace, NOT the .xcodeproj).
- Select the CuedUp target -> Signing & Capabilities -> check "Automatically manage
  signing" -> set Team to the new Apple Developer account. Xcode registers the bundle ID.
- Scheme to Release, destination "Any iOS Device (arm64)".
- Product -> Archive -> Distribute App -> App Store Connect -> Upload.

### 4. App Store Connect

- Create the app record (My Apps -> +) with bundle ID `com.thenobodyprojects.cuedup` if
  Xcode did not already.
- TestFlight tab -> wait ~5-15 min for the build to process -> add yourself and friends
  as Internal Testers. They accept an email invite and install via the TestFlight app.

## Open risks / notes

- SQLite on the Ubuntu box = single point of failure. Fine for a small internal beta.
  Migrate to Postgres later if it grows (config already auto-rewrites `postgres://`).
- Legal pages are real (`legal_routes.py` serves `/privacy` + `/terms`, app links live).
  Social login is OFF (`ENABLE_SOCIAL_LOGIN=false`), so no placeholder buttons ship. Before
  public submission: swap the `theshelfmateapp@gmail.com` contact email in `legal_routes.py`
  and finish the App Store Connect subscription setup (see Current state).
- `ENABLE_STREAMING_LOOKUP = true` now — backed by the free JustWatch bridge (not Watchmode).
- No em-dashes in user-facing copy. No mention of AI/Claude/Anthropic in repo.
