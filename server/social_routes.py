"""
Friend system, recommendations, and review shares.

Endpoints:
  Friends:
    GET    /friends/                  list accepted friends
    GET    /friends/requests          pending incoming friend requests
    POST   /friends/request           body: { friend_code } — send request
    POST   /friends/<id>/accept       accept pending request
    POST   /friends/<id>/decline      decline pending request
    DELETE /friends/<id>              remove friendship

  Recommendations:
    GET    /recs/                     pending incoming recs
    POST   /recs/                     body: { to_user_id, imdb_id, media_type, title, year?, poster?, genre?, note? }
    POST   /recs/<id>/accept          adds to my watchlist + marks accepted
    POST   /recs/<id>/decline         marks declined

  Review shares:
    GET    /reviews/                  unread incoming review shares
    POST   /reviews/                  body: { to_user_id, imdb_id, title, poster?, rating?, review_text?, rec_id? }
    POST   /reviews/<id>/read         mark as read

  Notifications:
    GET    /notifications/count       { recs, reviews, friend_requests, total }
"""

from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, and_

from models import db, User, Friendship, Recommendation, ReviewShare, WatchlistItem


social_bp = Blueprint("social", __name__)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def user_summary(user):
    """Public-safe view of a user — used for friend lists, rec senders, etc."""
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def friendship_to_dict(f, me_id):
    other_id = f.addressee_id if f.requester_id == me_id else f.requester_id
    other = User.query.get(other_id)
    return {
        "friendship_id": f.id,
        "user": user_summary(other),
        "status": f.status,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def friend_request_to_dict(f):
    """For inbound requests, always show the requester."""
    return {
        "friendship_id": f.id,
        "from_user": user_summary(User.query.get(f.requester_id)),
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def rec_to_dict(r):
    return {
        "id": r.id,
        "from_user": user_summary(User.query.get(r.from_user_id)),
        "imdb_id": r.imdb_id,
        "media_type": r.media_type,
        "title": r.title,
        "year": r.year,
        "poster": r.poster,
        "genre": r.genre,
        "note": r.note,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def review_to_dict(rv):
    return {
        "id": rv.id,
        "from_user": user_summary(User.query.get(rv.from_user_id)),
        "imdb_id": rv.imdb_id,
        "title": rv.title,
        "poster": rv.poster,
        "rating": rv.rating,
        "review_text": rv.review_text,
        "rec_id": rv.rec_id,
        "status": rv.status,
        "created_at": rv.created_at.isoformat() if rv.created_at else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def are_friends(user_a_id, user_b_id):
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


def existing_friendship(user_a_id, user_b_id):
    """Return any existing Friendship row between two users, regardless of direction or status."""
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
    ).first()


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------

@social_bp.route("/friends/", methods=["GET"])
@jwt_required()
def list_friends():
    me_id = int(get_jwt_identity())
    friendships = Friendship.query.filter(
        or_(
            Friendship.requester_id == me_id,
            Friendship.addressee_id == me_id,
        ),
        Friendship.status == "accepted",
    ).all()
    return jsonify([friendship_to_dict(f, me_id) for f in friendships]), 200


@social_bp.route("/friends/requests", methods=["GET"])
@jwt_required()
def list_friend_requests():
    me_id = int(get_jwt_identity())
    requests_ = Friendship.query.filter(
        Friendship.addressee_id == me_id,
        Friendship.status == "pending",
    ).all()
    return jsonify([friend_request_to_dict(f) for f in requests_]), 200


@social_bp.route("/friends/request", methods=["POST"])
@jwt_required()
def send_friend_request():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}
    code = (data.get("friend_code") or "").strip().upper()
    if not code:
        return jsonify({"message": "friend_code required"}), 400

    target = User.query.filter_by(friend_code=code).first()
    if not target:
        return jsonify({"message": "No user with that code"}), 404

    if target.id == me_id:
        return jsonify({"message": "Can't friend yourself"}), 400

    existing = existing_friendship(me_id, target.id)
    if existing:
        if existing.status == "accepted":
            return jsonify({"message": "Already friends"}), 400
        if existing.status == "pending":
            # If THEY sent to ME already, auto-accept (treat as mutual)
            if existing.addressee_id == me_id:
                existing.status = "accepted"
                existing.accepted_at = datetime.utcnow()
                db.session.commit()
                return jsonify({
                    "message": "Friend request accepted",
                    "friendship": friendship_to_dict(existing, me_id),
                }), 200
            return jsonify({"message": "Friend request already sent"}), 400

    f = Friendship(
        requester_id=me_id,
        addressee_id=target.id,
        status="pending",
    )
    db.session.add(f)
    db.session.commit()
    return jsonify({
        "message": "Friend request sent",
        "friendship_id": f.id,
        "to_user": user_summary(target),
    }), 201


@social_bp.route("/friends/<int:friendship_id>/accept", methods=["POST"])
@jwt_required()
def accept_friend_request(friendship_id):
    me_id = int(get_jwt_identity())
    f = Friendship.query.get(friendship_id)
    if not f or f.addressee_id != me_id:
        return jsonify({"message": "Request not found"}), 404
    if f.status != "pending":
        return jsonify({"message": f"Request is {f.status}"}), 400
    f.status = "accepted"
    f.accepted_at = datetime.utcnow()
    db.session.commit()
    return jsonify(friendship_to_dict(f, me_id)), 200


@social_bp.route("/friends/<int:friendship_id>/decline", methods=["POST"])
@jwt_required()
def decline_friend_request(friendship_id):
    me_id = int(get_jwt_identity())
    f = Friendship.query.get(friendship_id)
    if not f or f.addressee_id != me_id:
        return jsonify({"message": "Request not found"}), 404
    if f.status != "pending":
        return jsonify({"message": f"Request is {f.status}"}), 400
    db.session.delete(f)
    db.session.commit()
    return jsonify({"message": "Request declined"}), 200


@social_bp.route("/friends/<int:friendship_id>", methods=["DELETE"])
@jwt_required()
def remove_friend(friendship_id):
    me_id = int(get_jwt_identity())
    f = Friendship.query.get(friendship_id)
    if not f or (f.requester_id != me_id and f.addressee_id != me_id):
        return jsonify({"message": "Friendship not found"}), 404
    db.session.delete(f)
    db.session.commit()
    return jsonify({"message": "Friendship removed"}), 200


# ---------------------------------------------------------------------------
# Friend activity — everything me and one friend share, for the tappable
# username view in the app.
# ---------------------------------------------------------------------------

@social_bp.route("/friends/<int:user_id>/activity", methods=["GET"])
@jwt_required()
def friend_activity(user_id):
    me_id = int(get_jwt_identity())
    friend = User.query.get(user_id)
    if not friend:
        return jsonify({"message": "User not found"}), 404
    if not are_friends(me_id, user_id):
        return jsonify({"message": "You're not friends with this user"}), 403

    # Recs + reviews exchanged, both directions
    recs_from_them = (
        Recommendation.query
        .filter_by(from_user_id=user_id, to_user_id=me_id)
        .order_by(Recommendation.created_at.desc()).limit(50).all()
    )
    recs_to_them = (
        Recommendation.query
        .filter_by(from_user_id=me_id, to_user_id=user_id)
        .order_by(Recommendation.created_at.desc()).limit(50).all()
    )
    reviews_from_them = (
        ReviewShare.query
        .filter_by(from_user_id=user_id, to_user_id=me_id)
        .order_by(ReviewShare.created_at.desc()).limit(50).all()
    )
    reviews_to_them = (
        ReviewShare.query
        .filter_by(from_user_id=me_id, to_user_id=user_id)
        .order_by(ReviewShare.created_at.desc()).limit(50).all()
    )

    # Movie nights where BOTH of us were participants
    from models import MovieNightSession, MovieNightParticipant
    my_sessions = {
        p.session_id
        for p in MovieNightParticipant.query.filter_by(user_id=me_id).all()
    }
    shared_parts = (
        MovieNightParticipant.query
        .filter(
            MovieNightParticipant.user_id == user_id,
            MovieNightParticipant.session_id.in_(my_sessions),
        ).all()
        if my_sessions else []
    )
    nights = []
    if shared_parts:
        their_ratings = {p.session_id: p.rating for p in shared_parts}
        my_parts = MovieNightParticipant.query.filter(
            MovieNightParticipant.user_id == me_id,
            MovieNightParticipant.session_id.in_(list(their_ratings.keys())),
        ).all()
        my_ratings = {p.session_id: p.rating for p in my_parts}
        sessions = (
            MovieNightSession.query
            .filter(MovieNightSession.id.in_(list(their_ratings.keys())))
            .order_by(MovieNightSession.created_at.desc()).limit(50).all()
        )
        nights = [{
            "id": s.id,
            "title": s.picked_title,
            "year": s.picked_year,
            "poster": s.picked_poster,
            "media_type": s.picked_media_type,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "my_rating": my_ratings.get(s.id),
            "their_rating": their_ratings.get(s.id),
        } for s in sessions]

    # Their recent additions — but a 'private' friend's shelf stays private.
    # Mutual exchanges (recs/reviews/nights) always show: both parties own those.
    is_private = friend.privacy_mode == "private"
    recent_items = []
    if not is_private:
        items = (
            WatchlistItem.query
            .filter_by(user_id=user_id)
            .order_by(WatchlistItem.id.desc()).limit(20).all()
        )
        recent_items = [{
            "imdb_id": i.imdb_id,
            "title": i.title,
            "year": i.year,
            "poster": i.poster,
            "media_type": i.media_type,
            "watch_status": i.watch_status,
            "rating": i.rating,
        } for i in items]

    return jsonify({
        "user": user_summary(friend),
        "is_private": is_private,
        "recs_from_them": [rec_to_dict(r) for r in recs_from_them],
        "recs_to_them": [rec_to_dict(r) for r in recs_to_them],
        "reviews_from_them": [review_to_dict(rv) for rv in reviews_from_them],
        "reviews_to_them": [review_to_dict(rv) for rv in reviews_to_them],
        "nights_together": nights,
        "recent_items": recent_items,
    }), 200


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

@social_bp.route("/recs/", methods=["GET"])
@jwt_required()
def list_recs():
    me_id = int(get_jwt_identity())
    recs = (
        Recommendation.query
        .filter(Recommendation.to_user_id == me_id, Recommendation.status == "pending")
        .order_by(Recommendation.created_at.desc())
        .all()
    )
    return jsonify([rec_to_dict(r) for r in recs]), 200


@social_bp.route("/recs/", methods=["POST"])
@jwt_required()
def send_rec():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}

    to_user_id = data.get("to_user_id")
    imdb_id = data.get("imdb_id")
    title = data.get("title")
    if not (to_user_id and imdb_id and title):
        return jsonify({"message": "to_user_id, imdb_id, and title required"}), 400

    try:
        to_user_id = int(to_user_id)
    except (TypeError, ValueError):
        return jsonify({"message": "to_user_id must be an integer"}), 400

    if not are_friends(me_id, to_user_id):
        return jsonify({"message": "Can only recommend to friends"}), 403

    media_type = data.get("media_type", "movie")
    if media_type not in {"movie", "tv", "song", "book"}:
        return jsonify({"message": f"Invalid media_type: {media_type}"}), 400

    rec = Recommendation(
        from_user_id=me_id,
        to_user_id=to_user_id,
        imdb_id=imdb_id,
        media_type=media_type,
        title=title,
        year=data.get("year"),
        poster=data.get("poster"),
        genre=data.get("genre"),
        note=(data.get("note") or "").strip() or None,
        status="pending",
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify(rec_to_dict(rec)), 201


@social_bp.route("/recs/<int:rec_id>/accept", methods=["POST"])
@jwt_required()
def accept_rec(rec_id):
    me_id = int(get_jwt_identity())
    rec = Recommendation.query.get(rec_id)
    if not rec or rec.to_user_id != me_id:
        return jsonify({"message": "Recommendation not found"}), 404
    if rec.status != "pending":
        return jsonify({"message": f"Already {rec.status}"}), 400

    # If user already has this item in their watchlist, just mark the rec accepted
    existing = WatchlistItem.query.filter_by(
        user_id=me_id, imdb_id=rec.imdb_id, media_type=rec.media_type
    ).first()
    if existing:
        # Still attribute it to the friend, if it wasn't already
        if not existing.recommended_by_user_id:
            existing.recommended_by_user_id = rec.from_user_id
        rec.status = "accepted"
        db.session.commit()
        return jsonify({"message": "Item already in your list; attributed to friend"}), 200

    new_item = WatchlistItem(
        title=rec.title,
        year=rec.year,
        imdb_id=rec.imdb_id,
        movie_type=None,
        media_type=rec.media_type,
        plot=None,
        poster=rec.poster,
        genre=rec.genre,
        watch_status="want_to_watch",
        user_id=me_id,
        recommended_by_user_id=rec.from_user_id,
    )
    db.session.add(new_item)
    rec.status = "accepted"
    db.session.commit()

    return jsonify({
        "message": "Added to your list",
        "watchlist_item_id": new_item.id,
    }), 201


@social_bp.route("/recs/<int:rec_id>/decline", methods=["POST"])
@jwt_required()
def decline_rec(rec_id):
    me_id = int(get_jwt_identity())
    rec = Recommendation.query.get(rec_id)
    if not rec or rec.to_user_id != me_id:
        return jsonify({"message": "Recommendation not found"}), 404
    if rec.status != "pending":
        return jsonify({"message": f"Already {rec.status}"}), 400
    rec.status = "declined"
    db.session.commit()
    return jsonify({"message": "Declined"}), 200


# ---------------------------------------------------------------------------
# Review shares
# ---------------------------------------------------------------------------

@social_bp.route("/reviews/", methods=["GET"])
@jwt_required()
def list_reviews():
    me_id = int(get_jwt_identity())
    reviews = (
        ReviewShare.query
        .filter(ReviewShare.to_user_id == me_id)
        .order_by(ReviewShare.created_at.desc())
        .all()
    )
    return jsonify([review_to_dict(rv) for rv in reviews]), 200


@social_bp.route("/reviews/", methods=["POST"])
@jwt_required()
def send_review():
    me_id = int(get_jwt_identity())
    data = request.get_json() or {}

    to_user_id = data.get("to_user_id")
    imdb_id = data.get("imdb_id")
    title = data.get("title")
    if not (to_user_id and imdb_id and title):
        return jsonify({"message": "to_user_id, imdb_id, and title required"}), 400

    try:
        to_user_id = int(to_user_id)
    except (TypeError, ValueError):
        return jsonify({"message": "to_user_id must be an integer"}), 400

    if not are_friends(me_id, to_user_id):
        return jsonify({"message": "Can only share with friends"}), 403

    # rec_id is optional; only accept it if it points at a real rec that was
    # actually sent to me. Anything else (bad id, someone else's rec) is
    # silently dropped rather than stored as a dangling/forged link.
    rec_id = data.get("rec_id")
    if rec_id is not None:
        try:
            rec_id = int(rec_id)
        except (TypeError, ValueError):
            rec_id = None
        else:
            rec = Recommendation.query.get(rec_id)
            if not rec or rec.to_user_id != me_id:
                rec_id = None

    rating = data.get("rating")
    if rating is not None:
        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                rating = None
        except (TypeError, ValueError):
            rating = None

    review = ReviewShare(
        from_user_id=me_id,
        to_user_id=to_user_id,
        rec_id=rec_id,
        imdb_id=imdb_id,
        title=title,
        poster=data.get("poster"),
        rating=rating,
        review_text=(data.get("review_text") or "").strip() or None,
        status="unread",
    )
    db.session.add(review)
    db.session.commit()
    return jsonify(review_to_dict(review)), 201


@social_bp.route("/reviews/<int:review_id>/read", methods=["POST"])
@jwt_required()
def mark_review_read(review_id):
    me_id = int(get_jwt_identity())
    rv = ReviewShare.query.get(review_id)
    if not rv or rv.to_user_id != me_id:
        return jsonify({"message": "Review not found"}), 404
    rv.status = "read"
    db.session.commit()
    return jsonify(review_to_dict(rv)), 200


# ---------------------------------------------------------------------------
# Notifications count (for the Recs badge)
# ---------------------------------------------------------------------------

@social_bp.route("/notifications/count", methods=["GET"])
@jwt_required()
def notifications_count():
    me_id = int(get_jwt_identity())
    pending_recs = Recommendation.query.filter_by(
        to_user_id=me_id, status="pending"
    ).count()
    unread_reviews = ReviewShare.query.filter_by(
        to_user_id=me_id, status="unread"
    ).count()
    pending_friends = Friendship.query.filter_by(
        addressee_id=me_id, status="pending"
    ).count()
    return jsonify({
        "recs": pending_recs,
        "reviews": unread_reviews,
        "friend_requests": pending_friends,
        "total": pending_recs + unread_reviews + pending_friends,
    }), 200
