"""ShelfMates Movie Fest — Movie of the Week + monthly Battles.

Two blueprints:
  festival_bp (/festival)  public, JWT-protected, used by the app
  admin_bp    (/admin)     admin-only, used by the curation web page

Admin auth: Cloudflare Access guards /admin at the edge and injects the
authenticated user's email in `Cf-Access-Authenticated-User-Email`. We re-check
that header against Config.ADMIN_EMAILS so a misconfigured tunnel can't expose
the panel. X-Admin-Token is a local-only fallback for direct curl on the box.

Curation is hand-set, so it works with zero users. The curated `streaming`
field (JSON list of platform values) is the authoritative where-to-watch for
festival titles — the admin verifies it before pushing, so we never surface a
pick nobody can stream.
"""

import json
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from config import Config
import streaming_lookup
from models import (
    db,
    User,
    WatchlistItem,
    MovieOfWeek,
    MovieOfWeekCompletion,
    Battle,
    BattleVote,
    StreamingAvailabilityReport,
    Recommendation,
    MovieNightSession,
    MovieNightParticipant,
    ActivityLike,
)
from movie_routes import _omdb_search_forgiving
from streaming_routes import ALLOWED_PLATFORMS
from achievements import award_points, sync_and_notify

# Points granted for the bounded, cheat-proof events (once each).
MOW_RATING_POINTS = 2
BATTLE_RATING_POINTS = 2

festival_bp = Blueprint("festival", __name__, url_prefix="/festival")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _current_week_key():
    # ISO week, e.g. "2026-W26". %G/%V are the ISO year + ISO week number.
    return datetime.utcnow().strftime("%G-W%V")


def _clean_platforms(raw):
    """Keep only known platform values, lowercased, de-duped, order preserved."""
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        v = (str(p) if p is not None else "").strip().lower()
        if v in ALLOWED_PLATFORMS and v not in out:
            out.append(v)
    return out


def _load_platforms(stored):
    if not stored:
        return []
    try:
        v = json.loads(stored)
        return _clean_platforms(v)
    except (ValueError, TypeError):
        return []


def _mow_to_dict(mow, completion=None):
    return {
        "id": mow.id,
        "week_key": mow.week_key,
        "imdb_id": mow.imdb_id,
        "title": mow.title,
        "year": mow.year,
        "poster": mow.poster,
        "media_type": mow.media_type,
        "blurb": mow.blurb,
        "streaming": _load_platforms(mow.streaming),
        "active": bool(mow.active),
        "completed": completion is not None,
        "my_rating": completion.rating if completion else None,
        "my_review": completion.review if completion else None,
    }


def _battle_to_dict(battle, my_choice=None, counts=None):
    counts = counts or {"a": 0, "b": 0}
    now = datetime.utcnow()
    return {
        "id": battle.id,
        "title": battle.title,
        "movie_a": {
            "imdb_id": battle.a_imdb_id,
            "title": battle.a_title,
            "year": battle.a_year,
            "poster": battle.a_poster,
            "streaming": _load_platforms(battle.a_streaming),
            "votes": counts.get("a", 0),
        },
        "movie_b": {
            "imdb_id": battle.b_imdb_id,
            "title": battle.b_title,
            "year": battle.b_year,
            "poster": battle.b_poster,
            "streaming": _load_platforms(battle.b_streaming),
            "votes": counts.get("b", 0),
        },
        "ends_at": battle.ends_at.isoformat() + "Z",
        "closed": now > battle.ends_at,
        "active": bool(battle.active),
        "my_choice": my_choice,
    }


def _seed_streaming_reports(imdb_id, platforms, country="US"):
    """Mirror admin-curated streaming into the crowdsourced where-to-watch table
    so the title's detail screen surfaces it too. Upserts + refreshes freshness."""
    if not imdb_id or not platforms:
        return
    for p in platforms:
        existing = StreamingAvailabilityReport.query.filter_by(
            imdb_id=imdb_id, country=country, platform=p
        ).first()
        if existing:
            existing.active = True
            existing.last_confirmed_at = datetime.utcnow()
        else:
            db.session.add(StreamingAvailabilityReport(
                imdb_id=imdb_id, country=country, platform=p,
                reported_by_user_id=None,
            ))
    db.session.commit()


def _vote_counts(battle_id):
    rows = (
        db.session.query(BattleVote.choice, db.func.count(BattleVote.id))
        .filter(BattleVote.battle_id == battle_id)
        .group_by(BattleVote.choice)
        .all()
    )
    counts = {"a": 0, "b": 0}
    for choice, n in rows:
        if choice in counts:
            counts[choice] = n
    return counts


