"""ShelfMates achievements + flair catalog and awarding logic.

Two systems:
  Achievements — earned automatically by hitting count thresholds ("ladders").
                 Each tier also grants points (per-ladder escalation: 5,7,9,...).
  Flair        — cosmetic titles bought with points.

This module is pure-ish: the catalog is data, and the metric/sync functions take
a user_id and use the models. Import models lazily inside functions to avoid any
import cycle (mutation modules import this, and this touches their models).

Single source of truth — the app fetches the catalog from /achievements/catalog
rather than hardcoding it.
"""

import json


def _tiers(*pairs):
    """pairs: (count, name). Points escalate per tier: 5, 7, 9, ..."""
    return [
        {"tier": i + 1, "count": c, "name": n, "points": 5 + 2 * i}
        for i, (c, n) in enumerate(pairs)
    ]


# ladder key -> metric name is the same string; `blocked` hides until that media
# type ships, but the metric still computes harmlessly (count stays 0).
LADDERS = [
    {
        "key": "screening_room", "name": "Screening Room", "motif": "reel",
        "metric": "watched", "blocked": False,
        "tiers": _tiers((5, "First Showing"), (25, "Double Feature"),
                        (50, "Marathoner"), (100, "Reel Devotee"),
                        (200, "Silver Screener"), (350, "Projectionist")),
    },
    {
        "key": "the_stack", "name": "The Stack", "motif": "vhs",
        "metric": "added", "blocked": False,
        "tiers": _tiers((10, "Shelf Starter"), (25, "Stack Builder"),
                        (50, "Shelf Stacker"), (100, "Tower Keeper")),
    },
    {
        "key": "word_of_mouth", "name": "Word of Mouth", "motif": "megaphone",
        "metric": "shares", "blocked": False,
        "tiers": _tiers((5, "Tipster"), (20, "Tape Passer"), (50, "Connector"),
                        (100, "Tastemaker"), (150, "Hype Engine"),
                        (200, "The Oracle")),
    },
    {
        "key": "box_set", "name": "The Box Set", "motif": "boxset",
        "metric": "seasons", "blocked": False,
        "tiers": _tiers((5, "Pilot Light"), (15, "Box Set Opener"),
                        (30, "Season Sweeper"), (60, "Binge Master"),
                        (100, "Series Finale")),
    },
    {
        "key": "movie_night", "name": "Movie Night", "motif": "popcorn",
        "metric": "movie_nights", "blocked": False,
        "tiers": _tiers((1, "First Invite"), (4, "Regular"), (8, "Snack Captain"),
                        (16, "Night Owl"), (32, "Couch Commander"),
                        (52, "Host of the Year")),
    },
    {
        "key": "the_arena", "name": "The Arena", "motif": "crossed_reels",
        "metric": "battles", "blocked": False,
        "tiers": _tiers((6, "Challenger"), (12, "Contender"), (18, "Brawler"),
                        (24, "Headliner"), (28, "Main Event"), (32, "Champion")),
    },
    {
        "key": "cued_in", "name": "Cued In", "motif": "clapper",
        "metric": "movie_of_week", "blocked": False,
        "tiers": _tiers((1, "Tuned In"), (4, "Subscriber"), (8, "Loyal"),
                        (16, "Devotee"), (32, "Ride or Die"),
                        (52, "Charter Member")),
    },
    {
        "key": "on_repeat", "name": "On Repeat", "motif": "cassette",
        "metric": "listened", "blocked": True,
        "tiers": _tiers((5, "First Spin"), (25, "B-Side"), (50, "Heavy Rotation"),
                        (100, "Mixtape Maker"), (200, "Crate Digger"),
                        (350, "Audiophile")),
    },
    {
        "key": "reading_room", "name": "The Reading Room", "motif": "book",
        "metric": "books", "blocked": True,
        "tiers": _tiers((5, "First Chapter"), (25, "Bookmarked"),
                        (50, "Page Turner"), (100, "Shelf Reader"),
                        (200, "Bookworm"), (350, "Well-Read")),
    },
]

LADDER_BY_KEY = {l["key"]: l for l in LADDERS}


def _flair(category, price, *names):
    return [
        {"key": n.lower().replace(" ", "_"), "name": n,
         "category": category, "price": price}
        for n in names
    ]


