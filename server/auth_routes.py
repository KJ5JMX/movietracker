import hashlib
import json
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from html import escape

from flask import Blueprint, request, jsonify, Response
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import jwt
from jwt import PyJWKClient
from config import Config
from email_utils import send_email, password_reset_email
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
    PasswordResetToken,
)


MIN_PASSWORD_LENGTH = 6

# Pragmatic email check: one @, a dot in the domain, no spaces. Not RFC-perfect
# on purpose -- the real validation is whether the reset email arrives.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value):
    return bool(value) and bool(EMAIL_RE.match(value))


def _hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
        "onboarded": bool(user.onboarded),
        "has_apple": bool(user.apple_sub),
        "has_google": bool(user.google_sub),
    }


@auth_bp.route("/register", methods=["POST"])
def register():
    if _rate_limited(f"register:{_client_ip()}", limit=10, window_seconds=300):
        return jsonify({"message": "Too many signup attempts. Try again in a few minutes."}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password")
    email = (data.get("email") or "").strip()

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    # Email is now required at signup so accounts have a password-reset path.
    if not email:
        return jsonify({"message": "Email is required"}), 400
    if not _valid_email(email):
        return jsonify({"message": "Please enter a valid email address"}), 400

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    # Case-insensitive duplicate check so 'Blake' and 'blake' can't coexist.
    # Login stays exact-match, so existing users are unaffected.
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return jsonify({"message": "Username already exists"}), 400

    # Email must be unique (case-insensitive) so reset targets one account.
    # Enforced in code, not a DB constraint, to avoid breaking pre-existing
    # rows that have NULL or duplicate emails from before this was required.
    if User.query.filter(func.lower(User.email) == email.lower()).first():
        return jsonify({"message": "An account with that email already exists"}), 400

    password_hash = generate_password_hash(password)
    new_user = User(username=username, password_hash=password_hash, email=email)
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
        email = (data["email"] or "").strip()
        if not email:
            return jsonify({"message": "Email can't be empty"}), 400
        if not _valid_email(email):
            return jsonify({"message": "Please enter a valid email address"}), 400
        # Unique (case-insensitive), excluding this user's own row.
        clash = User.query.filter(
            func.lower(User.email) == email.lower(), User.id != user.id
        ).first()
        if clash:
            return jsonify({"message": "An account with that email already exists"}), 400
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

    if "username" in data:
        username = (data["username"] or "").strip()
        if not username:
            return jsonify({"message": "Username can't be empty"}), 400
        if len(username) > 30:
            return jsonify({"message": "Username must be 30 characters or fewer"}), 400
        clash = User.query.filter(
            func.lower(User.username) == username.lower(), User.id != user.id
        ).first()
        if clash:
            return jsonify({"message": "Username already taken"}), 400
        user.username = username

    if "onboarded" in data:
        user.onboarded = bool(data["onboarded"])

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
    from models import DiscussionComment, DeviceToken
    DiscussionComment.query.filter(
        DiscussionComment.user_id == user_id
    ).delete(synchronize_session=False)

    # Push device tokens die with the account.
    DeviceToken.query.filter(
        DeviceToken.user_id == user_id
    ).delete(synchronize_session=False)

    # Outstanding password-reset tokens for this account.
    PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user_id
    ).delete(synchronize_session=False)

    # Other users' items that credit this user as recommender: drop the
    # attribution, keep their item.
    WatchlistItem.query.filter(
        WatchlistItem.recommended_by_user_id == user_id
    ).update({"recommended_by_user_id": None}, synchronize_session=False)

    db.session.delete(user)  # cascades this user's own watchlist_items
    db.session.commit()
    return jsonify({"message": "Account deleted"}), 200


# ---------------------------------------------------------------------------
# Password reset (forgot password). Flow:
#   1. App POSTs an identifier (email or username) to /auth/forgot-password.
#   2. If it matches an account with an email, we email a single-use link to
#      /auth/reset?token=... (token stored only as a SHA-256 hash).
#   3. The link opens a server-rendered page where the user sets a new
#      password. No app deep-linking required; works on any device's browser.
# The forgot-password response is deliberately identical whether or not the
# account exists, so it can't be used to discover who has an account.
# ---------------------------------------------------------------------------

_GENERIC_FORGOT_MSG = (
    "If an account matches that, we've sent a reset link. "
    "Check your email."
)