# ===========================================================================
# Public endpoints (app)
# ===========================================================================

@festival_bp.route("/movie-of-week", methods=["GET"])
@jwt_required()
def get_movie_of_week():
    """The current active Movie of the Week + this user's completion state."""
    user_id = int(get_jwt_identity())
    mow = (
        MovieOfWeek.query.filter_by(active=True)
        .order_by(MovieOfWeek.week_key.desc())
        .first()
    )
    if not mow:
        return jsonify({"movie_of_week": None}), 200

    completion = MovieOfWeekCompletion.query.filter_by(
        mow_id=mow.id, user_id=user_id
    ).first()
    return jsonify({"movie_of_week": _mow_to_dict(mow, completion)}), 200


@festival_bp.route("/movie-of-week/complete", methods=["POST"])
@jwt_required()
def complete_movie_of_week():
    """Mark the current Movie of the Week complete for this user.

    Records the completion (sticky for the week) and creates/updates a watched
    WatchlistItem so the pick shows up in the user's library and discovery.
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    mow = (
        MovieOfWeek.query.filter_by(active=True)
        .order_by(MovieOfWeek.week_key.desc())
        .first()
    )
    if not mow:
        return jsonify({"message": "No active Movie of the Week"}), 404

    rating = data.get("rating")
    if rating is not None:
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                rating = None
        except (TypeError, ValueError):
            rating = None
    review = (data.get("review") or "").strip() or None

    completion = MovieOfWeekCompletion.query.filter_by(
        mow_id=mow.id, user_id=user_id
    ).first()
    first_completion = completion is None
    if completion:
        completion.rating = rating
        completion.review = review
        completion.completed_at = datetime.utcnow()
    else:
        completion = MovieOfWeekCompletion(
            mow_id=mow.id,
            user_id=user_id,
            rating=rating,
            review=review,
        )
        db.session.add(completion)

    # Mirror into the user's watchlist as watched so it surfaces in their
    # library + the discovery feed. Reuse an existing row if they already had it.
    item = WatchlistItem.query.filter_by(
        user_id=user_id, imdb_id=mow.imdb_id, media_type=mow.media_type
    ).first()
    if item:
        if item.watch_status != "watched":
            item.watch_status = "watched"
            if not item.watched_at:
                item.watched_at = datetime.utcnow()
        if rating is not None:
            item.rating = rating
        if review:
            item.notes = review
    else:
        item = WatchlistItem(
            title=mow.title,
            year=mow.year,
            imdb_id=mow.imdb_id,
            media_type=mow.media_type,
            movie_type="movie" if mow.media_type == "movie" else "series",
            poster=mow.poster,
            watch_status="watched",
            watched_at=datetime.utcnow(),
            rating=rating,
            notes=review,
            user_id=user_id,
        )
        db.session.add(item)

    db.session.commit()

    # Points only on the first completion (cheat-proof: bounded, once per pick).
    # Capture the balance before/after so the app can show exactly what this
    # watch earned, including any achievement tiers it happened to unlock.
    from models import User
    user = User.query.get(user_id)
    points_before = user.points or 0
    if first_completion:
        award_points(user_id, MOW_RATING_POINTS)
    newly = sync_and_notify(user_id) or []
    points_after = user.points or 0

    return jsonify({
        "movie_of_week": _mow_to_dict(mow, completion),
        "points_awarded": points_after - points_before,
        "total_points": points_after,
        "achievements_unlocked": newly,
    }), 200


@festival_bp.route("/battles", methods=["GET"])
@jwt_required()
def get_battles():
    """Active battles with vote counts and this user's vote."""
    user_id = int(get_jwt_identity())
    battles = (
        Battle.query.filter_by(active=True)
        .order_by(Battle.created_at.desc())
        .all()
    )
    if not battles:
        return jsonify({"battles": []}), 200

    my_votes = {
        v.battle_id: v.choice
        for v in BattleVote.query.filter(
            BattleVote.user_id == user_id,
            BattleVote.battle_id.in_([b.id for b in battles]),
        ).all()
    }
    out = [
        _battle_to_dict(b, my_votes.get(b.id), _vote_counts(b.id))
        for b in battles
    ]
    return jsonify({"battles": out}), 200


