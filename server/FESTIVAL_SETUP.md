# ShelfMates Movie Fest — setup & deploy

Movie of the Week + monthly Battles, plus an admin curation page at `/admin`.
Backend is built, migrated, and tested; the iOS app screens are wired in.

## 1. Run the migration

On the Ubuntu box (or locally):

```bash
cd server
pipenv run flask db upgrade   # applies the fest tables + the week rename
```

Adds four tables: `movies_of_week`, `movie_of_week_completions`, `battles`,
`battle_votes`. The migration is reversible (`flask db downgrade f1a2b3c4d5e6`).

## 2. Set the admin env vars

In the backend `.env`:

```
ADMIN_EMAILS=somethingclever182@gmail.com
# optional local-only fallback for hitting /admin via curl on the box:
ADMIN_TOKEN=$(openssl rand -hex 32)
```

`ADMIN_EMAILS` is the allowlist the app checks against the email Cloudflare
Access injects. Use the same email you'll log into Cloudflare with.

## 3. Put /admin behind Cloudflare Access

This is the login. You already run the tunnel, so this is config, not code.

1. Cloudflare Zero Trust dashboard -> Access -> Applications -> Add an application
   -> Self-hosted.
2. Application domain: `cuedup-api.thenobodyprojects.com`, path: `/admin`.
   (Scope it to the path so only the admin panel is gated, not the whole API.)
3. Add a policy: Action **Allow**, Include -> Emails -> your email(s). Everyone
   else is blocked at Cloudflare's edge before the request ever reaches Flask.
4. Save. Visiting `https://cuedup-api.thenobodyprojects.com/admin` now prompts a
   Cloudflare login (email one-time-PIN by default) and works from anywhere.

Defense in depth: even if the tunnel were misconfigured, Flask still rejects any
request whose `Cf-Access-Authenticated-User-Email` header isn't in
`ADMIN_EMAILS` (403). Cloudflare strips that header from inbound client requests,
so it can't be spoofed from the public side.

## 4. Curate

At `/admin` you can:
- Search OMDb, pick the **Movie of the Week**, set its week, blurb, and the
  streaming services it's on (you verify these before pushing).
- Build a **Battle**: pick two movies, set each one's streaming, set the voting
  window in days. Close a battle early from the list.

Setting a new Movie of the Week deactivates the previous one, so the app only
ever shows the current pick.

## 5. What the app does

Entry point: the **+** button on Lists fans out a radial menu — Add / Movie Fest
/ Battle.

- **Movie Fest** (`MovieOfWeekScreen`): shows the current pick with OMDb plot,
  your curated "Streaming here", and a watch + rate + review flow. Marking it
  complete is sticky for the week and creates a watched item in the user's
  library (which flows into the discovery feed).
- **Battles** (`BattleScreen`): two movies, a live countdown, vote (changeable
  until the window closes), and live vote share. The winner is intended to
  surface in discovery as a battle pick.

## Public endpoints (JWT)

| Method | Path | Body |
|---|---|---|
| GET | `/festival/movie-of-week` | — |
| POST | `/festival/movie-of-week/complete` | `{ rating?, review? }` |
| GET | `/festival/battles` | — |
| POST | `/festival/battles/<id>/vote` | `{ choice: "a" \| "b" }` |

## Admin endpoints (Cloudflare Access + ADMIN_EMAILS)

| Method | Path | Body |
|---|---|---|
| GET | `/admin/` | (HTML page) |
| GET | `/admin/api/search?q=` | — |
| GET/POST | `/admin/api/movie-of-week` | POST: `{ imdb_id, title, year, poster, streaming[], week_key?, blurb? }` |
| GET/POST | `/admin/api/battles` | POST: `{ title, movie_a{}, movie_b{}, days }` |
| POST | `/admin/api/battles/<id>/close` | — |

## Honest caveats (carried over from the design discussion)

- **Battle voting needs density.** With a handful of users a battle may get a
  few votes; the "winner -> discovery" stamp is only as meaningful as the number
  of voters behind it. Movie of the Week works fine at any size; battles get
  better as the userbase grows.
- **Curated streaming is US-only and hand-maintained.** It's authoritative for
  festival picks because you verify it, but it doesn't auto-refresh — re-check it
  if a title's availability changes mid-month.
- **Discovery integration is partial.** Completing a pick creates a watched item
  that surfaces through the existing friend-activity feed (strongest when rated
  4+). A dedicated "battle picks" discovery shelf isn't built yet.
