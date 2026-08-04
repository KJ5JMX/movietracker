"""Friend book club — an ungated group chat on a shared book.

Model (all enforced HERE, server-side):
  Membership: the book has to be on your list to read and post. Your shelf is
              the membership card; the club materializes when friends share a
              book.
  Visibility: you see every comment from YOUR friends (and yourself) on that
              book. No chapter gate — the chat is one shared room.
  Spoilers:   opt-in and per-message. A comment can carry is_spoiler=true, and
              the client covers it until the reader taps to reveal. The body is
              still sent; a spoiler flag is a courtesy, not a lock.
  The race:   who's furthest along, and who finished first, is read off each
              reader's WatchlistItem (chapter_progress + watch_status). Marking
              the book Read (watch_status == 'watched') is crossing the line —
              first to do it wins. Positions are motivation, never a gate.

Endpoints (JWT required):
  GET    /discussions/<media_type>/<external_id>   thread + readers + reactions
  POST   /discussions/<media_type>/<external_id>   { body, is_spoiler?, chapter? }
  POST   /discussions/comment/<id>/react           { emoji }  (toggle)
  DELETE /discussions/comment/<id>                 own comments only
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from push import notify
from models import (
    db,
    User,
    WatchlistItem,
    Friendship,
    DiscussionComment,
    DiscussionReaction,
)


discussion_bp = Blueprint("discussions", __name__, url_prefix="/discussions")

# Books only for v1. TV-by-episode is a natural fast-follow; widening this
# set (plus a client UI) is the whole change.
DISCUSSABLE_TYPES = {"book"}

MAX_BODY_LEN = 2000
MAX_EMOJI_LEN = 16
FINISHED_STATUS = "watched"  # books label this "Read"


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


def _reactions_for(comment_ids, visible_ids, me_id):
    """Tally reactions per comment, counting only friends-and-me.

    Returns { comment_id: [ {emoji, count, reacted}, ... ] }, emojis ordered by
    first-seen so the row is stable. `reacted` is whether the caller is in the
    tally for that emoji.
    """
    if not comment_ids:
        return {}
    rows = (
        DiscussionReaction.query
        .filter(
            DiscussionReaction.comment_id.in_(comment_ids),
            DiscussionReaction.user_id.in_(visible_ids),
        )
        .order_by(DiscussionReaction.id.asc())
        .all()
    )
    out = {}
    for r in rows:
        by_emoji = out.setdefault(r.comment_id, {})
        entry = by_emoji.get(r.emoji)
        if entry is None:
            entry = {"emoji": r.emoji, "count": 0, "reacted": False}
            by_emoji[r.emoji] = entry
        entry["count"] += 1
        if r.user_id == me_id:
            entry["reacted"] = True
    return {cid: list(emap.values()) for cid, emap in out.items()}


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
    my_finished = my_item.watch_status == FINISHED_STATUS
    my_finished_at = my_item.watched_at.isoformat() if my_item.watched_at else None
    friends = _friend_ids(me_id)

    # Friends who also have this book, with their race position. Positions are
    # never spoilers — they're motivation. finished_at is how we rank the win.
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
        for i in friend_items:
            readers.append({
                "user": _user_summary(reader_users.get(i.user_id)),
                "chapter_progress": i.chapter_progress or 0,
                "finished": i.watch_status == FINISHED_STATUS,
                "finished_at": i.watched_at.isoformat() if i.watched_at else None,
            })

    visible_ids = friends | {me_id}
    all_comments = (
        DiscussionComment.query
        .filter(
            DiscussionComment.imdb_id == external_id,
            DiscussionComment.media_type == media_type,
            DiscussionComment.user_id.in_(visible_ids),
        )
        .order_by(DiscussionComment.created_at.asc())
        .all()
    )

    commenters = {
        u.id: u for u in User.query.filter(
            User.id.in_({c.user_id for c in all_comments})
        ).all()
    } if all_comments else {}

    reactions = _reactions_for(
        [c.id for c in all_comments], visible_ids, me_id
    )

    comments = [{
        "id": c.id,
        "user": _user_summary(commenters.get(c.user_id)),
        "chapter": c.chapter,
        "body": c.body,
        "is_spoiler": bool(c.is_spoiler),
        "reactions": reactions.get(c.id, []),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "mine": c.user_id == me_id,
    } for c in all_comments]

    return jsonify({
        "my_progress": my_progress,
        "my_finished": my_finished,
        "my_finished_at": my_finished_at,
        "readers": readers,
        "comments": comments,
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

    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"message": "Comment can't be empty"}), 400
    if len(body) > MAX_BODY_LEN:
        return jsonify({"message": f"Comment too long (max {MAX_BODY_LEN} characters)"}), 400

    is_spoiler = bool(data.get("is_spoiler"))

    # chapter is optional metadata now — the poster's position when they wrote
    # it. Default to their recorded progress. Never gates anything.
    my_progress = my_item.chapter_progress or 0
    try:
        chapter = int(data.get("chapter"))
        if chapter < 0:
            chapter = my_progress
    except (TypeError, ValueError):
        chapter = my_progress

    comment = DiscussionComment(
        user_id=me_id,
        imdb_id=external_id,
        media_type=media_type,
        chapter=chapter,
        body=body,
        is_spoiler=is_spoiler,
    )
    db.session.add(comment)
    db.session.commit()

    user = User.query.get(me_id)

    # Notify friends who share this book. Ungated: everyone in the club hears
    # about a new message. Spoiler messages push a neutral preview so the
    # notification itself never spoils.
    friend_ids = _friend_ids(me_id)
    if friend_ids:
        club = WatchlistItem.query.filter(
            WatchlistItem.user_id.in_(friend_ids),
            WatchlistItem.imdb_id == external_id,
            WatchlistItem.media_type == media_type,
        ).all()
        book_title = my_item.title or "your book club"
        poster_name = (user.display_name or user.username) if user else "A friend"
        preview = "marked a spoiler — open to reveal" if is_spoiler else comment.body[:100]
        notify(
            [it.user_id for it in club],
            f"{poster_name} · {book_title}",
            preview,
            category="discussions",
        )

    return jsonify({
        "id": comment.id,
        "user": _user_summary(user),
        "chapter": comment.chapter,
        "body": comment.body,
        "is_spoiler": bool(comment.is_spoiler),
        "reactions": [],
        "created_at": comment.created_at.isoformat(),
        "mine": True,
    }), 201


@discussion_bp.route("/comment/<int:comment_id>/react", methods=["POST"])
@jwt_required()
def toggle_reaction(comment_id):
    """Add or remove one emoji reaction on a comment (long-press to react).

    Toggling: reacting with an emoji you've already left removes it. You can
    only react to comments you can see — your own or a friend's.
    """
    me_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"message": "emoji is required"}), 400
    if len(emoji) > MAX_EMOJI_LEN:
        return jsonify({"message": "emoji is too long"}), 400

    comment = DiscussionComment.query.get(comment_id)
    if not comment:
        return jsonify({"message": "Comment not found"}), 404

    visible_ids = _friend_ids(me_id) | {me_id}
    if comment.user_id not in visible_ids:
        return jsonify({"message": "Comment not found"}), 404

    existing = DiscussionReaction.query.filter_by(
        comment_id=comment_id, user_id=me_id, emoji=emoji
    ).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(DiscussionReaction(
            comment_id=comment_id, user_id=me_id, emoji=emoji
        ))
    db.session.commit()

    # Return the fresh tally for just this comment, for the caller's view.
    tally = _reactions_for([comment_id], visible_ids, me_id).get(comment_id, [])
    return jsonify({"comment_id": comment_id, "reactions": tally}), 200


@discussion_bp.route("/comment/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    me_id = int(get_jwt_identity())
    comment = DiscussionComment.query.get(comment_id)
    if not comment or comment.user_id != me_id:
        return jsonify({"message": "Comment not found"}), 404
    # Clear reactions explicitly — don't rely on the DB cascade being armed
    # (SQLite only enforces ondelete when PRAGMA foreign_keys is on).
    DiscussionReaction.query.filter_by(comment_id=comment_id).delete()
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"message": "Comment deleted"}), 200
