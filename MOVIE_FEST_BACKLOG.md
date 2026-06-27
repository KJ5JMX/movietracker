# ShelfMates — Movie Fest / Points / Backlog

Running list so nothing gets lost. Status tags: [DECIDED], [TODO], [BUG], [DISCUSS].

## Points & gamification (design)

- [DECIDED] Points ("plot points") are **purely cosmetic** — they only unlock
  flair/titles. Nothing with real-world value, so faking buys nothing.
- [DECIDED] Points are awarded **only for cheat-proof bounded events**:
  - 2 points for rating the Movie of the Week
  - 2 points for rating a Battle (participation)
- [DECIDED] **No points for raw ratings/reviews** on regular library items, and
  **no points for review text** — points were never going to buy good reviews.
  Review stays optional and unrewarded.
- [DECIDED] Review quality comes from audience (friends see it) + structured
  prompts (one-line take, "who'd like this", vibe chip), not from a length rule.
- [DECIDED] **Earning an achievement grants points too**, escalating so later
  achievements are worth more: first ~5, then +2 each one after. This is the
  main income that feeds the flair shop (and it's cheat-proof, since achievements
  are milestone-gated).
  - [DECIDED] Escalation is **per-ladder tier**: tier 1 of any ladder = 5, tier 2
    = 7, tier 3 = 9, and so on. Predictable and order-independent.
- [DECIDED] Achievements and flair are **two separate systems**: achievements =
  what you've done (earned automatically), flair = what you choose to show
  (bought with points).
- [TODO] Points ledger + balance per user; display next to profile name.
- [DISCUSS] Movie of the Week cadence -> 2 weeks (gives time to actually watch).
  No schema change needed; `week_key` is just a label. Adjust copy if "biweekly".

## Bugs

- [BUG] **Movie Night recommends unreleased titles.** Tested today: it suggested
  a movie that's on my list but not out yet (I have a release reminder set on it).
  Fix: Movie Night should exclude items that aren't released (coming_soon /
  release_date in the future).

## Feature requests

1. [TODO] **Lists: separate watched vs want-to-watch.** A user wants to see
   everything they've already done vs. their queue. Add a status filter/segment
   (e.g. All / Want to / Watched) or a "remove from watched" path.
2. [TODO] **Discovery detail: no "add to list" inside the card.** The discovery
   feed card has "add to list" on the main card, but tapping in to read about the
   movie opens a detail that looks like an in-list item with no way to add it.
   - [CONFIRMED] Marking watched from inside that card is fine to keep (you may
     have already seen it).
   - Add an "Add to my list" action inside the detail when the item is NOT
     already in the user's list.
3. [TODO] **Settings: collapse Preferences + Your Taste into dropdown sections**
   (like Profile) to make room for an Achievements entry.
4. [TODO] **Settings: Plot Points section** with the user's balance and an
   "Add to profile" toggle (show/hide points + flair next to their name).
5. [TODO] **Achievements page/section.** See draft below.

## Achievements (each tier = its own name + icon)

Revised per decisions (watched is now the long prestige ladder; adding is the
short easy one; seasons brought down to reachable; reviewer dropped).

- [DECIDED] Watched (the prestige ladder): 5 / 25 / 50 / 100 / 200 / 350
- [DECIDED] Added to list (easy, early grabs): 10 / 25 / 50 / 100
- [DECIDED] Shares / recs: 5 / 20 / 50 / 100 / 150 / 200
- [DECIDED] Seasons completed (brought down): 5 / 15 / 30 / 60 / 100
- [DECIDED] Movie nights: 1 / 4 / 8 / 16 / 32 / 52
- [DECIDED] Battles: 6 / 12 / 18 / 24 / 28 / 32
- [DECIDED] Movie of the Week: 1 / 4 / 8 / 16 / 32 / 52
- [DECIDED] Listened (songs): mirrors Watched — live
- [DECIDED] Books: mirrors Watched — live
- [DROPPED] Reviewer-by-count — re-opens the "good"-review farm. Revisit only if
  a non-farmable version is found (e.g. count reviews only on watched+rated items
  that a friend actually engaged with).

Notes:
- Mix of instant grabs (first watch, first movie night, added 10) and long
  community-tenure ladders (52 movie nights, 32 battles) is intentional — the
  long ones signal "been here a while." Numbers above are starting points; tune
  after seeing real usage.
- Time-gated events (battles, MoW) can't be rushed, so make sure new users have
  easy non-event wins available on day one.

## Flair / titles (DISCUSS — unlocked with points)

Film & TV: Actor, Actress, Director, Producer, Executive Producer, Screenwriter,
Showrunner, Cinematographer, Film Editor, Production Designer, Art Director,
Casting Director, Costume Designer, Makeup Artist, Hair Stylist, Stunt
Coordinator, Stunt Performer, Voice Actor, Composer, Music Supervisor, Sound
Designer, VFX Artist, Animator, Production Assistant

Music: Singer, Songwriter, Music Producer, Musician, Band, DJ, Composer,
Recording Engineer, Mixing Engineer, Mastering Engineer, Conductor

Books: Author, Novelist, Ghostwriter, Poet, Journalist, Book Editor, Proofreader,
Illustrator, Cover Designer, Publisher, Literary Agent, Narrator

- [DECIDED] Flair is priced along the career ladder: lower roles (Production
  Assistant, etc.) are cheap, prestige roles (Director, Executive Producer) cost
  more. Same idea per category (Music, Books).
- [DECIDED] Achievement-completion points (above) are the income that makes the
  shop reachable, so prices can scale up with the ladder without starving it.
- [TODO] Assign a point cost to each title in price bands (entry / mid / senior /
  elite) once the achievement-point income curve is locked, so the elite titles
  feel earned but not impossible.
