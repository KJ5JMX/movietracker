import json
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, request, jsonify
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import (
    db,
    User,
    Friendship,
    Recommendation,
    ReviewShare,
    StreamingServiceTap,
    MovieNightSession,
    MovieNightParticipant,
    WatchlistItem,
)


MIN_PASSWORD_LENGTH = 6

# ---------------------------------------------------------------------------
# Lightweight in-process rate limiter for the unauthenticated auth endpoints.
# Sliding window per key. Deliberately dependency-free; with gunicorn the
# window is per-worker, so the effective global limit is (limit x workers) —
# still plenty to stop credential stuffing on a small beta.
# ---------------------------------------------------------------------------

_RATE_BUCKETS = defaultdict(deque)
_RATE_LOCK = threading.Lock()


def _client_ip():
    """Behind the Cloudflare Tunnel the socket peer is localhost; trust the
    CF header first, then X-Forwarded-For, then the socket address."""
    return (
        request.headers.get("CF-Connecting-IP")
        or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )


def _rate_limited(key, limit, window_seconds):
    """Record a hit for `key` and return True if it exceeded the limit."""
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
    return False


def _parse_genres(raw):
    """Genres are stored as a JSON list of strings. Return as a list, or []."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(g) for g in value if isinstance(g, str) and g.strip()]
    except (ValueError, TypeError):
        pass
    return []


def _serialize_genres(value):
    """Accepts a list of strings, returns JSON text. None preserves the unset state."""
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    cleaned = sorted({str(g).strip() for g in value if isinstance(g, str) and str(g).strip()})
    return json.dumps(cleaned) if cleaned else json.dumps([])


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# Characters excluded for friend codes: 0/O, 1/I/l - too easily confused when read aloud
FRIEND_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_friend_code():
    """Generate an 8-char friend code formatted like 'AB12-XYZ9'."""
    raw = "".join(secrets.choice(FRIEND_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def ensure_friend_code(user):
    """Assign a unique friend code if the user doesn't have one yet."""
    if user.friend_code:
        return
    for _ in range(10):
        candidate = generate_friend_code()
        if not User.query.filter_by(friend_code=candidate).first():
            user.friend_code = candidate
            db.session.commit()
            return
    raise RuntimeError("Could not generate a unique friend code")


def user_to_dict(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "friend_code": user.friend_code,
        "notification_prefs": user.notification_prefs,
        "privacy_mode": user.privacy_mode,
        "dark_mode": bool(user.dark_mode),
        "pro_status": user.pro_status,
        "is_pro": user.is_pro,
        "pro_expires_at": (
            user.pro_expires_at.isoformat() if user.pro_expires_at else None
        ),
        "genres": _parse_genres(user.genres),
    }


