"""
Movie Night V1 endpoints.

Endpoints:
  POST /night/preview         body: same filters as /roll. Returns { count } of
                              matching titles (not Pro-gated; the count is the upsell).
  POST /night/roll            body: { participant_ids, max_runtime?, mood?, media_type? }
                              Returns top 3 candidates from combined want-to-watch lists.
  POST /night/sessions        body: { participant_ids, picked_imdb_id, ...item snapshot }
  GET  /night/sessions/active List active sessions where I'm host or participant.
  GET  /night/sessions/<id>   Full session detail (item + participants + ratings).
  POST /night/sessions/<id>/end                 Host marks session ended.
  POST /night/sessions/<id>/rate                body: { rating } — record my post-watch rating + add to watched list.
"""

import random
from datetime import datetime, timezone, date

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, and_

from push import notify
from models import (
    db,
    User,
    Friendship,
    WatchlistItem,
    MovieNightSession,
    MovieNightParticipant,
    NightMessage,
)
from watchlist_routes import _parse_release_date
from achievements import sync_and_notify


night_bp = Blueprint("night", __name__, url_prefix="/night")


# ---------------------------------------------------------------------------
# Mood → genre keyword map. Match against WatchlistItem.genre substring.
# ---------------------------------------------------------------------------

MOOD_GENRES = {
    "comfort": ["comedy", "romance", "animation", "family"],
    "smart":   ["drama", "documentary", "mystery", "biography"],
    "wild":    ["action", "sci-fi", "adventure", "fantasy"],
    "scary":   ["horror", "thriller"],
    "funny":   ["comedy"],
}


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _are_friends(user_a_id, user_b_id):
    if user_a_id == user_b_id:
        return True
    return Friendship.query.filter(
        or_(
            and_(
                Friendship.requester_id == user_a_id,
                Friendship.addressee_id == user_b_id,
            ),
            and_(
                Friendship.requester_id == user_b_id,
                Friendship.addressee_id == user_a_id,
            ),
        ),
        Friendship.status == "accepted",
    ).first() is not None


def _validate_participants(me_id, participant_ids):
    """Returns (clean_ids, error_message). clean_ids always includes me_id."""
    ids = set()
    ids.add(me_id)
    if not isinstance(participant_ids, list):
        return None, "participant_ids must be a list"
    for raw in participant_ids:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            return None, f"Invalid participant id: {raw}"
        if pid == me_id:
            continue
        if not _are_friends(me_id, pid):
            return None, f"User {pid} is not a friend"
        ids.add(pid)
    return sorted(ids), None


# ---------------------------------------------------------------------------
# Shared filter pipeline for /roll and /preview
# ---------------------------------------------------------------------------

def _parse_filters(data):
    """Returns (media_type, max_runtime, mood, error_message)."""
    media_type = data.get("media_type", "movie")
    if media_type not in {"movie", "tv", "any"}:
        return None, None, None, f"Invalid media_type: {media_type}"
    max_runtime = data.get("max_runtime")
    if max_runtime is not None:
        try:
            max_runtime = int(max_runtime)
        except (TypeError, ValueError):
            return None, None, None, "max_runtime must be an integer"
    mood = (data.get("mood") or "").strip().lower() or None
    return media_type, max_runtime, mood, None


