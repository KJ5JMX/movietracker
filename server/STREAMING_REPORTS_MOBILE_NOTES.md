# Streaming availability reports — backend done, mobile TODO

The backend (`server/`) is built, migrated, and tested. The CuedUp mobile app
isn't in this workspace, so this file is the spec for wiring the two screens.

## What the backend gives you

Base path: `/streaming`. All routes require the usual JWT `Authorization: Bearer`
header. Platform must be one of: `netflix`, `hulu`, `amazon`, `hbo`, `disney`,
`other` (sent lowercase; backend also lowercases). Country defaults to `US`.

| Method | Path | Body / query | Use |
|---|---|---|---|
| POST | `/streaming/report` | `{ imdb_id, platform, country? }` | Report a platform from the rating flow. Upserts: repeat report on same (title, country, platform) just refreshes it + bumps `confirm_count`. Returns 201 new / 200 existing. |
| GET | `/streaming/reports` | `?imdb_id=tt123&country=US` | All *active* reports for a title, freshest first. Powers the detail screen. |
| POST | `/streaming/report/<id>/confirm` | — | "Still there" — refresh freshness + bump count. |
| POST | `/streaming/report/<id>/remove` | — | "Not there anymore" — deactivates. A later report re-activates it. |

Each report object:

```json
{
  "id": 1,
  "imdb_id": "tt0111161",
  "country": "US",
  "platform": "netflix",
  "confirm_count": 3,
  "last_confirmed_at": "2026-06-26T15:14:55Z",
  "days_since_confirmed": 0
}
```

`days_since_confirmed` is precomputed so the UI doesn't do date math — use it for
the "reported 3 weeks ago" label and for stale-styling (e.g. grey out > 30 days).

## Mobile change 1 — platform dropdown in the rating flow

When a user marks something **watched** and rates it, add one optional picker:
"Where did you watch it?" with options Netflix / Hulu / Amazon / HBO / Disney /
Other. Keep it optional — don't block saving the rating on it.

On save, after the existing watchlist PATCH, fire:

```ts
// platform: 'netflix' | 'hulu' | 'amazon' | 'hbo' | 'disney' | 'other'
async function reportPlatform(imdbId: string, platform: string) {
  await api.post('/streaming/report', { imdb_id: imdbId, platform });
  // country omitted -> backend defaults to "US"
}
```

(`api` = whatever axios/fetch wrapper already attaches the JWT. Match the call
style used in your existing watchlist requests.)

## Mobile change 2 — detail screen "where to watch" block

On the movie/detail screen, fetch and render the active reports:

```ts
const { data } = await api.get('/streaming/reports', {
  params: { imdb_id: imdbId },   // country defaults to US server-side
});
```

For each report, show: platform name + a freshness line built from
`days_since_confirmed`:

- `0` → "reported today"
- `1` → "reported yesterday"
- `< 7` → "reported N days ago"
- `< 30` → "reported N weeks ago"
- else → "reported N months ago" + grey/stale styling

Next to each, two tap targets:

- **Still there** → `POST /streaming/report/{id}/confirm`, then refetch the list.
- **Not anymore** → `POST /streaming/report/{id}/remove`, then refetch the list.

If the list is empty, show nothing (or a quiet "No reports yet"). Don't fabricate
availability — empty is honest.

## Why it's shaped this way (so future-you doesn't undo it)

- **Honest staleness over false precision.** Every report carries its age. A
  visibly-old report beats a clean-looking one that's silently wrong — this is
  the Waze/GasBuddy pattern: show the age, let the crowd refresh it.
- **No incentive to cheat.** The data unlocks nothing, so fake reports buy
  nothing. That's deliberate — don't later tie points/rewards to reporting or
  you re-import a cheating problem.
- **Density caveat.** The confirm/remove loop only self-maintains once enough
  people hit the *same* title. At small scale, you (the curator) seed and refresh
  it by hand; treat this as the free, lower-fidelity layer. The paid, always-fresh
  API lookup (`WATCHMODE_*` in config, currently off) is the eventual upgrade.
- **US-only for now.** `country` defaults to US everywhere. When you expand,
  start passing real country codes from the user's profile setting — the column
  and the unique constraint already account for region.
