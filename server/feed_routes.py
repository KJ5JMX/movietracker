"""
Discovery feed endpoint.

The feed is a curated, transparent surface — never an opaque algorithm. Every
item has a clear `reason` field so the UI can show "Sarah added this" rather
than "Recommended for you." Sections are derived from friend activity and the
user's stated genre preferences; nothing is collaboratively-filtered or scored.

This is a Pro-gated feature: free users get a 402 with code `pro_required` and
the frontend swaps in the Upgrade modal. Comped testers (pro_status='comp')
see it like any other Pro user.

Endpoints:
  GET /feed   Returns { sections: [{ id, title, subtitle, items: [...] }, ...] }
"""

import json
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from models import User, Friendship, WatchlistItem


feed_bp = Blueprint("feed", __name__, url_prefix="/feed")

# How many items to show per section. Tight on purpose — the feed should feel
# editorially curated, not infinite-scroll.
SECTION_LIMIT = 8

# How recent counts as "recent" for friend additions. We use WatchlistItem.id
# as a proxy for created_at (no timestamp column exists today) — for a given
# friend, the highest id is the most recently added.
RECENT_PER_FRIEND = 10


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _parse_genres(raw):
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [g for g in v if isinstance(g, str)]
    except (ValueError, TypeError):
        pass
    return []


def _friend_ids(me_id):
    rows = Friendship.query.filter(
        or_(Friendship.requester_id == me_id, Friendship.addressee_id == me_id),
        Friendship.status == "accepted",
    ).all()
    ids = set()
    for f in rows:
        other = f.addressee_id if f.requester_id == me_id else f.requester_id
        ids.add(other)
    if not ids:
        return ids
    # Honor privacy_mode: friends who set "private" opted out of having their
    # list surfaced in discovery feeds. ("public" and "friends" behave the
    # same today — there is no public, non-friend surface yet. Movie Night is
    # unaffected: joining a session is an explicit opt-in.)
    private_ids = {
        u.id
        for u in User.query.with_entities(User.id)
        .filter(User.id.in_(ids), User.privacy_mode == "private")
        .all()
    }
    return ids - private_ids


def _my_imdb_ids(me_id):
    """Return set of (imdb_id, media_type) tuples I already have, so feed can dedupe."""
    rows = WatchlistItem.query.with_entities(
        WatchlistItem.imdb_id, WatchlistItem.media_type
    ).filter(WatchlistItem.user_id == me_id).all()
    return {(r.imdb_id, r.media_type) for r in rows}


def _item_to_feed_dict(item, reason, reason_user=None):
    """Lightweight feed-item dict. Mirrors WatchlistItem serializer's main fields
    but adds the `reason` line that drives the cozy, transparent feed copy."""
    return {
        "imdb_id": item.imdb_id,
        "title": item.title,
        "year": item.year,
        "poster": item.poster,
        "media_type": item.media_type,
        "movie_type": item.movie_type,
        "genre": item.genre,
        "rating": item.rating,
        "runtime_minutes": item.runtime_minutes,
        "released": item.released,
        # Snapshot fields that AddItemScreen needs if user taps "Add to my list"
        "plot": item.plot,
        "director": item.director,
        "actors": item.actors,
        "imdb_rating": item.imdb_rating,
        "rated": item.rated,
        # Discovery-specific
        "reason": reason,
        "reason_user": _user_summary(reason_user),
    }


def _genre_match(item_genre, user_genres):
    """Case-insensitive substring match — OMDb returns multi-genre strings
    like "Action, Adventure, Sci-Fi" so we look for any user genre inside."""
    if not user_genres or not item_genre:
        return False
    g_lower = item_genre.lower()
    return any(ug.lower() in g_lower for ug in user_genres)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_friend_activity(me_id, friend_ids, owned):
    """Recent additions by friends (any want_to_watch item I don't have).
    Most recently added across all friends, deduped by imdb_id+media_type."""
    if not friend_ids:
        return []
    # Pull recent items from all friends, ordered by id desc (proxy for recency)
    items = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .filter(WatchlistItem.watch_status == "want_to_watch")
        .order_by(WatchlistItem.id.desc())
        .limit(SECTION_LIMIT * 4)  # over-fetch so we have room after dedupe
        .all()
    )
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    seen = set()
    out = []
    for it in items:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in seen:
            continue
        seen.add(key)
        adder = users_by_id.get(it.user_id)
        adder_name = (adder.display_name or adder.username) if adder else "A friend"
        out.append(_item_to_feed_dict(it, f"{adder_name} added this", adder))
        if len(out) >= SECTION_LIMIT:
            break
    return out


