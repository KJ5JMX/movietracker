from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, WatchlistItem


watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")


def item_to_dict(item):
    return {
        "id": item.id,
        "title": item.title,
        "year": item.year,
        "imdb_id": item.imdb_id,
        "movie_type": item.movie_type,
        "plot": item.plot,
        "poster": item.poster,
        "watch_status": item.watch_status,
        "rating": item.rating,
        "notes": item.notes,
    }


@watchlist_bp.route("/", methods=["GET"])
@jwt_required()
def get_watchlist():
    user_id = int(get_jwt_identity())
    items = WatchlistItem.query.filter_by(user_id=user_id).all()
    return jsonify([item_to_dict(item) for item in items]), 200


@watchlist_bp.route("/", methods=["POST"])
@jwt_required()
def add_to_watchlist():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    imdb_id = data.get("imdb_id")
    if not imdb_id:
        return jsonify({"message": "imdb_id is required"}), 400

    existing = WatchlistItem.query.filter_by(user_id=user_id, imdb_id=imdb_id).first()
    if existing:
        return jsonify({"message": "Movie already in watchlist"}), 400

    new_item = WatchlistItem(
        title=data.get("title"),
        year=data.get("year"),
        imdb_id=imdb_id,
        movie_type=data.get("movie_type"),
        plot=data.get("plot"),
        poster=data.get("poster"),
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

    data = request.get_json()
    item.watch_status = data.get("watch_status", item.watch_status)
    item.rating = data.get("rating", item.rating)
    item.notes = data.get("notes", item.notes)
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