@festival_bp.route("/battles/<int:battle_id>/vote", methods=["POST"])
@jwt_required()
def vote_battle(battle_id):
    """Cast or change a vote ('a' or 'b'). Locked once the battle closes."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    choice = (data.get("choice") or "").strip().lower()
    if choice not in ("a", "b"):
        return jsonify({"message": "choice must be 'a' or 'b'"}), 400

    battle = Battle.query.get(battle_id)
    if not battle or not battle.active:
        return jsonify({"message": "Battle not found"}), 404
    if datetime.utcnow() > battle.ends_at:
        return jsonify({"message": "Voting has closed for this battle"}), 400

    vote = BattleVote.query.filter_by(
        battle_id=battle_id, user_id=user_id
    ).first()
    first_vote = vote is None
    if vote:
        vote.choice = choice
    else:
        vote = BattleVote(battle_id=battle_id, user_id=user_id, choice=choice)
        db.session.add(vote)
    db.session.commit()

    # Points only on the first vote per battle (changing your vote earns nothing).
    if first_vote:
        award_points(user_id, BATTLE_RATING_POINTS)
    sync_and_notify(user_id)

    return jsonify(
        _battle_to_dict(battle, choice, _vote_counts(battle_id))
    ), 200


# ===========================================================================
# Admin auth
# ===========================================================================

def require_admin(fn):
    """Gate an admin route. Trusts Cloudflare Access's injected email header,
    re-checked against ADMIN_EMAILS; falls back to X-Admin-Token for local use."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        email = (
            request.headers.get("Cf-Access-Authenticated-User-Email") or ""
        ).strip().lower()
        token = request.headers.get("X-Admin-Token")

        email_ok = bool(email) and email in Config.ADMIN_EMAILS
        token_ok = bool(Config.ADMIN_TOKEN) and token == Config.ADMIN_TOKEN

        if not (email_ok or token_ok):
            return jsonify({"message": "Admin access required"}), 403
        return fn(*args, **kwargs)

    return wrapper


# ===========================================================================
# Admin endpoints (curation web page)
# ===========================================================================

@admin_bp.route("/", methods=["GET"])
@require_admin
def admin_home():
    return Response(ADMIN_PAGE_HTML, mimetype="text/html")


@admin_bp.route("/api/search", methods=["GET"])
@require_admin
def admin_search():
    q = request.args.get("q", "")
    if not q.strip():
        return jsonify([]), 200
    return jsonify(_omdb_search_forgiving(q, None, "movie")), 200


@admin_bp.route("/api/streaming-health", methods=["GET"])
@require_admin
def admin_streaming_health():
    """Canary for the streaming provider — drives the status dot on the admin
    page. Runs a real lookup, so a green dot means the pipeline works end to end."""
    return jsonify(streaming_lookup.health_check()), 200


@admin_bp.route("/api/streaming-debug", methods=["GET"])
@require_admin
def admin_streaming_debug():
    """Raw JustWatch diagnostic. Open in the browser (Access-gated) to see what
    the provider actually returns before mapping. ?title= and ?country= optional."""
    title = request.args.get("title", "Back to the Future")
    country = request.args.get("country")
    return jsonify(streaming_lookup.debug(title, country)), 200


@admin_bp.route("/api/movie-of-week", methods=["GET"])
@require_admin
def admin_get_mow():
    mow = (
        MovieOfWeek.query.filter_by(active=True)
        .order_by(MovieOfWeek.week_key.desc())
        .first()
    )
    return jsonify({"movie_of_week": _mow_to_dict(mow) if mow else None}), 200


@admin_bp.route("/api/movie-of-week", methods=["POST"])
@require_admin
def admin_set_mow():
    """Create or replace the Movie of the Week for a week_key. Setting one
    deactivates any other active pick so the app only ever shows one."""
    data = request.get_json(silent=True) or {}
    imdb_id = (data.get("imdb_id") or "").strip()
    title = (data.get("title") or "").strip()
    if not imdb_id or not title:
        return jsonify({"message": "imdb_id and title are required"}), 400

    week_key = (data.get("week_key") or "").strip() or _current_week_key()
    platforms = _clean_platforms(data.get("streaming") or [])

    existing = MovieOfWeek.query.filter_by(week_key=week_key).first()
    # Deactivate every other pick.
    MovieOfWeek.query.filter(MovieOfWeek.week_key != week_key).update(
        {"active": False}
    )

    if existing:
        existing.imdb_id = imdb_id
        existing.title = title
        existing.year = data.get("year")
        existing.poster = data.get("poster")
        existing.media_type = data.get("media_type") or "movie"
        existing.blurb = (data.get("blurb") or "").strip() or None
        existing.streaming = json.dumps(platforms)
        existing.active = True
        mow = existing
    else:
        mow = MovieOfWeek(
            week_key=week_key,
            imdb_id=imdb_id,
            title=title,
            year=data.get("year"),
            poster=data.get("poster"),
            media_type=data.get("media_type") or "movie",
            blurb=(data.get("blurb") or "").strip() or None,
            streaming=json.dumps(platforms),
            active=True,
        )
        db.session.add(mow)

    db.session.commit()
    _seed_streaming_reports(imdb_id, platforms)
    return jsonify({"movie_of_week": _mow_to_dict(mow)}), 200