def _scored_candidates(user_ids, media_type, max_runtime, mood):
    """The matching pipeline: group everyone's lists, filter, score.
    Returns the scored list sorted best-first."""
    mood_keywords = MOOD_GENRES.get(mood, []) if mood else []

    # Pull every participant's full list. Group by imdb_id+media_type so we can
    # detect overlap and aggregate watch_status across the group.
    query = WatchlistItem.query.filter(WatchlistItem.user_id.in_(user_ids))
    if media_type != "any":
        query = query.filter(WatchlistItem.media_type == media_type)
    items = query.all()

    # Group: key = (imdb_id, media_type)
    groups = {}
    for it in items:
        key = (it.imdb_id, it.media_type)
        bucket = groups.setdefault(key, {
            "imdb_id": it.imdb_id,
            "media_type": it.media_type,
            "title": it.title,
            "year": it.year,
            "poster": it.poster,
            "genre": it.genre,
            "runtime_minutes": it.runtime_minutes,
            "released": it.released,
            "wanted_by": set(),   # user_ids who have watch_status='want_to_watch'
            "watched_by": set(),  # user_ids who have watch_status='watched'
        })
        # Prefer the richest snapshot fields if any participant has them
        if not bucket["poster"] and it.poster:
            bucket["poster"] = it.poster
        if not bucket["genre"] and it.genre:
            bucket["genre"] = it.genre
        if not bucket["runtime_minutes"] and it.runtime_minutes:
            bucket["runtime_minutes"] = it.runtime_minutes
        if not bucket["released"] and it.released:
            bucket["released"] = it.released
        if it.watch_status == "watched":
            bucket["watched_by"].add(it.user_id)
        else:
            bucket["wanted_by"].add(it.user_id)

    # Filter + score
    scored = []
    for key, b in groups.items():
        # Skip anything ALL participants have already watched
        if len(b["watched_by"]) == len(user_ids):
            continue
        # If nobody actively WANTS this (everyone has it as watched but not full overlap),
        # still allow it through with low weight — but skip if literally no want_to_watch
        if not b["wanted_by"]:
            continue
        # Skip titles that aren't out yet — you can't watch tonight what hasn't
        # released. (Items can be on a list with a "remind me on release" set.)
        release_date = _parse_release_date(b["released"])
        if release_date and release_date > date.today():
            continue
        # Runtime filter: if max provided AND we know the runtime AND it's over, skip
        if max_runtime and b["runtime_minutes"] and b["runtime_minutes"] > max_runtime:
            continue
        # Mood filter: must match at least one keyword in genre (case-insensitive)
        if mood_keywords:
            genre = (b["genre"] or "").lower()
            if not any(kw in genre for kw in mood_keywords):
                continue

        # Score: overlap is king. Each participant who wants it = +10.
        # Penalize items already watched by some participants slightly.
        score = len(b["wanted_by"]) * 10 - len(b["watched_by"]) * 2
        # Tiny randomness so identical scores get shuffled each roll
        score += random.random()
        scored.append((score, b))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Preview: how many titles match the current filters. Deliberately NOT
# Pro-gated for groups — the count is the upsell; the roll stays gated.
# ---------------------------------------------------------------------------

@night_bp.route("/preview", methods=["POST"])
@jwt_required()
def preview():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}

    user_ids, err = _validate_participants(me_id, data.get("participant_ids") or [])
    if err:
        return jsonify({"message": err}), 400
    media_type, max_runtime, mood, err = _parse_filters(data)
    if err:
        return jsonify({"message": err}), 400

    scored = _scored_candidates(user_ids, media_type, max_runtime, mood)
    return jsonify({
        "count": len(scored),
        "participant_count": len(user_ids),
        "media_type": media_type,
    }), 200


# ---------------------------------------------------------------------------
# Roll: pick top 3 candidates from combined want-to-watch lists
# ---------------------------------------------------------------------------

@night_bp.route("/roll", methods=["POST"])
@jwt_required()
def roll():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}

    participant_ids = data.get("participant_ids") or []
    user_ids, err = _validate_participants(me_id, participant_ids)
    if err:
        return jsonify({"message": err}), 400

    # Movie Night is a Pro feature end to end (solo or group).
    me = User.query.get(me_id)
    if not me or not me.is_pro:
        return jsonify({
            "message": "Movie Night requires Pro",
            "code": "pro_required",
        }), 402

    media_type, max_runtime, mood, err = _parse_filters(data)
    if err:
        return jsonify({"message": err}), 400

    scored = _scored_candidates(user_ids, media_type, max_runtime, mood)
    top = [b for _, b in scored[:3]]

    def candidate_dict(b):
        return {
            "imdb_id": b["imdb_id"],
            "media_type": b["media_type"],
            "title": b["title"],
            "year": b["year"],
            "poster": b["poster"],
            "genre": b["genre"],
            "runtime_minutes": b["runtime_minutes"],
            "wanted_by_count": len(b["wanted_by"]),
            "watched_by_count": len(b["watched_by"]),
            "total_participants": len(user_ids),
        }

    return jsonify({
        "candidates": [candidate_dict(b) for b in top],
        "participant_count": len(user_ids),
        "had_results": len(scored) > 0,
        "match_count": len(scored),
    }), 200


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _serialize_session(session, me_id):
    participants = MovieNightParticipant.query.filter_by(session_id=session.id).all()
    user_ids = [p.user_id for p in participants]
    users_by_id = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}
    participant_dicts = []
    for p in participants:
        participant_dicts.append({
            "user": _user_summary(users_by_id.get(p.user_id)),
            "rating": p.rating,
            "rated_at": p.rated_at.isoformat() if p.rated_at else None,
        })
    return {
        "id": session.id,
        "host_user_id": session.host_user_id,
        "host": _user_summary(users_by_id.get(session.host_user_id)),
        "is_host": session.host_user_id == me_id,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "scheduled_for": session.scheduled_for.isoformat() if session.scheduled_for else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "picked": {
            "imdb_id": session.picked_imdb_id,
            "title": session.picked_title,
            "year": session.picked_year,
            "poster": session.picked_poster,
            "media_type": session.picked_media_type,
        },
        "filters": {
            "max_runtime": session.filter_max_runtime,
            "mood": session.filter_mood,
        },
        "participants": participant_dicts,
    }


