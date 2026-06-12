"""Device token registration for push notifications."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, DeviceToken

push_bp = Blueprint("push", __name__, url_prefix="/push")

VALID_PLATFORMS = {"ios", "android"}


@push_bp.route("/register", methods=["POST"])
@jwt_required()
def register_token():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()
    platform = (data.get("platform") or "ios").strip().lower()
    if not token:
        return jsonify({"message": "token is required"}), 400
    if platform not in VALID_PLATFORMS:
        return jsonify({"message": f"Invalid platform: {platform}"}), 400

    # A device token can move between accounts (sign out / sign in), so it
    # always belongs to whoever registered it most recently.
    row = DeviceToken.query.filter_by(token=token).first()
    if row:
        row.user_id = me_id
        row.platform = platform
    else:
        db.session.add(
            DeviceToken(user_id=me_id, token=token, platform=platform)
        )
    db.session.commit()
    return jsonify({"message": "registered"}), 200


@push_bp.route("/register", methods=["DELETE"])
@jwt_required()
def unregister_token():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()
    if token:
        DeviceToken.query.filter_by(token=token, user_id=me_id).delete()
        db.session.commit()
    return jsonify({"message": "unregistered"}), 200