def _html_page(title, body_html, status=200):
    """Minimal server-rendered page in the ShelfMates palette."""
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; background: #F4EFE6;
         color: #2D2520; margin: 0; padding: 24px; }}
  .card {{ max-width: 420px; margin: 40px auto; background: #FFFCF7; border: 2px solid #2D2520;
          border-radius: 12px; padding: 28px; box-shadow: 4px 4px 0 #2D2520; }}
  h1 {{ color: #2D5F4F; font-size: 22px; margin-top: 0; }}
  label {{ display: block; font-weight: 600; margin: 16px 0 6px; }}
  input[type=password] {{ width: 100%; box-sizing: border-box; padding: 12px; font-size: 16px;
          border: 2px solid #2D2520; border-radius: 8px; background: #fff; }}
  button {{ width: 100%; margin-top: 22px; padding: 14px; font-size: 16px; font-weight: 700;
          color: #FFFCF7; background: #2D5F4F; border: 2px solid #1f4639; border-radius: 8px;
          cursor: pointer; }}
  .err {{ background: #f6dcd2; border: 2px solid #b3502f; color: #7a3115; padding: 10px;
          border-radius: 8px; margin-bottom: 12px; }}
  .muted {{ color: #7B5E47; font-size: 14px; }}
</style>
</head>
<body><div class="card">{body_html}</div></body>
</html>"""
    return Response(html, status=status, mimetype="text/html")


def _reset_form(token, error=None):
    err_html = f'<div class="err">{escape(error)}</div>' if error else ""
    body = f"""
  <h1>Set a new password</h1>
  {err_html}
  <form method="POST" action="/auth/reset">
    <input type="hidden" name="token" value="{escape(token)}">
    <label for="password">New password</label>
    <input type="password" id="password" name="password" autocomplete="new-password" required>
    <label for="confirm">Confirm password</label>
    <input type="password" id="confirm" name="confirm" autocomplete="new-password" required>
    <button type="submit">Update password</button>
    <p class="muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
  </form>"""
    return _html_page("Reset your password", body)


def _invalid_link_page():
    body = """
  <h1>Link expired</h1>
  <p>This reset link is invalid or has already been used. Open the app and
  tap "Forgot password?" to request a new one.</p>"""
    return _html_page("Link expired", body, status=400)


def _find_user_by_identifier(identifier):
    """Match an account by email (case-insensitive) or username (case-insensitive)."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    return (
        User.query.filter(func.lower(User.email) == ident.lower()).first()
        or User.query.filter(func.lower(User.username) == ident.lower()).first()
    )


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    # Rate-limit by IP and by identifier so this can't be used to blast a
    # mailbox or to enumerate accounts by timing.
    if _rate_limited(f"forgot:ip:{_client_ip()}", limit=10, window_seconds=600):
        return jsonify({"message": "Too many requests. Try again in a few minutes."}), 429

    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or data.get("email") or data.get("username") or "")
    if identifier:
        _rate_limited(f"forgot:id:{identifier.strip().lower()}", limit=5, window_seconds=600)

    user = _find_user_by_identifier(identifier)
    if user and user.email:
        # Invalidate any earlier outstanding tokens for this user first.
        PasswordResetToken.query.filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).delete(synchronize_session=False)

        raw_token = secrets.token_urlsafe(32)
        ttl = Config.RESET_TOKEN_TTL_MINUTES
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(minutes=ttl),
        )
        db.session.add(prt)
        db.session.commit()

        reset_url = f"{Config.APP_PUBLIC_URL}/auth/reset?token={raw_token}"
        subject, html, text = password_reset_email(reset_url, ttl)
        send_email(user.email, subject, html, text=text)

    # Always the same response, whether or not anything was found/sent.
    return jsonify({"message": _GENERIC_FORGOT_MSG}), 200


def _lookup_active_token(raw_token):
    """Return a usable PasswordResetToken for raw_token, or None."""
    if not raw_token:
        return None
    prt = PasswordResetToken.query.filter_by(token_hash=_hash_token(raw_token)).first()
    if not prt or prt.used_at is not None:
        return None
    if prt.expires_at < datetime.utcnow():
        return None
    return prt


@auth_bp.route("/reset", methods=["GET"])
def reset_form():
    token = request.args.get("token", "")
    if not _lookup_active_token(token):
        return _invalid_link_page()
    return _reset_form(token)


@auth_bp.route("/reset", methods=["POST"])
def reset_submit():
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    prt = _lookup_active_token(token)
    if not prt:
        return _invalid_link_page()

    if len(password) < MIN_PASSWORD_LENGTH:
        return _reset_form(token, error=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != confirm:
        return _reset_form(token, error="Passwords don't match.")

    user = User.query.get(prt.user_id)
    if not user:
        return _invalid_link_page()

    user.password_hash = generate_password_hash(password)
    prt.used_at = datetime.utcnow()
    # Burn any other outstanding tokens for this user.
    PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.id != prt.id,
        PasswordResetToken.used_at.is_(None),
    ).delete(synchronize_session=False)
    db.session.commit()

    body = """
  <h1>Password updated</h1>
  <p>Your password has been changed. Head back to the ShelfMates app and log in
  with your new password.</p>"""
    return _html_page("Password updated", body)


# ---------------------------------------------------------------------------
# Social sign-in (Apple, Google). The app sends the provider's identity token;
# we verify its signature against the provider's public keys, check the
# audience/issuer, then find-or-create the account keyed on the provider's
# stable subject id. A brand-new social account starts onboarded=False so the
# app routes it to the username/genre onboarding screen.
# ---------------------------------------------------------------------------

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

# PyJWKClient caches fetched keys internally; reuse one per JWKS URL.
_jwks_clients = {}


def _jwks_client(url):
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url)
        _jwks_clients[url] = client
    return client


def _verify_identity_token(token, jwks_url, allowed_auds, allowed_issuers):
    """Verify a provider identity token (RS256, JWKS-signed). Returns the
    claims dict, or raises a jwt exception if anything is off."""
    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=list(allowed_auds),
        options={"require": ["exp", "iat", "sub"]},
    )
    if claims.get("iss") not in allowed_issuers:
        raise jwt.InvalidIssuerError("Unexpected issuer")
    return claims


def _unique_username_from(email):
    """A safe, unique starter username for a new social account. The user
    renames it during onboarding; this just has to be valid and not collide."""
    base = email.split("@")[0] if email else "shelfmate"
    base = re.sub(r"[^A-Za-z0-9_]", "", base)[:20] or "shelfmate"
    candidate = base
    for _ in range(50):
        if not User.query.filter(func.lower(User.username) == candidate.lower()).first():
            return candidate
        candidate = f"{base}{secrets.randbelow(10000)}"
    return f"shelfmate{secrets.token_hex(4)}"


def _email_taken(email, exclude_id=None):
    if not email:
        return False
    q = User.query.filter(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.first() is not None


def _social_login(provider, sub, email, display_name=None):
    """Find-or-create by provider subject id, linking to an existing account
    when the provider gives us a (verified) email that already exists.
    Returns (user, is_new)."""
    sub_col = User.apple_sub if provider == "apple" else User.google_sub
    user = User.query.filter(sub_col == sub).first()
    is_new = False

    # No account for this provider id yet: link to an existing account if the
    # provider handed us an email we already know, else make a new account.
    if not user and email:
        user = User.query.filter(func.lower(User.email) == email.lower()).first()

    if user:
        setattr(user, f"{provider}_sub", sub)
        if email and not user.email and not _email_taken(email, exclude_id=user.id):
            user.email = email
    else:
        is_new = True
        user = User(
            username=_unique_username_from(email),
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            email=email if not _email_taken(email) else None,
            display_name=(display_name or None),
            onboarded=False,
        )
        setattr(user, f"{provider}_sub", sub)
        db.session.add(user)
        db.session.flush()

    ensure_friend_code(user)
    db.session.commit()
    return user, is_new


@auth_bp.route("/apple", methods=["POST"])
def apple_login():
    if _rate_limited(f"social:ip:{_client_ip()}", limit=30, window_seconds=300):
        return jsonify({"message": "Too many attempts. Try again shortly."}), 429
    if not Config.APPLE_CLIENT_IDS:
        return jsonify({
            "message": "Apple sign-in isn't enabled on this server yet",
            "code": "apple_not_configured",
        }), 503

    data = request.get_json(silent=True) or {}
    token = data.get("identity_token") or data.get("id_token")
    if not token or not isinstance(token, str):
        return jsonify({"message": "identity_token required"}), 400

    try:
        claims = _verify_identity_token(
            token, APPLE_JWKS_URL, Config.APPLE_CLIENT_IDS, {APPLE_ISSUER}
        )
    except Exception as e:  # noqa: BLE001 - any verification failure is a 401
        print(f"[apple] token verification failed: {e}")
        return jsonify({"message": "Could not verify Apple token"}), 401

    sub = claims.get("sub")
    # Apple emails are verified by Apple (may be a private-relay address).
    email = (claims.get("email") or "").strip() or None
    if not _valid_email(email or ""):
        email = None
    # Apple sends the name only on first authorization, in the request body.
    display_name = (data.get("full_name") or data.get("name") or "").strip() or None

    user, is_new = _social_login("apple", sub, email, display_name)
    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": access_token,
        "user": user_to_dict(user),
        "is_new": is_new,
    }), 200


@auth_bp.route("/google", methods=["POST"])
def google_login():
    if _rate_limited(f"social:ip:{_client_ip()}", limit=30, window_seconds=300):
        return jsonify({"message": "Too many attempts. Try again shortly."}), 429
    if not Config.GOOGLE_CLIENT_IDS:
        return jsonify({
            "message": "Google sign-in isn't enabled on this server yet",
            "code": "google_not_configured",
        }), 503

    data = request.get_json(silent=True) or {}
    token = data.get("id_token") or data.get("identity_token")
    if not token or not isinstance(token, str):
        return jsonify({"message": "id_token required"}), 400

    try:
        claims = _verify_identity_token(
            token, GOOGLE_JWKS_URL, Config.GOOGLE_CLIENT_IDS, GOOGLE_ISSUERS
        )
    except Exception as e:  # noqa: BLE001
        print(f"[google] token verification failed: {e}")
        return jsonify({"message": "Could not verify Google token"}), 401

    sub = claims.get("sub")
    # Only trust the email for account-linking if Google says it's verified.
    verified = claims.get("email_verified") in (True, "true")
    email = (claims.get("email") or "").strip() or None
    if not (verified and _valid_email(email or "")):
        email = None
    display_name = (claims.get("name") or "").strip() or None

    user, is_new = _social_login("google", sub, email, display_name)
    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": access_token,
        "user": user_to_dict(user),
        "is_new": is_new,
    }), 200
