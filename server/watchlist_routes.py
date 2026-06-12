import json
import re
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, WatchlistItem, User


# OMDb returns release dates in formats like:
#   "16 Aug 2024", "Aug 16, 2024", "2024-08-16", "2024"
# Try a handful of patterns; if nothing matches, return None and the item is
# treated as already-released (no Coming Soon badge).
_RELEASE_FORMATS = (
    "%d %b %Y",   # 16 Aug 2024
    "%b %d, %Y",  # Aug 16, 2024
    "%Y-%m-%d",   # 2024-08-16
    "%d %B %Y",   # 16 August 2024
    "%B %d, %Y",  # August 16, 2027
)


def _parse_release_date(released_str):
    """Parse an OMDb-style release date string into a date object, or None."""
    if not released_str or not isinstance(released_str, str):
        return None
    s = released_str.strip()
    for fmt in _RELEASE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Year-only fallback: treat as Jan 1 of that year. This won't be marked
    # coming-soon unless the year is in the future.
    if re.fullmatch(r"\d{4}", s):
        return date(int(s), 1, 1)
    return None


def _parse_runtime(value):
    """Accepts int, str like '148 min', '1h 48m', or None. Returns int minutes or None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        # Try plain integer first
        digits = re.findall(r"\d+", value)
        if not digits:
            return None
        if "h" in value.lower():
            # Format like "1h 48m" or "2h"
            hours = int(digits[0])
            minutes = int(digits[1]) if len(digits) > 1 else 0
            total = hours * 60 + minutes
            return total if total > 0 else None
        # "148 min" or "148"
        return int(digits[0]) if int(digits[0]) > 0 else None
    return None


watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")


ALLOWED_MEDIA_TYPES = {"movie", "tv", "song", "book"}


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _parse_seasons(raw):
    """seasons_watched is stored as a JSON string; return as a list of ints (or [])."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [int(s) for s in value if isinstance(s, (int, str)) and str(s).isdigit()]
    except (ValueError, TypeError):
        pass
    return []


def _serialize_seasons(value):
    """Accept a list of ints (or strings castable to int) and return JSON string."""
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    cleaned = sorted({int(s) for s in value if str(s).isdigit()})
    return json.dumps(cleaned)


def item_to_dict(item, recommenders=None):
    recommended_by = None
    if item.recommended_by_user_id:
        if recommenders and item.recommended_by_user_id in recommenders:
            recommended_by = _user_summary(recommenders[item.recommended_by_user_id])
        else:
            recommended_by = _user_summary(
                User.query.get(item.recommended_by_user_id)
            )

    release_date = _parse_release_date(item.released)
    coming_soon = bool(release_date and release_date > date.today())

    return {
        "id": item.id,
        "title": item.title,
        "year": item.year,
        "imdb_id": item.imdb_id,
        "movie_type": item.movie_type,
        "media_type": item.media_type,
        "plot": item.plot,
        "poster": item.poster,
        "genre": item.genre,
        "director": item.director,
        "actors": item.actors,
        "imdb_rating": item.imdb_rating,
        "rated": item.rated,
        "released": item.released,
        "release_date_iso": release_date.isoformat() if release_date else None,
        "coming_soon": coming_soon,
        "runtime_minutes": item.runtime_minutes,
        "seasons_watched": _parse_seasons(item.seasons_watched),
        "chapter_progress": item.chapter_progress,
        "watch_status": item.watch_status,
        "rating": item.rating,
        "notes": item.notes,
        "recommended_by_user_id": item.recommended_by_user_id,
        "recommended_by": recommended_by,
    }