@admin_bp.route("/api/battles", methods=["GET"])
@require_admin
def admin_list_battles():
    battles = Battle.query.order_by(Battle.created_at.desc()).all()
    return jsonify(
        {"battles": [_battle_to_dict(b, None, _vote_counts(b.id)) for b in battles]}
    ), 200


@admin_bp.route("/api/battles", methods=["POST"])
@require_admin
def admin_create_battle():
    """Create a battle from two movies + a deadline (days from now)."""
    data = request.get_json(silent=True) or {}
    a = data.get("movie_a") or {}
    b = data.get("movie_b") or {}
    if not a.get("imdb_id") or not b.get("imdb_id"):
        return jsonify({"message": "Both movies are required"}), 400
    if a.get("imdb_id") == b.get("imdb_id"):
        return jsonify({"message": "Pick two different movies"}), 400

    try:
        days = int(data.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 90))
    from datetime import timedelta

    battle = Battle(
        title=(data.get("title") or "").strip() or "Movie Battle",
        a_imdb_id=a["imdb_id"],
        a_title=a.get("title") or "",
        a_year=a.get("year"),
        a_poster=a.get("poster"),
        a_streaming=json.dumps(_clean_platforms(a.get("streaming") or [])),
        b_imdb_id=b["imdb_id"],
        b_title=b.get("title") or "",
        b_year=b.get("year"),
        b_poster=b.get("poster"),
        b_streaming=json.dumps(_clean_platforms(b.get("streaming") or [])),
        ends_at=datetime.utcnow() + timedelta(days=days),
        active=True,
    )
    db.session.add(battle)
    db.session.commit()
    _seed_streaming_reports(battle.a_imdb_id, _load_platforms(battle.a_streaming))
    _seed_streaming_reports(battle.b_imdb_id, _load_platforms(battle.b_streaming))
    return jsonify(_battle_to_dict(battle, None, {"a": 0, "b": 0})), 201


@admin_bp.route("/api/battles/<int:battle_id>/update", methods=["POST"])
@require_admin
def admin_update_battle(battle_id):
    """Edit an existing battle — title, either movie, their streaming, or the
    voting window. Only fields present in the body are changed."""
    from datetime import timedelta

    battle = Battle.query.get(battle_id)
    if not battle:
        return jsonify({"message": "Battle not found"}), 404
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if title:
        battle.title = title

    a = data.get("movie_a") or {}
    if a.get("imdb_id"):
        battle.a_imdb_id = a["imdb_id"]
        battle.a_title = a.get("title") or battle.a_title
        battle.a_year = a.get("year")
        battle.a_poster = a.get("poster")
        battle.a_streaming = json.dumps(_clean_platforms(a.get("streaming") or []))

    b = data.get("movie_b") or {}
    if b.get("imdb_id"):
        battle.b_imdb_id = b["imdb_id"]
        battle.b_title = b.get("title") or battle.b_title
        battle.b_year = b.get("year")
        battle.b_poster = b.get("poster")
        battle.b_streaming = json.dumps(_clean_platforms(b.get("streaming") or []))

    if "days" in data:
        try:
            days = max(1, min(int(data["days"]), 90))
            battle.ends_at = battle.created_at + timedelta(days=days)
        except (TypeError, ValueError):
            pass

    db.session.commit()
    _seed_streaming_reports(battle.a_imdb_id, _load_platforms(battle.a_streaming))
    _seed_streaming_reports(battle.b_imdb_id, _load_platforms(battle.b_streaming))
    return jsonify(_battle_to_dict(battle, None, _vote_counts(battle.id))), 200


@admin_bp.route("/api/battles/<int:battle_id>/close", methods=["POST"])
@require_admin
def admin_close_battle(battle_id):
    battle = Battle.query.get(battle_id)
    if not battle:
        return jsonify({"message": "Battle not found"}), 404
    battle.active = False
    db.session.commit()
    return jsonify({"message": "Battle closed", "id": battle_id}), 200