FLAIR = (
    _flair("Film & TV", 10, "Production Assistant", "Stunt Performer",
           "Hair Stylist", "Makeup Artist", "Animator", "Voice Actor")
    + _flair("Film & TV", 25, "Costume Designer", "Casting Director",
             "Art Director", "Sound Designer", "VFX Artist", "Film Editor",
             "Music Supervisor", "Stunt Coordinator")
    + _flair("Film & TV", 50, "Cinematographer", "Production Designer",
             "Screenwriter", "Composer", "Actor", "Actress")
    + _flair("Film & TV", 100, "Director", "Producer", "Executive Producer",
             "Showrunner")
    + _flair("Music", 10, "Musician", "Band", "DJ")
    + _flair("Music", 25, "Singer", "Songwriter", "Recording Engineer",
             "Mixing Engineer", "Mastering Engineer")
    + _flair("Music", 50, "Music Producer", "Score Composer")
    + _flair("Music", 100, "Conductor")
    + _flair("Books", 10, "Proofreader", "Illustrator", "Cover Designer",
             "Narrator")
    + _flair("Books", 25, "Ghostwriter", "Book Editor", "Journalist", "Poet")
    + _flair("Books", 50, "Author", "Novelist", "Literary Agent")
    + _flair("Books", 100, "Publisher")
)

FLAIR_BY_KEY = {f["key"]: f for f in FLAIR}


# ---------------------------------------------------------------------------
# Metrics — how many of each thing the user has done.
# ---------------------------------------------------------------------------

def compute_metrics(user_id):
    from models import (
        WatchlistItem, Recommendation, ReviewShare,
        MovieNightParticipant, BattleVote, MovieOfWeekCompletion,
    )

    items = WatchlistItem.query.filter_by(user_id=user_id).all()

    watched_movie_tv = sum(
        1 for it in items
        if it.watch_status == "watched" and it.media_type in ("movie", "tv")
    )
    listened = sum(
        1 for it in items
        if it.watch_status == "watched" and it.media_type == "song"
    )
    books = sum(
        1 for it in items
        if it.watch_status == "watched" and it.media_type == "book"
    )
    added = len(items)

    seasons = 0
    for it in items:
        if it.seasons_watched:
            try:
                v = json.loads(it.seasons_watched)
                if isinstance(v, list):
                    seasons += len(v)
            except (ValueError, TypeError):
                pass

    shares = (
        Recommendation.query.filter_by(from_user_id=user_id).count()
        + ReviewShare.query.filter_by(from_user_id=user_id).count()
    )
    movie_nights = MovieNightParticipant.query.filter_by(user_id=user_id).count()
    battles = (
        BattleVote.query.filter_by(user_id=user_id)
        .distinct(BattleVote.battle_id).count()
    )
    movie_of_week = MovieOfWeekCompletion.query.filter_by(user_id=user_id).count()

    return {
        "watched": watched_movie_tv,
        "added": added,
        "shares": shares,
        "seasons": seasons,
        "movie_nights": movie_nights,
        "battles": battles,
        "movie_of_week": movie_of_week,
        "listened": listened,
        "books": books,
    }


# ---------------------------------------------------------------------------
# Awarding — grant any newly-earned tiers + their points. Idempotent.
# ---------------------------------------------------------------------------

def sync_achievements(user_id):
    """Grant every tier the user now qualifies for but hasn't earned yet.
    Returns the list of newly-earned {ladder_key, tier, name, points}."""
    from models import db, User, UserAchievement

    user = User.query.get(user_id)
    if not user:
        return []

    metrics = compute_metrics(user_id)
    already = {
        (ua.ladder_key, ua.tier)
        for ua in UserAchievement.query.filter_by(user_id=user_id).all()
    }

    newly = []
    for ladder in LADDERS:
        if ladder["blocked"]:
            continue
        count = metrics.get(ladder["metric"], 0)
        for t in ladder["tiers"]:
            if count >= t["count"] and (ladder["key"], t["tier"]) not in already:
                db.session.add(UserAchievement(
                    user_id=user_id, ladder_key=ladder["key"], tier=t["tier"],
                ))
                user.points = (user.points or 0) + t["points"]
                newly.append({
                    "ladder_key": ladder["key"], "tier": t["tier"],
                    "name": t["name"], "points": t["points"],
                })

    if newly:
        db.session.commit()
    return newly


def award_points(user_id, amount):
    """Direct point grant for bounded events (Movie of the Week / battle rating)."""
    from models import db, User
    user = User.query.get(user_id)
    if not user:
        return
    user.points = (user.points or 0) + amount
    db.session.commit()


def catalog_dict():
    """Static catalog for the app to render."""
    return {"ladders": LADDERS, "flair": FLAIR}