@auth_bp.route("/register", methods=["POST"])
def register():
    if _rate_limited(f"register:{_client_ip()}", limit=10, window_seconds=300):
        return jsonify({"message": "Too many signup attempts. Try again in a few minutes."}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    # Case-insensitive duplicate check so 'Blake' and 'blake' can't coexist.
    # Login stays exact-match, so existing users are unaffected.
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return jsonify({"message": "Username already exists"}), 400

    password_hash = generate_password_hash(password)
    new_user = User(username=username, password_hash=password_hash)
    db.session.add(new_user)
    db.session.commit()

    ensure_friend_code(new_user)

    access_token = create_access_token(identity=str(new_user.id))
    return jsonify({
        "access_token": access_token,
        "user": user_to_dict(new_user),
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    # Limit per IP and per target username so one attacker can't hammer a
    # single account from many IPs OR many accounts from one IP unchecked.
    if _rate_limited(f"login:ip:{_client_ip()}", limit=15, window_seconds=300) or _rate_limited(
        f"login:user:{username.lower()}", limit=15, window_seconds=300
    ):
        return jsonify({"message": "Too many login attempts. Try again in a few minutes."}), 429

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Invalid username or password"}), 401

    ensure_friend_code(user)

    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": access_token,
        "user": user_to_dict(user),
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404
    ensure_friend_code(user)

    # Lazy subscription expiry: if a paid/trial user's Apple expiry has
    # passed, downgrade on read. Imported here (not at module top) to avoid a
    # circular import — iap_routes imports user_to_dict from this module.
    from iap_routes import apply_expiry_if_lapsed
    if apply_expiry_if_lapsed(user):
        db.session.commit()

    return jsonify(user_to_dict(user)), 200


@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}

    if "email" in data:
        email = (data["email"] or "").strip() or None
        user.email = email

    if "display_name" in data:
        name = (data["display_name"] or "").strip() or None
        user.display_name = name

    if "notification_prefs" in data:
        prefs = data["notification_prefs"]
        if prefs not in ("all", "mentions", "none"):
            return jsonify({"message": "Invalid notification_prefs"}), 400
        user.notification_prefs = prefs

    if "privacy_mode" in data:
        mode = data["privacy_mode"]
        if mode not in ("public", "friends", "private"):
            return jsonify({"message": "Invalid privacy_mode"}), 400
        user.privacy_mode = mode

    if "dark_mode" in data:
        user.dark_mode = bool(data["dark_mode"])

    if "genres" in data:
        serialized = _serialize_genres(data["genres"])
        if serialized is None and data["genres"] is not None:
            return jsonify({"message": "genres must be a list of strings"}), 400
        user.genres = serialized

    db.session.commit()
    return jsonify(user_to_dict(user)), 200


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}
    current = data.get("current_password")
    new = data.get("new_password")

    if not current or not new:
        return jsonify({"message": "current_password and new_password are required"}), 400

    if not check_password_hash(user.password_hash, current):
        return jsonify({"message": "Current password is incorrect"}), 401

    if len(new) < 6:
        return jsonify({"message": "New password must be at least 6 characters"}), 400

    user.password_hash = generate_password_hash(new)
    db.session.commit()
    return jsonify({"message": "Password updated"}), 200


@auth_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}
    password = data.get("password")
    if not password or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Password confirmation required"}), 401

    # Explicitly remove every row that references this user. Only
    # watchlist_items has an ORM cascade; the rest would either orphan
    # (SQLite) or raise an FK IntegrityError (Postgres) on user delete.
    # Done as bulk deletes inside one transaction.

    # Movie night sessions this user hosted (and ALL their participant rows),
    # then this user's participant rows in other people's sessions.
    hosted_ids = [
        s.id
        for s in MovieNightSession.query.with_entities(MovieNightSession.id)
        .filter(MovieNightSession.host_user_id == user_id)
        .all()
    ]
    if hosted_ids:
        MovieNightParticipant.query.filter(
            MovieNightParticipant.session_id.in_(hosted_ids)
        ).delete(synchronize_session=False)
        MovieNightSession.query.filter(
            MovieNightSession.id.in_(hosted_ids)
        ).delete(synchronize_session=False)
    MovieNightParticipant.query.filter(
        MovieNightParticipant.user_id == user_id
    ).delete(synchronize_session=False)

    Friendship.query.filter(
        or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)
    ).delete(synchronize_session=False)

    # Review shares first: they may FK recommendations via rec_id, so clear
    # them before deleting recs to keep Postgres happy.
    ReviewShare.query.filter(
        or_(ReviewShare.from_user_id == user_id, ReviewShare.to_user_id == user_id)
    ).delete(synchronize_session=False)
    # Any surviving review (between two other users) that still points at one
    # of this user's recs: drop the link, keep the review.
    doomed_rec_ids = [
        r.id
        for r in Recommendation.query.with_entities(Recommendation.id)
        .filter(
            or_(
                Recommendation.from_user_id == user_id,
                Recommendation.to_user_id == user_id,
            )
        )
        .all()
    ]
    if doomed_rec_ids:
        ReviewShare.query.filter(ReviewShare.rec_id.in_(doomed_rec_ids)).update(
            {"rec_id": None}, synchronize_session=False
        )
    Recommendation.query.filter(
        or_(
            Recommendation.from_user_id == user_id,
            Recommendation.to_user_id == user_id,
        )
    ).delete(synchronize_session=False)

    StreamingServiceTap.query.filter(
        StreamingServiceTap.user_id == user_id
    ).delete(synchronize_session=False)

    # Discussion comments are this user's own words — they go with the account.
    from models import DiscussionComment
    DiscussionComment.query.filter(
        DiscussionComment.user_id == user_id
    ).delete(synchronize_session=False)

    # Other users' items that credit this user as recommender: drop the
    # attribution, keep their item.
    WatchlistItem.query.filter(
        WatchlistItem.recommended_by_user_id == user_id
    ).update({"recommended_by_user_id": None}, synchronize_session=False)

    db.session.delete(user)  # cascades this user's own watchlist_items
    db.session.commit()
    return jsonify({"message": "Account deleted"}), 200
