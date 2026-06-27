"""
Spoiler-safe friend discussions on books — chapter-gated, friends-only.

The mechanic (two gates, both enforced HERE, never client-side):
  POST gate: a comment's chapter can't exceed the poster's own
             chapter_progress on that book. You can't spoil past where
             you've read.
  READ gate: a reader only receives comments tagged <= their own
             chapter_progress. Comments ahead of them are returned as a
             locked teaser (chapters + count only, never the body).

Visibility follows the friendship graph: each reader sees comments from
THEIR friends (plus their own). Having the book on your list is the only
membership required — the "book club" materializes when friends share a
book.

Endpoints (JWT required):
  GET    /discussions/book/<work_id>      thread, gated for the caller
  POST   /discussions/book/<work_id>      { chapter, body }
  DELETE /discussions/comment/<id>        own comments only
"""

from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, and_

from push import notify
from models import db, User, WatchlistItem, Friendship, DiscussionComment


discussion_bp = Blueprint("discussions", __name__, url_prefix="/discussions")

# Books only for v1. TV-by-episode is a natural fast-follow; widening this
# set (plus a client UI) is the whole change.
DISCUSSABLE_TYPES = {"book"}

MAX_BODY_LEN = 2000


def _friend_ids(me_id):
    rows = Friendship.query.filter(
        or_(Friendship.requester_id == me_id, Friendship.addressee_id == me_id),
        Friendship.status == "accepted",
    ).all()
    return {
        f.addressee_id if f.requester_id == me_id else f.requester_id
        for f in rows
    }


def _my_item(me_id, media_type, external_id):
    return WatchlistItem.query.filter_by(
        user_id=me_id, imdb_id=external_id, media_type=media_type
    ).first()


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


@discussion_bp.route("/<media_type>/<external_id>", methods=["GET"])
@jwt_required()
def get_discussion(media_type, external_id):
    me_id = int(get_jwt_identity())
    if media_type not in DISCUSSABLE_TYPES:
        return jsonify({"message": f"Discussions not available for {media_type}"}), 400

    my_item = _my_item(me_id, media_type, external_id)
    if not my_item:
        # The shelf is the membership card — no item, no discussion access.
        return jsonify({"message": "Add this to your list to join the discussion"}), 403

    my_progress = my_item.chapter_progress or 0
    friends = _friend_ids(me_id)

    # Friends who also have this book, with their progress (positions are
    # never spoilers — they're motivation)
    readers = []
    if friends:
        friend_items = (
            WatchlistItem.query
            .filter(
                WatchlistItem.user_id.in_(friends),
                WatchlistItem.imdb_id == external_id,
                WatchlistItem.media_type == media_type,
            ).all()
        )
        reader_users = {
            u.id: u for u in User.query.filter(
                User.id.in_([i.user_id for i in friend_items])
            ).all()
        } if friend_items else {}
        readers = [{
            "user": _user_summary(reader_users.get(i.user_id)),
            "chapter_progress": i.chapter_progress or 0,
        } for i in friend_items]

    visible_ids = friends | {me_id}
    all_comments = (
        DiscussionComment.query
        .filter(
            DiscussionComment.imdb_id == external_id,
            DiscussionComment.media_type == media_type,
            DiscussionComment.user_id.in_(visible_ids),
        )
        .order_by(DiscussionComment.chapter.asc(), DiscussionComment.created_at.asc())
        .all()
    )

    commenters = {
        u.id: u for u in User.query.filter(
            User.id.in_({c.user_id for c in all_comments})
        ).all()
    } if all_comments else {}

    visible, locked_chapters = [], []
    for c in all_comments:
        # READ gate: own comments always visible; friends' only at/below my progress
        if c.user_id == me_id or c.chapter <= my_progress:
            visible.append({
                "id": c.id,
                "user": _user_summary(commenters.get(c.user_id)),
                "chapter": c.chapter,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "mine": c.user_id == me_id,
            })
        else:
            # Teaser only: WHERE the conversation is, never WHAT it says
            locked_chapters.append(c.chapter)

    return jsonify({
        "my_progress": my_progress,
        "readers": readers,
        "comments": visible,
        "locked": {
            "count": len(locked_chapters),
            "chapters": sorted(set(locked_chapters)),
        },
    }), 200


@discussion_bp.route("/<media_type>/<external_id>", methods=["POST"])
@jwt_required()
def post_comment(media_type, external_id):
    me_id = int(get_jwt_identity())
    if media_type not in DISCUSSABLE_TYPES:
        return jsonify({"message": f"Discussions not available for {media_type}"}), 400

    my_item = _my_item(me_id, media_type, external_id)
    if not my_item:
        return jsonify({"message": "Add this to your list to join the discussion"}), 403

    data = request.get_json(silent=True) or {}
    try:
        chapter = int(data.get("chapter"))
    except (TypeError, ValueError):
        return jsonify({"message": "chapter must be a number"}), 400
    if chapter < 1:
        return jsonify({"message": "chapter must be 1 or higher"}), 400

    my_progress = my_item.chapter_progress or 0
    # POST gate: you can't comment ahead of your own reading position
    if chapter > my_progress:
        return jsonify({
            "message": f"You're on chapter {my_progress} — update your progress before commenting on chapter {chapter}",
            "code": "ahead_of_progress",
        }), 400

    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"message": "Comment can't be empty"}), 400
    if len(body) > MAX_BODY_LEN:
        return jsonify({"message": f"Comment too long (max {MAX_BODY_LEN} characters)"}), 400

    comment = DiscussionComment(
        user_id=me_id,
        imdb_id=external_id,
        media_type=media_type,
        chapter=chapter,
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    user = User.query.get(me_id)

    # Notify friends who share this book AND have read at least this far.
    # Same spoiler gate as the read path: nobody hears about a chapter they
    # have not reached.
    friend_ids = _friend_ids(me_id)
    if friend_ids:
        eligible = WatchlistItem.query.filter(
            WatchlistItem.user_id.in_(friend_ids),
            WatchlistItem.imdb_id == external_id,
            WatchlistItem.media_type == media_type,
            WatchlistItem.chapter_progress >= chapter,
        ).all()
        book_title = my_item.title or "a book you're reading"
        poster_name = (user.display_name or user.username) if user else "A friend"
        notify(
            [it.user_id for it in eligible],
            f"{poster_name} \u00b7 {book_title} ch {chapter}",
            comment.body[:100],
            category="discussions",
        )
    return jsonify({
        "id": comment.id,
        "user": _user_summary(user),
        "chapter": comment.chapter,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
        "mine": True,
    }), 201


@discussion_bp.route("/comment/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    me_id = int(get_jwt_identity())
    comment = DiscussionComment.query.get(comment_id)
    if not comment or comment.user_id != me_id:
        return jsonify({"message": "Comment not found"}), 404
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"message": "Comment deleted"}), 200
