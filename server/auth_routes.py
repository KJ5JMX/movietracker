import json
import secrets
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User


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
        "genres": _parse_genres(user.genres),
    }


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
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
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

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

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted"}), 200
