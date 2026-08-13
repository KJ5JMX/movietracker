"""Pro avatar shop: the app-facing catalog + image serving.

Pro avatars live in the DB as base64 PNG data (ProAvatar.image_full_data /
image_head_data). This blueprint exposes:

  GET /pro-avatars                  -> the revolving shop (active + on a slot)
  GET /pro-avatars/<key>/full.png   -> the full character image bytes
  GET /pro-avatars/<key>/head.png   -> the circular headshot crop bytes

The image routes are intentionally unauthenticated so React Native's <Image>
can load and OS-cache them by URL like any other remote image. Admin upload +
management lives on admin_bp (festival_routes), behind require_admin.
"""

import base64
from flask import Blueprint, jsonify, Response, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from models import db, ProAvatar, User, UserAvatar, CoinLedger

cosmetics_bp = Blueprint("cosmetics", __name__)


def _strip_data_uri(s):
    """Accept either raw base64 or a 'data:image/png;base64,...' data URI."""
    if not s:
        return s
    if s[:5] == "data:" and "," in s:
        return s.split(",", 1)[1]
    return s


def pro_avatar_to_dict(a, owned=False):
    return {
        "key": a.key,
        "name": a.name,
        "coin_price": a.coin_price,
        "artist_credit": a.artist_credit,
        "slot": a.slot,
        "owned": bool(owned),
        # False once it rotates out of the shop. Owners keep it forever; it just
        # moves out of the current drop and can no longer be bought by anyone.
        "in_shop": bool(a.is_active and a.slot is not None),
        # URLs the app loads directly; served by the routes below.
        "image_full_url": f"/pro-avatars/{a.key}/full.png",
        "image_head_url": f"/pro-avatars/{a.key}/head.png",
    }


@cosmetics_bp.route("/pro-avatars", methods=["GET"])
@jwt_required()
def list_pro_avatars():
    """The revolving Pro shop, plus everything this user already owns.

    Two groups come back in one list, distinguished by `in_shop`:
      - the current drop (active + on a slot), buyable by anyone
      - avatars this user owns, including ones since rotated out, so their
        purchases never disappear from the shop screen

    Retired avatars nobody owns are simply absent -- there is nothing to show
    and nothing to buy.
    """
    uid = int(get_jwt_identity())
    owned_keys = {
        ua.avatar_key
        for ua in UserAvatar.query.filter_by(user_id=uid).all()
    }

    in_shop = (
        ProAvatar.query
        .filter(ProAvatar.is_active.is_(True), ProAvatar.slot.isnot(None))
        .order_by(ProAvatar.slot.asc(), ProAvatar.sort_order.asc())
        .all()
    )
    shown = {a.key for a in in_shop}

    owned_retired = []
    if owned_keys:
        owned_retired = (
            ProAvatar.query
            .filter(ProAvatar.key.in_(owned_keys), ProAvatar.key.notin_(shown or [""]))
            .order_by(ProAvatar.sort_order.asc(), ProAvatar.id.asc())
            .all()
        )

    out = [pro_avatar_to_dict(a, a.key in owned_keys) for a in in_shop]
    out += [pro_avatar_to_dict(a, True) for a in owned_retired]
    return jsonify(out), 200


def _serve_image(key, which):
    a = ProAvatar.query.filter_by(key=key).first()
    if not a:
        return jsonify({"message": "Avatar not found"}), 404
    raw_b64 = a.image_full_data if which == "full" else a.image_head_data
    raw_b64 = _strip_data_uri(raw_b64)
    if not raw_b64:
        return jsonify({"message": "No image"}), 404
    try:
        raw = base64.b64decode(raw_b64)
    except Exception:
        return jsonify({"message": "Bad image data"}), 500
    resp = Response(raw, mimetype="image/png")
    # Immutable-ish: a given key's art doesn't change, so let clients cache hard.
    resp.headers["Cache-Control"] = "public, max-age=604800"
    return resp


@cosmetics_bp.route("/pro-avatars/<key>/full.png", methods=["GET"])
def pro_avatar_full(key):
    return _serve_image(key, "full")