def _fmt_when(dt):
    # "Fri Jun 19, 8:00 PM" (Linux strftime; the container is Linux)
    return dt.strftime("%a %b %-d, %-I:%M %p")


@night_bp.route("/schedule", methods=["POST"])
@jwt_required()
def schedule_night():
    """Plan a Movie Night ahead of time. No pick yet; the host rolls when
    the night arrives. Invitees get a push now and a reminder near start."""
    me_id = int(get_jwt_identity())
    me = User.query.get(me_id)
    if not me:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}
    user_ids, err = _validate_participants(me_id, data.get("participant_ids") or [])
    if err:
        return jsonify({"message": err}), 400
    if not me.is_pro:
        return jsonify({
            "message": "Movie Night requires Pro",
            "code": "pro_required",
        }), 402

    raw = data.get("scheduled_for")
    try:
        scheduled_for = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return jsonify({"message": "scheduled_for must be an ISO datetime"}), 400
    # Normalize to naive UTC (the whole codebase uses naive utcnow)
    if scheduled_for.tzinfo is not None:
        scheduled_for = scheduled_for.astimezone(timezone.utc).replace(tzinfo=None)
    if scheduled_for <= datetime.utcnow():
        return jsonify({"message": "scheduled_for must be in the future"}), 400

    session = MovieNightSession(
        host_user_id=me_id,
        status="scheduled",
        scheduled_for=scheduled_for,
        filter_max_runtime=data.get("max_runtime"),
        filter_mood=data.get("mood"),
    )
    db.session.add(session)
    db.session.flush()
    for uid in user_ids:
        db.session.add(MovieNightParticipant(session_id=session.id, user_id=uid))
    db.session.commit()

    host_name = me.display_name or me.username
    invitees = [uid for uid in user_ids if uid != me_id]
    when_label = str(data.get("when_label") or "").strip()[:40]
    when = when_label or _fmt_when(scheduled_for) + " UTC"
    notify(invitees, "Movie Night invite",
           f"{host_name} planned a movie night \u00b7 {when}",
           category="movie_nights")
    return jsonify(_serialize_session(session, me_id)), 201


