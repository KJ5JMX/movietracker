# ShelfMates — Achievements, Points & Flair spec

Theme: cozy retro, physical-media nostalgia, movie-night culture, pre-streaming.
Two separate systems: **Achievements** (earned automatically by doing) and
**Flair** (bought with points). Earning an achievement tier also grants points
(per-ladder escalation: tier 1 = 5, then +2 each: 5 / 7 / 9 / 11 / 13 / 15).

## Achievement ladders & tiers

Each ladder has a name + motif icon; each tier has its own name + badge.

### 🎞️ Screening Room — movies watched
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 5 | First Showing | 5 |
| 2 | 25 | Double Feature | 7 |
| 3 | 50 | Marathoner | 9 |
| 4 | 100 | Reel Devotee | 11 |
| 5 | 200 | Silver Screener | 13 |
| 6 | 350 | Projectionist | 15 |

### 📼 The Stack — items added to list
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 10 | Shelf Starter | 5 |
| 2 | 25 | Stack Builder | 7 |
| 3 | 50 | Shelf Stacker | 9 |
| 4 | 100 | Tower Keeper | 11 |

### 📣 Word of Mouth — shares / recs sent
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 5 | Tipster | 5 |
| 2 | 20 | Tape Passer | 7 |
| 3 | 50 | Connector | 9 |
| 4 | 100 | Tastemaker | 11 |
| 5 | 150 | Hype Engine | 13 |
| 6 | 200 | The Oracle | 15 |

### 📺 The Box Set — TV seasons completed
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 5 | Pilot Light | 5 |
| 2 | 15 | Box Set Opener | 7 |
| 3 | 30 | Season Sweeper | 9 |
| 4 | 60 | Binge Master | 11 |
| 5 | 100 | Series Finale | 13 |

### 🍿 Movie Night — movie nights joined
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 1 | First Invite | 5 |
| 2 | 4 | Regular | 7 |
| 3 | 8 | Snack Captain | 9 |
| 4 | 16 | Night Owl | 11 |
| 5 | 32 | Couch Commander | 13 |
| 6 | 52 | Host of the Year | 15 |

### ⚔️ The Arena — battles participated
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 6 | Challenger | 5 |
| 2 | 12 | Contender | 7 |
| 3 | 18 | Brawler | 9 |
| 4 | 24 | Headliner | 11 |
| 5 | 28 | Main Event | 13 |
| 6 | 32 | Champion | 15 |

### 🎬 Cued In — Movie of the Week completed
| Tier | Count | Name | Points |
|---|---|---|---|
| 1 | 1 | Tuned In | 5 |
| 2 | 4 | Subscriber | 7 |
| 3 | 8 | Loyal | 9 |
| 4 | 16 | Devotee | 11 |
| 5 | 32 | Ride or Die | 13 |
| 6 | 52 | Charter Member | 15 |

### 🎵 On Repeat — songs listened (BLOCKED: needs songs)
First Spin (5) / B-Side (25) / Heavy Rotation (50) / Mixtape Maker (100) /
Crate Digger (200) / Audiophile (350)

### 📚 The Reading Room — books finished (BLOCKED: needs books)
First Chapter (5) / Bookmarked (25) / Page Turner (50) / Shelf Reader (100) /
Bookworm (200) / Well-Read (350)

## Icon system (Reddit-style badges)

One **motif** per ladder (reel, VHS/stack, megaphone, boxed set, popcorn,
crossed reels, clapper, cassette, book). Tiers escalate by **badge frame
material**, on-theme retro:

1. Cardboard  2. Bronze  3. Silver  4. Gold  5. Holographic  6. Neon

So "Screening Room" tier 4 = the film-reel motif in a gold frame. This makes ~40
badges from 9 motifs + 6 frames, all visually consistent. (Art is a separate
effort — I can generate simple placeholders like the Fest icons, or you drop in
finished art.)

## Flair (bought with points, priced by career ladder)

Four price bands; lower roles cheap, prestige roles expensive.

### 🎬 Film & TV
- Entry (10): Production Assistant, Stunt Performer, Hair Stylist, Makeup Artist, Animator, Voice Actor
- Mid (25): Costume Designer, Casting Director, Art Director, Sound Designer, VFX Artist, Film Editor, Music Supervisor, Stunt Coordinator
- Senior (50): Cinematographer, Production Designer, Screenwriter, Composer, Actor, Actress
- Elite (100): Director, Producer, Executive Producer, Showrunner

### 🎵 Music
- Entry (10): Musician, Band, DJ
- Mid (25): Singer, Songwriter, Recording Engineer, Mixing Engineer, Mastering Engineer
- Senior (50): Music Producer, Composer
- Elite (100): Conductor

### 📚 Books
- Entry (10): Proofreader, Illustrator, Cover Designer, Narrator
- Mid (25): Ghostwriter, Book Editor, Journalist, Poet
- Senior (50): Author, Novelist, Literary Agent
- Elite (100): Publisher

## Points economy sanity check

Maxing a 6-tier ladder = 5+7+9+11+13+15 = 60 pts. With ~7 live ladders that's a
few hundred points over a long time, plus 2 per Movie of the Week / battle. Entry
flair (10) is reachable fast; Elite (100) is a long-haul flex. Tune bands after
real usage.
