"""Points, achievements, and flair endpoints.

  GET  /achievements/catalog   static ladder + flair catalog (app renders it)
  GET  /me/progress            my points, per-ladder progress, owned/equipped flair
  POST /me/flair/buy           { flair_key }      spend points to own a title
  POST /me/flair/equip         { flair_key|null } show one you own (or clear)
  POST /me/flair/show          { show: bool }     toggle points+flair on profile

Achievements are synced lazily on every /me/progress read, so progress is always
correct even if a real-time hook was missed. Bounded-event points (Movie of the
Week + battles) are granted directly at the event in festival_routes.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, User, UserAchievement, UserFlair
from achievements import (
    LADDERS, FLAIR_BY_KEY, compute_metrics, sync_achievements, catalog_dict,
)

gam_bp = Blueprint("gamification", __name__)


@gam_bp.route("/achievements/catalog", methods=["GET"])
@jwt_required()
def get_catalog():
    return jsonify(catalog_dict()), 200


def _progress_dict(user_id):
    user = User.query.get(user_id)
    metrics = compute_metrics(user_id)
    earned = {
        (ua.ladder_key, ua.tier): ua.earned_at
        for ua in UserAchievement.query.filter_by(user_id=user_id).all()
    }
    owned = [uf.flair_key for uf in UserFlair.query.filter_by(user_id=user_id).all()]

    ladders = []
    for ladder in LADDERS:
        count = metrics.get(ladder["metric"], 0)
        tiers = []
        next_tier = None
        for t in ladder["tiers"]:
            is_earned = (ladder["key"], t["tier"]) in earned
            tiers.append({**t, "earned": is_earned})
            if next_tier is None and not is_earned:
                next_tier = t
        ladders.append({
            "key": ladder["key"], "name": ladder["name"], "motif": ladder["motif"],
            "blocked": ladder["blocked"], "count": count,
            "tiers": tiers, "next_tier": next_tier,
        })

    selected_name = (
        FLAIR_BY_KEY.get(user.flair_selected, {}).get("name")
        if user.flair_selected else None
    )
    return {
        "points": user.points or 0,
        "show_flair": bool(user.show_flair),
        "flair_selected": user.flair_selected,
        "flair_selected_name": selected_name,
        "owned_flair": owned,
        "metrics": metrics,
        "ladders": ladders,
    }


@gam_bp.route("/me/progress", methods=["GET"])
@jwt_required()
def get_progress():
    user_id = int(get_jwt_identity())
    # Lazy sync so tiers are granted/points credited even if a hook was missed.
    newly = sync_achievements(user_id)
    data = _progress_dict(user_id)
    data["newly_earned"] = newly
    return jsonify(data), 200


@gam_bp.route("/me/flair/buy", methods=["POST"])
@jwt_required()
def buy_flair():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    key = (data.get("flair_key") or "").strip()

    flair = FLAIR_BY_KEY.get(key)
    if not flair:
        return jsonify({"message": "Unknown flair"}), 400

    user = User.query.get(user_id)
    if UserFlair.query.filter_by(user_id=user_id, flair_key=key).first():
        return jsonify({"message": "You already own this flair"}), 400
    if (user.points or 0) < flair["price"]:
        return jsonify({"message": "Not enough points", "code": "insufficient_points"}), 402

    user.points -= flair["price"]
    db.session.add(UserFlair(user_id=user_id, flair_key=key))
    db.session.commit()
    return jsonify(_progress_dict(user_id)), 200


@gam_bp.route("/me/flair/equip", methods=["POST"])
@jwt_required()
def equip_flair():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    key = data.get("flair_key")

    user = User.query.get(user_id)
    if key is None or key == "":
        user.flair_selected = None
    else:
        if not UserFlair.query.filter_by(user_id=user_id, flair_key=key).first():
            return jsonify({"message": "You don't own that flair"}), 400
        user.flair_selected = key
    db.session.commit()
    return jsonify(_progress_dict(user_id)), 200


@gam_bp.route("/me/flair/show", methods=["POST"])
@jwt_required()
def toggle_show_flair():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    user = User.query.get(user_id)
    user.show_flair = bool(data.get("show"))
    db.session.commit()
    return jsonify({"show_flair": user.show_flair}), 200