@night_bp.route("/sessions", methods=["POST"])
@jwt_required()
def create_session():
    me_id = int(get_jwt_identity())
    me = User.query.get(me_id)
    if not me:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}

    participant_ids = data.get("participant_ids") or []
    user_ids, err = _validate_participants(me_id, participant_ids)
    if err:
        return jsonify({"message": err}), 400

    # Movie Night is a Pro feature end to end (solo or group).
    if not me.is_pro:
        return jsonify({
            "message": "Movie Night requires Pro",
            "code": "pro_required",
        }), 402

    imdb_id = data.get("picked_imdb_id")
    title = data.get("picked_title")
    if not (imdb_id and title):
        return jsonify({"message": "picked_imdb_id and picked_title are required"}), 400

    # Rolling for a previously scheduled night converts that session instead
    # of creating a parallel one.
    scheduled_id = data.get("session_id")
    if scheduled_id:
        existing = MovieNightSession.query.get(scheduled_id)
        if (
            existing
            and existing.host_user_id == me_id
            and existing.status == "scheduled"
        ):
            existing.status = "active"
            existing.picked_imdb_id = imdb_id
            existing.picked_title = title
            existing.picked_year = data.get("picked_year")
            existing.picked_poster = data.get("picked_poster")
            existing.picked_media_type = data.get("picked_media_type", "movie")
            db.session.commit()
            host_name = me.display_name or me.username
            others = [
                p.user_id
                for p in MovieNightParticipant.query.filter_by(
                    session_id=existing.id
                ).all()
                if p.user_id != me_id
            ]
            notify(others, "Movie Night is starting",
                   f"{host_name} picked: {title}",
                   category="movie_nights")
            return jsonify(_serialize_session(existing, me_id)), 200

    session = MovieNightSession(
        host_user_id=me_id,
        picked_imdb_id=imdb_id,
        picked_title=title,
        picked_year=data.get("picked_year"),
        picked_poster=data.get("picked_poster"),
        picked_media_type=data.get("picked_media_type", "movie"),
        filter_max_runtime=data.get("max_runtime"),
        filter_mood=data.get("mood"),
        status="active",
    )
    db.session.add(session)
    db.session.flush()  # need session.id

    for uid in user_ids:
        db.session.add(MovieNightParticipant(session_id=session.id, user_id=uid))
    db.session.commit()

    host_name = me.display_name or me.username
    invitees = [uid for uid in user_ids if uid != me_id]
    notify(invitees, "Movie Night",
           f"{host_name} started a movie night: {title}",
           category="movie_nights")
    return jsonify(_serialize_session(session, me_id)), 201


@night_bp.route("/sessions/active", methods=["GET"])
@jwt_required()
def list_active_sessions():
    me_id = int(get_jwt_identity())
    my_participant_rows = MovieNightParticipant.query.filter_by(user_id=me_id).all()
    session_ids = [p.session_id for p in my_participant_rows]
    if not session_ids:
        return jsonify([]), 200
    sessions = (
        MovieNightSession.query
        .filter(MovieNightSession.id.in_(session_ids))
        .filter(MovieNightSession.status.in_(["active", "scheduled"]))
        .order_by(MovieNightSession.created_at.desc())
        .all()
    )
    return jsonify([_serialize_session(s, me_id) for s in sessions]), 200


@night_bp.route("/sessions/<int:session_id>", methods=["GET"])
@jwt_required()
def get_session(session_id):
    me_id = int(get_jwt_identity())
    session = MovieNightSession.query.get(session_id)
    if not session:
        return jsonify({"message": "Session not found"}), 404
    # Must be a participant
    participant = MovieNightParticipant.query.filter_by(
        session_id=session_id, user_id=me_id
    ).first()
    if not participant:
        return jsonify({"message": "Not a participant"}), 403
    return jsonify(_serialize_session(session, me_id)), 200


@night_bp.route("/sessions/<int:session_id>/end", methods=["POST"])
@jwt_required()
def end_session(session_id):
    me_id = int(get_jwt_identity())
    session = MovieNightSession.query.get(session_id)
    if not session:
        return jsonify({"message": "Session not found"}), 404
    if session.host_user_id != me_id:
        return jsonify({"message": "Only the host can end the session"}), 403
    if session.status != "active":
        return jsonify({"message": f"Session is {session.status}"}), 400
    session.status = "ended"
    session.ended_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_serialize_session(session, me_id)), 200


