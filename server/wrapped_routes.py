"""That's a Wrap — the yearly recap.

GET /wrapped/<year> aggregates everything the app already records into the
stats the recap screen renders as slides. Items watched before the
watched_at column existed have unknown dates and simply don't count, which
is fine: the app is younger than the column.
"""

from collections import Counter
from datetime import datetime

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import (
    User,
    WatchlistItem,
    MovieNightSession,
    MovieNightParticipant,
    Recommendation,
)

wrapped_bp = Blueprint("wrapped", __name__, url_prefix="/wrapped")


def _year_bounds(year):
    return datetime(year, 1, 1), datetime(year + 1, 1, 1)


def _decade_label(year_str):
    try:
        y = int(str(year_str)[:4])
    except (TypeError, ValueError):
        return None
    return f"{(y // 10) * 10}s"


@wrapped_bp.route("/<int:year>", methods=["GET"])
@jwt_required()
def wrapped(year):
    me_id = int(get_jwt_identity())
    start, end = _year_bounds(year)

    watched = WatchlistItem.query.filter(
        WatchlistItem.user_id == me_id,
        WatchlistItem.watched_at >= start,
        WatchlistItem.watched_at < end,
    ).all()
    added_count = WatchlistItem.query.filter(
        WatchlistItem.user_id == me_id,
        WatchlistItem.created_at >= start,
        WatchlistItem.created_at < end,
    ).count()

    by_type = Counter(it.media_type for it in watched)

    genres = Counter()
    for it in watched:
        for g in (it.genre or "").split(","):
            g = g.strip()
            if g:
                genres[g] += 1

    decades = Counter()
    for it in watched:
        label = _decade_label(it.year)
        if label:
            decades[label] += 1

    ratings = [it.rating for it in watched if it.rating]
    minutes = sum(
        it.runtime_minutes or 0
        for it in watched
        if it.media_type in ("movie", "tv")
    )

    # Movie nights I took part in this year (anything that actually happened)
    my_session_ids = [
        p.session_id
        for p in MovieNightParticipant.query.filter_by(user_id=me_id).all()
    ]
    nights = []
    if my_session_ids:
        nights = MovieNightSession.query.filter(
            MovieNightSession.id.in_(my_session_ids),
            MovieNightSession.status.in_(["active", "ended"]),
            MovieNightSession.created_at >= start,
            MovieNightSession.created_at < end,
        ).all()

    # Top co-watcher: who shared the most of those nights with me
    co_counter = Counter()
    if nights:
        night_ids = [n.id for n in nights]
        for p in MovieNightParticipant.query.filter(
            MovieNightParticipant.session_id.in_(night_ids)
        ).all():
            if p.user_id != me_id:
                co_counter[p.user_id] += 1
    top_co = None
    if co_counter:
        top_id, top_count = co_counter.most_common(1)[0]
        u = User.query.get(top_id)
        if u:
            top_co = {
                "name": u.display_name or u.username,
                "nights": top_count,
            }

    recs_sent = Recommendation.query.filter(
        Recommendation.from_user_id == me_id,
        Recommendation.created_at >= start,
        Recommendation.created_at < end,
    ).count()
    recs_hits = Recommendation.query.filter(
        Recommendation.from_user_id == me_id,
        Recommendation.created_at >= start,
        Recommendation.created_at < end,
        Recommendation.status == "accepted",
    ).count()

    five_stars = [it.title for it in watched if it.rating == 5][:5]

    return jsonify({
        "year": year,
        "watched_total": len(watched),
        "watched_by_type": {
            "movie": by_type.get("movie", 0),
            "tv": by_type.get("tv", 0),
            "book": by_type.get("book", 0),
            "song": by_type.get("song", 0),
        },
        "added_total": added_count,
        "minutes_watched": minutes,
        "top_genres": [
            {"genre": g, "count": n} for g, n in genres.most_common(3)
        ],
        "top_decade": (
            {"decade": decades.most_common(1)[0][0],
             "count": decades.most_common(1)[0][1]}
            if decades else None
        ),
        "avg_rating": (
            round(sum(ratings) / len(ratings), 1) if ratings else None
        ),
        "five_star_titles": five_stars,
        "movie_nights": len(nights),
        "top_co_watcher": top_co,
        "recs_sent": recs_sent,
        "recs_added_by_friends": recs_hits,
    }), 200