def _all_user_ids():
    return [u.id for u in User.query.with_entities(User.id).all()]


@admin_bp.route("/api/dashboard", methods=["GET"])
@require_admin
def admin_dashboard():
    """History for the admin dashboard: each week's pick + how many completed it,
    and each battle's vote split + winner."""
    mows = MovieOfWeek.query.order_by(MovieOfWeek.week_key.desc()).all()
    mow_rows = []
    for m in mows:
        completed = MovieOfWeekCompletion.query.filter_by(mow_id=m.id).count()
        mow_rows.append({
            "week_key": m.week_key, "title": m.title, "year": m.year,
            "completed": completed, "active": bool(m.active),
        })

    battles = Battle.query.order_by(Battle.created_at.desc()).all()
    b_rows = []
    now = datetime.utcnow()
    for b in battles:
        c = _vote_counts(b.id)
        winner = None
        if c["a"] != c["b"]:
            winner = b.a_title if c["a"] > c["b"] else b.b_title
        b_rows.append({
            "id": b.id, "title": b.title,
            "a_title": b.a_title, "a_votes": c["a"],
            "b_title": b.b_title, "b_votes": c["b"],
            "winner": winner, "closed": now > b.ends_at, "active": bool(b.active),
        })

    return jsonify({"movies_of_week": mow_rows, "battles": b_rows}), 200


@admin_bp.route("/api/notify/movie-of-week", methods=["POST"])
@require_admin
def admin_notify_mow():
    mow = (
        MovieOfWeek.query.filter_by(active=True)
        .order_by(MovieOfWeek.week_key.desc()).first()
    )
    if not mow:
        return jsonify({"message": "No active Movie of the Week"}), 404
    from push import notify
    notify(
        _all_user_ids(), "New Movie of the Week", mow.title,
        category="festival", data={"type": "movie_of_week"},
    )
    return jsonify({"message": "Notification sent"}), 200


@admin_bp.route("/api/stats", methods=["GET"])
@require_admin
def admin_stats():
    """At-a-glance counts for the curation dashboard."""
    pro_statuses = ("comp", "paid", "trial")
    users_total = User.query.count()
    users_pro = User.query.filter(User.pro_status.in_(pro_statuses)).count()

    def items(media_type):
        return WatchlistItem.query.filter_by(media_type=media_type).count()

    return jsonify({
        "users_total": users_total,
        "users_pro": users_pro,
        "users_free": users_total - users_pro,
        "movies": items("movie"),
        "tv": items("tv"),
        "books": items("book"),
        "songs": items("song"),
        "watched": WatchlistItem.query.filter_by(watch_status="watched").count(),
        "recs": Recommendation.query.count(),
        "movie_nights": MovieNightSession.query.count(),
        "nights_rated": MovieNightParticipant.query.filter(
            MovieNightParticipant.rated_at.isnot(None)
        ).count(),
        "likes": ActivityLike.query.count(),
        "mow_completions": MovieOfWeekCompletion.query.count(),
        "battle_votes": BattleVote.query.count(),
    }), 200


@admin_bp.route("/api/notify/battle/<int:battle_id>", methods=["POST"])
@require_admin
def admin_notify_battle(battle_id):
    b = Battle.query.get(battle_id)
    if not b:
        return jsonify({"message": "Battle not found"}), 404
    from push import notify
    notify(
        _all_user_ids(), "New Battle", f"{b.a_title} vs {b.b_title}",
        category="festival", data={"type": "battle"},
    )
    return jsonify({"message": "Notification sent"}), 200


@admin_bp.route("/api/notify/battle/<int:battle_id>/result", methods=["POST"])
@require_admin
def admin_notify_battle_result(battle_id):
    b = Battle.query.get(battle_id)
    if not b:
        return jsonify({"message": "Battle not found"}), 404
    c = _vote_counts(battle_id)
    if c["a"] == c["b"]:
        msg = f"{b.title}: it's a tie!"
    else:
        winner = b.a_title if c["a"] > c["b"] else b.b_title
        msg = f"{winner} won {b.title}"
    from push import notify
    notify(
        _all_user_ids(), "Battle results", msg,
        category="festival", data={"type": "battle_result"},
    )
    # Mark concluded so the auto-result job doesn't announce it again.
    b.active = False
    db.session.commit()
    return jsonify({"message": "Notification sent"}), 200


# The admin page HTML is defined in admin_page.py to keep this file focused.
from admin_page import ADMIN_PAGE_HTML  # noqa: E402