@night_bp.route("/sessions/<int:session_id>", methods=["PATCH"])
@jwt_required()
def edit_scheduled_night(session_id):
    """Edit a planned (not-yet-rolled) Movie Night: change the time, who's
    invited, or the filters. Host only, and only while it's still scheduled."""
    me_id = int(get_jwt_identity())
    me = User.query.get(me_id)
    if not me:
        return jsonify({"message": "User not found"}), 404

    session = MovieNightSession.query.get(session_id)
    if not session:
        return jsonify({"message": "Session not found"}), 404
    if session.host_user_id != me_id:
        return jsonify({"message": "Only the host can edit this night"}), 403
    if session.status != "scheduled":
        return jsonify({"message": "Only scheduled nights can be edited"}), 400

    data = request.get_json() or {}

    if "scheduled_for" in data:
        raw = data.get("scheduled_for")
        try:
            scheduled_for = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return jsonify({"message": "scheduled_for must be an ISO datetime"}), 400
        if scheduled_for.tzinfo is not None:
            scheduled_for = scheduled_for.astimezone(timezone.utc).replace(tzinfo=None)
        if scheduled_for <= datetime.utcnow():
            return jsonify({"message": "scheduled_for must be in the future"}), 400
        session.scheduled_for = scheduled_for
        # New time means the prior reminder no longer applies.
        session.reminder_sent = False

    if "participant_ids" in data:
        user_ids, err = _validate_participants(me_id, data.get("participant_ids") or [])
        if err:
            return jsonify({"message": err}), 400
        if len(user_ids) > 1 and not me.is_pro:
            return jsonify({
                "message": "Movie Night with friends requires Pro",
                "code": "pro_required",
            }), 402
        MovieNightParticipant.query.filter_by(session_id=session.id).delete(
            synchronize_session=False
        )
        for uid in user_ids:
            db.session.add(MovieNightParticipant(session_id=session.id, user_id=uid))

    if "max_runtime" in data:
        session.filter_max_runtime = data.get("max_runtime")
    if "mood" in data:
        session.filter_mood = data.get("mood")

    db.session.commit()

    host_name = me.display_name or me.username
    others = [
        p.user_id
        for p in MovieNightParticipant.query.filter_by(session_id=session.id).all()
        if p.user_id != me_id
    ]
    when_label = str(data.get("when_label") or "").strip()[:40]
    when = when_label or (
        _fmt_when(session.scheduled_for) + " UTC" if session.scheduled_for else ""
    )
    notify(others, "Movie Night updated",
           f"{host_name} changed the plan · {when}".strip(" · "),
           category="movie_nights")
    return jsonify(_serialize_session(session, me_id)), 200


@night_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def cancel_scheduled_night(session_id):
    """Cancel a planned Movie Night. Host only, scheduled only (an active
    night is ended via /end, not deleted)."""
    me_id = int(get_jwt_identity())
    me = User.query.get(me_id)
    session = MovieNightSession.query.get(session_id)
    if not session:
        return jsonify({"message": "Session not found"}), 404
    if session.host_user_id != me_id:
        return jsonify({"message": "Only the host can cancel this night"}), 403
    if session.status != "scheduled":
        return jsonify({"message": "Only scheduled nights can be canceled"}), 400

    others = [
        p.user_id
        for p in MovieNightParticipant.query.filter_by(session_id=session.id).all()
        if p.user_id != me_id
    ]
    MovieNightParticipant.query.filter_by(session_id=session.id).delete(
        synchronize_session=False
    )
    db.session.delete(session)
    db.session.commit()

    host_name = me.display_name or me.username
    notify(others, "Movie Night canceled", f"{host_name} called off the movie night",
           category="movie_nights")
    return jsonify({"message": "Movie night canceled", "id": session_id}), 200


@night_bp.route("/sessions/<int:session_id>/rate", methods=["POST"])
@jwt_required()
def rate_session(session_id):
    """Record this participant's post-watch rating. Also flips the matching
    WatchlistItem to 'watched' + sets its rating, so the user's personal list
    stays in sync. If the item isn't in their list, adds it."""
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}
    raw_rating = data.get("rating")
    try:
        rating = int(raw_rating)
    except (TypeError, ValueError):
        return jsonify({"message": "rating must be 1-5"}), 400
    if not (1 <= rating <= 5):
        return jsonify({"message": "rating must be 1-5"}), 400

    # Optional written review, stored as the item's notes (same field the
    # Detail screen edits)
    notes = (data.get("notes") or "").strip()[:2000] or None

    session = MovieNightSession.query.get(session_id)
    if not session:
        return jsonify({"message": "Session not found"}), 404

    participant = MovieNightParticipant.query.filter_by(
        session_id=session_id, user_id=me_id
    ).first()
    if not participant:
        return jsonify({"message": "Not a participant"}), 403

    participant.rating = rating
    participant.rated_at = datetime.utcnow()

    # Sync to personal watchlist
    item = WatchlistItem.query.filter_by(
        user_id=me_id,
        imdb_id=session.picked_imdb_id,
        media_type=session.picked_media_type,
    ).first()
    if item:
        item.watch_status = "watched"
        item.rating = rating
        if not item.watched_at:
            item.watched_at = datetime.utcnow()
        if notes:
            item.notes = notes
    else:
        item = WatchlistItem(
            title=session.picked_title,
            year=session.picked_year,
            imdb_id=session.picked_imdb_id,
            media_type=session.picked_media_type,
            poster=session.picked_poster,
            watch_status="watched",
            rating=rating,
            notes=notes,
            watched_at=datetime.utcnow(),
            user_id=me_id,
        )
        db.session.add(item)

    db.session.commit()
    sync_and_notify(me_id)
    return jsonify(_serialize_session(session, me_id)), 200