@cosmetics_bp.route("/pro-avatars/<key>/head.png", methods=["GET"])
def pro_avatar_head(key):
    return _serve_image(key, "head")


# ===========================================================================
# Coin economy — balance, lazy Pro grants, buying avatars, gifting a coin
# ===========================================================================

def _credit(user, delta, reason, ref=None):
    """Move `delta` coins on `user` and append a ledger row. Positive = grant/
    purchase, negative = spend/gift. Caller commits."""
    user.coins = (user.coins or 0) + delta
    db.session.add(CoinLedger(
        user_id=user.id, delta=delta, reason=reason, ref=ref,
        balance_after=user.coins,
    ))
    return user.coins


def _apply_pro_grants(user):
    """Lazy grants run when a Pro user checks their balance: the one-time
    3-coin signup bonus and the monthly coin (once per calendar month).
    Idempotent via the flag + timestamp on the user."""
    if not user or not user.is_pro:
        return
    changed = False
    if not user.coin_signup_bonus_granted:
        _credit(user, 3, "signup_bonus")
        user.coin_signup_bonus_granted = True
        changed = True
    now = datetime.utcnow()
    last = user.coin_last_monthly_grant
    if last is None or (last.year, last.month) != (now.year, now.month):
        _credit(user, 1, "monthly_grant")
        user.coin_last_monthly_grant = now
        changed = True
    if changed:
        db.session.commit()


@cosmetics_bp.route("/coins", methods=["GET"])
@jwt_required()
def get_coins():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user:
        return jsonify({"message": "User not found"}), 404
    _apply_pro_grants(user)
    return jsonify({"coins": user.coins or 0, "is_pro": user.is_pro}), 200


@cosmetics_bp.route("/pro-avatars/<key>/buy", methods=["POST"])
@jwt_required()
def buy_pro_avatar(key):
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user:
        return jsonify({"message": "User not found"}), 404
    a = ProAvatar.query.filter_by(key=key).first()
    if not a or not a.is_active:
        return jsonify({"message": "Avatar not available"}), 404
    if UserAvatar.query.filter_by(user_id=uid, avatar_key=key).first():
        return jsonify({"message": "Already owned", "coins": user.coins or 0}), 200
    price = a.coin_price or 0
    if (user.coins or 0) < price:
        return jsonify({
            "message": "Not enough plot coins.",
            "code": "insufficient_coins",
            "coins": user.coins or 0,
            "price": price,
        }), 402
    _credit(user, -price, "spend", ref=key)
    db.session.add(UserAvatar(user_id=uid, avatar_key=key, pool="pro"))
    user.avatar_selected = key  # equip immediately, like the free avatar shop
    db.session.commit()
    return jsonify({"ok": True, "coins": user.coins or 0, "owned_key": key}), 200


@cosmetics_bp.route("/coins/gift", methods=["POST"])
@jwt_required()
def gift_coin():
    """A Pro user gifts a coin to a free friend, who gets a 1-month Pro trial.
    Self-limiting: one gift per Pro user per calendar month."""
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user:
        return jsonify({"message": "User not found"}), 404
    if not user.is_pro:
        return jsonify({"message": "Only Pro members can gift a coin."}), 403
    data = request.get_json(silent=True) or {}
    friend = User.query.get(data.get("friend_id")) if data.get("friend_id") else None
    if not friend or friend.id == user.id:
        return jsonify({"message": "Pick a friend to gift."}), 400
    if friend.is_pro:
        return jsonify({"message": "They're already Pro."}), 400
    now = datetime.utcnow()
    last = user.coin_gift_last_grant
    if last is not None and (last.year, last.month) == (now.year, now.month):
        return jsonify({"message": "You've already gifted a coin this month."}), 400
    if (user.coins or 0) < 1:
        return jsonify({
            "message": "You need a coin to gift.",
            "code": "insufficient_coins",
        }), 402
    _credit(user, -1, "gift_sent", ref=str(friend.id))
    user.coin_gift_last_grant = now
    friend.pro_status = "trial"
    friend.pro_expires_at = now + timedelta(days=30)
    db.session.commit()
    return jsonify({"ok": True, "coins": user.coins or 0}), 200