@watchlist_bp.route("/", methods=["GET"])
@jwt_required()
def get_watchlist():
    user_id = int(get_jwt_identity())
    media_type = request.args.get("media_type")

    query = WatchlistItem.query.filter_by(user_id=user_id)
    if media_type:
        if media_type not in ALLOWED_MEDIA_TYPES:
            return jsonify({"message": f"Invalid media_type: {media_type}"}), 400
        query = query.filter_by(media_type=media_type)

    items = query.all()

    # Batch-lookup recommenders so we don't N+1 query when serializing
    recommender_ids = {
        item.recommended_by_user_id for item in items if item.recommended_by_user_id
    }
    recommenders = {}
    if recommender_ids:
        for u in User.query.filter(User.id.in_(recommender_ids)).all():
            recommenders[u.id] = u

    return jsonify([item_to_dict(item, recommenders) for item in items]), 200


@watchlist_bp.route("/", methods=["POST"])
@jwt_required()
def add_to_watchlist():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    imdb_id = data.get("imdb_id")
    if not imdb_id:
        return jsonify({"message": "imdb_id is required"}), 400

    # title is NOT NULL in the schema; without this check a missing title
    # surfaces as an IntegrityError 500 instead of a clean 400.
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"message": "title is required"}), 400

    media_type = data.get("media_type", "movie")
    if media_type not in ALLOWED_MEDIA_TYPES:
        return jsonify({"message": f"Invalid media_type: {media_type}"}), 400

    existing = WatchlistItem.query.filter_by(
        user_id=user_id, imdb_id=imdb_id, media_type=media_type
    ).first()
    if existing:
        return jsonify({"message": "Item already in your list"}), 400

    new_item = WatchlistItem(
        title=title,
        year=data.get("year"),
        imdb_id=imdb_id,
        movie_type=data.get("movie_type"),
        media_type=media_type,
        plot=data.get("plot"),
        poster=data.get("poster"),
        genre=data.get("genre"),
        director=data.get("director"),
        actors=data.get("actors"),
        imdb_rating=data.get("imdb_rating"),
        rated=data.get("rated"),
        released=data.get("released"),
        runtime_minutes=_parse_runtime(
            data.get("runtime_minutes") or data.get("runtime")
        ),
        watch_status=data.get("watch_status", "want_to_watch"),
        rating=data.get("rating"),
        notes=data.get("notes"),
        user_id=user_id,
    )
    db.session.add(new_item)
    db.session.commit()

    return jsonify(item_to_dict(new_item)), 201


@watchlist_bp.route("/<int:item_id>", methods=["PATCH"])
@jwt_required()
def update_watchlist_item(item_id):
    user_id = int(get_jwt_identity())
    item = WatchlistItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return jsonify({"message": "Watchlist item not found"}), 404

    data = request.get_json(silent=True) or {}
    # User-editable fields
    item.watch_status = data.get("watch_status", item.watch_status)
    item.rating = data.get("rating", item.rating)
    item.notes = data.get("notes", item.notes)
    if "seasons_watched" in data:
        item.seasons_watched = _serialize_seasons(data.get("seasons_watched"))
    if "chapter_progress" in data:
        raw = data.get("chapter_progress")
        if raw is None:
            item.chapter_progress = None
        else:
            try:
                progress = int(raw)
                if progress >= 0:
                    item.chapter_progress = progress
            except (TypeError, ValueError):
                pass  # ignore garbage; keep existing progress
    # Metadata fields (used for auto-backfill from DetailScreen)
    item.plot = data.get("plot", item.plot)
    item.genre = data.get("genre", item.genre)
    item.director = data.get("director", item.director)
    item.actors = data.get("actors", item.actors)
    item.imdb_rating = data.get("imdb_rating", item.imdb_rating)
    item.rated = data.get("rated", item.rated)
    item.released = data.get("released", item.released)
    if "runtime_minutes" in data or "runtime" in data:
        parsed = _parse_runtime(
            data.get("runtime_minutes") or data.get("runtime")
        )
        if parsed is not None:
            item.runtime_minutes = parsed
    db.session.commit()

    return jsonify(item_to_dict(item)), 200


@watchlist_bp.route("/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_watchlist_item(item_id):
    user_id = int(get_jwt_identity())
    item = WatchlistItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return jsonify({"message": "Watchlist item not found"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Watchlist item deleted"}), 200