# ---------------------------------------------------------------------------
# Movie Night chat + history (Pro: chat lives inside a Movie Night session)
# ---------------------------------------------------------------------------

def _message_to_dict(m, users_by_id=None):
    user = (users_by_id or {}).get(m.user_id) if users_by_id is not None else User.query.get(m.user_id)
    return {
        "id": m.id,
        "user": _user_summary(user),
        "text": m.text,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _is_participant(session_id, user_id):
    return MovieNightParticipant.query.filter_by(
        session_id=session_id, user_id=user_id
    ).first() is not None


@night_bp.route("/sessions/<int:session_id>/messages", methods=["POST"])
@jwt_required()
def post_message(session_id):
    me_id = int(get_jwt_identity())
    if not MovieNightSession.query.get(session_id):
        return jsonify({"message": "Session not found"}), 404
    if not _is_participant(session_id, me_id):
        return jsonify({"message": "Not a participant"}), 403
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"message": "Message can't be empty"}), 400
    msg = NightMessage(session_id=session_id, user_id=me_id, text=text[:1000])
    db.session.add(msg)
    db.session.commit()
    return jsonify(_message_to_dict(msg)), 201


@night_bp.route("/sessions/<int:session_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(session_id):
    me_id = int(get_jwt_identity())
    if not _is_participant(session_id, me_id):
        return jsonify({"message": "Not a participant"}), 403
    after = request.args.get("after", type=int)
    q = NightMessage.query.filter_by(session_id=session_id)
    if after:
        q = q.filter(NightMessage.id > after)
    msgs = q.order_by(NightMessage.id.asc()).all()
    users_by_id = {
        u.id: u for u in User.query.filter(
            User.id.in_([m.user_id for m in msgs])
        ).all()
    } if msgs else {}
    return jsonify([_message_to_dict(m, users_by_id) for m in msgs]), 200


@night_bp.route("/sessions/history", methods=["GET"])
@jwt_required()
def sessions_history():
    """Every Movie Night I've been part of, newest first (for the clock-icon list)."""
    me_id = int(get_jwt_identity())
    session_ids = [
        p.session_id
        for p in MovieNightParticipant.query.filter_by(user_id=me_id).all()
    ]
    if not session_ids:
        return jsonify([]), 200
    sessions = (
        MovieNightSession.query.filter(MovieNightSession.id.in_(session_ids))
        .order_by(MovieNightSession.created_at.desc())
        .all()
    )
    return jsonify([_serialize_session(s, me_id) for s in sessions]), 200


@night_bp.route("/sessions/for-title", methods=["GET"])
@jwt_required()
def sessions_for_title():
    """Movie Nights for a given title that I joined, with ratings + saved chat —
    powers the 'Movie night happened on this date' block on the movie's detail."""
    me_id = int(get_jwt_identity())
    imdb_id = request.args.get("imdb_id")
    if not imdb_id:
        return jsonify([]), 200
    session_ids = [
        p.session_id
        for p in MovieNightParticipant.query.filter_by(user_id=me_id).all()
    ]
    if not session_ids:
        return jsonify([]), 200
    sessions = (
        MovieNightSession.query.filter(
            MovieNightSession.id.in_(session_ids),
            MovieNightSession.picked_imdb_id == imdb_id,
        )
        .order_by(MovieNightSession.created_at.desc())
        .all()
    )
    out = []
    for s in sessions:
        d = _serialize_session(s, me_id)
        msgs = (
            NightMessage.query.filter_by(session_id=s.id)
            .order_by(NightMessage.id.asc()).all()
        )
        ubi = {
            u.id: u for u in User.query.filter(
                User.id.in_([m.user_id for m in msgs])
            ).all()
        } if msgs else {}
        d["messages"] = [_message_to_dict(m, ubi) for m in msgs]
        out.append(d)
    return jsonify(out), 200
