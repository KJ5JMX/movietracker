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
from datetime import datetime
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from models import User, Friendship, WatchlistItem


feed_bp = Blueprint("feed", __name__, url_prefix="/feed")

# One chronological stream of friend activity, with genre suggestions sprinkled
# in. Tuned to feel like a feed you scroll, not five cramped shelves.
ACTIVITY_LIMIT = 40        # most-recent friend events to surface
SUGGESTION_EVERY = 9       # drop a genre suggestion every N activity items


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


def _item_to_feed_dict(item, reason, reason_user=None, kind="activity"):
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
        "kind": kind,  # "activity" | "suggestion"
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _genre_match(item_genre, user_genres):
    """Case-insensitive substring match — OMDb returns multi-genre strings
    like "Action, Adventure, Sci-Fi" so we look for any user genre inside."""
    if not user_genres or not item_genre:
        return False
    g_lower = item_genre.lower()
    return any(ug.lower() in g_lower for ug in user_genres)


# ---------------------------------------------------------------------------
# Feed builders
# ---------------------------------------------------------------------------

def _event_reason(it, users_by_id):
    """The single 'who did what' line for one friend's item, picking the
    strongest signal: a high rating, then active reading, else a plain add."""
    user = users_by_id.get(it.user_id)
    name = (user.display_name or user.username) if user else "A friend"
    if it.rating and it.rating >= 4:
        return f"{name} rated this " + "★" * int(it.rating), user
    if it.media_type == "book" and it.watch_status == "reading":
        chapter = f" · ch {it.chapter_progress}" if it.chapter_progress else ""
        return f"{name} is reading this{chapter}", user
    return f"{name} added this", user


def _sort_key(it):
    """Newest first by created_at, with id as a stable fallback (and so rows
    that predate created_at sort to the bottom rather than crash)."""
    return (it.created_at or datetime.min, it.id)


def _build_activity(friend_ids, owned):
    """One merged, most-recent-first stream of friend activity: things they
    added, are reading, or rated highly. Deduped, excludes what I already own."""
    if not friend_ids:
        return []
    items = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .filter(
            or_(
                WatchlistItem.watch_status.in_(["want_to_watch", "reading"]),
                WatchlistItem.rating >= 4,
            )
        )
        .all()
    )
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    items.sort(key=_sort_key, reverse=True)
    seen = set()
    out = []
    for it in items:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in seen:
            continue
        seen.add(key)
        reason, user = _event_reason(it, users_by_id)
        out.append(_item_to_feed_dict(it, reason, user, kind="activity"))
        if len(out) >= ACTIVITY_LIMIT:
            break
    return out, seen


def _build_suggestions(friend_ids, owned, user_genres, exclude):
    """Genre-matched picks from friends' want-to-watch lists, to sprinkle into
    the stream. Empty if the user picked no genres."""
    if not friend_ids or not user_genres:
        return []
    # Any genre-matched item on a friend's shelf that the activity stream
    # didn't already surface. Drawn from all statuses so suggestions still
    # appear even when recent activity already covers the want-to-watch items.
    candidates = (
        WatchlistItem.query
        .filter(WatchlistItem.user_id.in_(friend_ids))
        .order_by(WatchlistItem.id.desc())
        .all()
    )
    users_by_id = {
        u.id: u for u in User.query.filter(User.id.in_(friend_ids)).all()
    }
    seen = set()
    out = []
    for it in candidates:
        key = (it.imdb_id, it.media_type)
        if key in owned or key in exclude or key in seen:
            continue
        if not _genre_match(it.genre, user_genres):
            continue
        seen.add(key)
        out.append(_item_to_feed_dict(
            it, "In your genres", users_by_id.get(it.user_id), kind="suggestion"
        ))
    return out


def _interleave(activity, suggestions, every):
    """Drop one suggestion after every `every` activity items."""
    out = []
    si = 0
    for i, a in enumerate(activity):
        out.append(a)
        if (i + 1) % every == 0 and si < len(suggestions):
            out.append(suggestions[si])
            si += 1
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

    if friend_ids:
        activity, shown_keys = _build_activity(friend_ids, owned)
    else:
        activity, shown_keys = [], set()
    suggestions = _build_suggestions(friend_ids, owned, user_genres, shown_keys)
    items = _interleave(activity, suggestions, SUGGESTION_EVERY)

    return jsonify({
        "items": items,
        "has_friends": len(friend_ids) > 0,
        "has_genres": len(user_genres) > 0,
    }), 200