def _section_coming_soon(me_id, friend_ids, owned, user_genres):
    """Upcoming items (release date in future) from friends, optionally filtered
    by my genres. If I have no genre prefs, no filter — show all upcoming friend picks."""
    from datetime import date
    from watchlist_routes import _parse_release_date

    if not friend_ids:
        return []

    # Pull all friend items with a released field; filter coming_soon in Python
    # (parsing the OMDb date string isn't something SQLite can do cleanly).
    candidates = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .filter(WatchlistItem.released.isnot(None))
        .all()
    )

    today = date.today()
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    seen = set()
    out = []
    # Sort by parsed release date ascending (soonest first)
    parsed = []
    for it in candidates:
        rd = _parse_release_date(it.released)
        if not rd or rd <= today:
            continue
        parsed.append((rd, it))
    parsed.sort(key=lambda x: x[0])

    for rd, it in parsed:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in seen:
            continue
        if user_genres and not _genre_match(it.genre, user_genres):
            continue
        seen.add(key)
        adder = users_by_id.get(it.user_id)
        adder_name = (adder.display_name or adder.username) if adder else "A friend"
        reason = (
            f"{adder_name} is waiting for this"
            if not user_genres
            else f"In your genres · {adder_name} is waiting for this"
        )
        out.append(_item_to_feed_dict(it, reason, adder))
        if len(out) >= SECTION_LIMIT:
            break
    return out


def _section_friend_loves(me_id, friend_ids, owned):
    """Items friends rated 4+ stars. Strong personal endorsement."""
    if not friend_ids:
        return []
    items = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .filter(WatchlistItem.rating.isnot(None))
        .filter(WatchlistItem.rating >= 4)
        .order_by(WatchlistItem.id.desc())
        .limit(SECTION_LIMIT * 4)
        .all()
    )
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    seen = set()
    out = []
    for it in items:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in seen:
            continue
        seen.add(key)
        rater = users_by_id.get(it.user_id)
        rater_name = (rater.display_name or rater.username) if rater else "A friend"
        stars = "★" * (it.rating or 0)
        out.append(_item_to_feed_dict(
            it, f"{rater_name} rated this {stars}", rater
        ))
        if len(out) >= SECTION_LIMIT:
            break
    return out


def _section_other_shelves(me_id, friend_ids, owned):
    """Cross-media discovery: songs and books friends have added."""
    if not friend_ids:
        return []
    items = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .filter(WatchlistItem.media_type.in_(["song", "book"]))
        .order_by(WatchlistItem.id.desc())
        .limit(SECTION_LIMIT * 4)
        .all()
    )
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    seen = set()
    out = []
    for it in items:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in seen:
            continue
        seen.add(key)
        adder = users_by_id.get(it.user_id)
        adder_name = (adder.display_name or adder.username) if adder else "A friend"
        kind = "book" if it.media_type == "book" else "song"
        out.append(_item_to_feed_dict(
            it, f"{adder_name} added this {kind}", adder
        ))
        if len(out) >= SECTION_LIMIT:
            break
    return out


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@feed_bp.route("/", methods=["GET"])
@jwt_required()
def get_feed():
    me_id = int(get_jwt_identity())
    me = User.query.get(me_id)
    if not me:
        return jsonify({"message": "User not found"}), 404

    # Pro-gated. Free users get a clean 402 so the frontend can swap in
    # the Upgrade pitch instead of an error state.
    if not me.is_pro:
        return jsonify({
            "message": "Discovery feed is a Pro feature",
            "code": "pro_required",
        }), 402

    friend_ids = _friend_ids(me_id)
    owned = _my_imdb_ids(me_id)
    user_genres = _parse_genres(me.genres)

    sections = [
        {
            "id": "friend_activity",
            "title": "ON YOUR FRIENDS' LISTS",
            "subtitle": "What they've added recently",
            "items": _section_friend_activity(me_id, friend_ids, owned),
        },
        {
            "id": "coming_soon",
            "title": (
                "COMING SOON IN YOUR GENRES"
                if user_genres else "COMING SOON FROM FRIENDS"
            ),
            "subtitle": (
                "Upcoming picks that match your taste"
                if user_genres
                else "Upcoming picks from friends' lists"
            ),
            "items": _section_coming_soon(me_id, friend_ids, owned, user_genres),
        },
        {
            "id": "friend_loves",
            "title": "WHAT FRIENDS ARE LOVING",
            "subtitle": "Highly rated by people you know",
            "items": _section_friend_loves(me_id, friend_ids, owned),
        },
        {
            "id": "other_shelves",
            "title": "ALSO ON THEIR SHELVES",
            "subtitle": "Books and music your friends are picking up",
            "items": _section_other_shelves(me_id, friend_ids, owned),
        },
    ]

    return jsonify({
        "sections": sections,
        "has_friends": len(friend_ids) > 0,
        "has_genres": len(user_genres) > 0,
    }), 200
