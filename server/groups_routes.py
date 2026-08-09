"""User-created groups (collections) of watchlist items.

A group is an organizational overlay shown as a single fan-of-posters card in
the list. Members keep their own ratings/detail. Many-to-many: an item can live
in several groups. Grouped items are hidden from the flat list because the Lists
screen fetches /watchlist/?exclude_grouped=1.
"""

import hashlib
from collections import Counter

import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from config import Config
from models import db, Group, GroupMember, WatchlistItem
from models import User
from watchlist_routes import item_to_dict

groups_bp = Blueprint("groups", __name__, url_prefix="/groups")

# How many member posters to surface for the fan effect on the list card.
FAN_POSTER_LIMIT = 5

# How many members to sample when looking for a shared TMDB franchise.
BACKDROP_SAMPLE = 5


def _tmdb_collection_backdrop(imdb_id):
    """If this movie belongs to a TMDB collection (a franchise like Harry
    Potter), return {"id", "backdrop"} for that collection's curated art. TV has
    no collections in TMDB, so this is movie-only. None on any miss."""
    if not Config.TMDB_API_KEY:
        return None
    try:
        find = requests.get(
            f"{Config.TMDB_BASE_URL}/find/{imdb_id}",
            params={"api_key": Config.TMDB_API_KEY, "external_source": "imdb_id"},
            timeout=8,
        ).json()
    except (requests.RequestException, ValueError):
        return None
    results = find.get("movie_results") if isinstance(find, dict) else None
    if not results:
        return None
    tmdb_id = results[0].get("id")
    if not tmdb_id:
        return None
    try:
        details = requests.get(
            f"{Config.TMDB_BASE_URL}/movie/{tmdb_id}",
            params={"api_key": Config.TMDB_API_KEY},
            timeout=8,
        ).json()
    except (requests.RequestException, ValueError):
        return None
    coll = details.get("belongs_to_collection") if isinstance(details, dict) else None
    if not coll or not coll.get("id"):
        return None
    backdrop = coll.get("backdrop_path")
    return {
        "id": coll["id"],
        # Wide, high-res franchise still for a full-width hero.
        "backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop}" if backdrop else None,
    }


def _resolve_collection_backdrop(items):
    """The collection's franchise backdrop, if its movies share a real TMDB
    collection. Samples up to BACKDROP_SAMPLE movie members and takes the most
    common collection; requires 2+ agreeing (or a lone movie that belongs to
    one) so a mixed 'movies to watch' group doesn't borrow one film's franchise.
    None when there's no shared franchise (the client falls back to a montage)."""
    movie_items = [
        it for it in items
        if (it.media_type in (None, "movie")) and it.imdb_id
    ]
    votes = Counter()
    backdrops = {}
    for it in movie_items[:BACKDROP_SAMPLE]:
        res = _tmdb_collection_backdrop(it.imdb_id)
        if res:
            votes[res["id"]] += 1
            if res["backdrop"]:
                backdrops[res["id"]] = res["backdrop"]
    if not votes:
        return None
    top_id, count = votes.most_common(1)[0]
    if count >= 2 or len(movie_items) == 1:
        return backdrops.get(top_id)
    return None


def _member_backdrop_key(items):
    """Stable hash of the member set, so a cached backdrop invalidates the
    moment the collection's contents change."""
    ids = sorted(str(it.imdb_id or it.id) for it in items)
    return hashlib.md5("|".join(ids).encode("utf-8")).hexdigest()


def _owned_items(user_id, item_ids):
    """Return the caller's WatchlistItems whose ids are in item_ids (deduped,
    ownership-checked). Silently drops ids the user doesn't own."""
    ids = {int(i) for i in item_ids if str(i).lstrip("-").isdigit()}
    if not ids:
        return []
    return (
        WatchlistItem.query.filter(
            WatchlistItem.user_id == user_id,
            WatchlistItem.id.in_(ids),
        ).all()
    )


def _members_ordered(group_id):
    """Membership rows in custom order: by position (manual watch order) with
    unpositioned rows falling back to insertion order (id)."""
    return (
        GroupMember.query.filter_by(group_id=group_id)
        .order_by(
            (GroupMember.position.is_(None)),  # positioned rows first
            GroupMember.position.asc(),
            GroupMember.id.asc(),
        )
        .all()
    )


def group_summary(group):
    """Light dict for the list card: name, count, posters for the fan, and the
    distinct media types inside (so the list can show the collection under the
    right filter, not only 'All')."""
    members = _members_ordered(group.id)
    item_ids = [m.watchlist_item_id for m in members]
    posters = []
    media_types = []
    if item_ids:
        items = {
            it.id: it
            for it in WatchlistItem.query.filter(
                WatchlistItem.id.in_(item_ids)
            ).all()
        }
        seen_types = set()
        for iid in item_ids:
            it = items.get(iid)
            if not it:
                continue
            if it.poster and len(posters) < FAN_POSTER_LIMIT:
                posters.append(it.poster)
            if it.media_type and it.media_type not in seen_types:
                seen_types.add(it.media_type)
                media_types.append(it.media_type)
    return {
        "id": group.id,
        "name": group.name,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "member_count": len(item_ids),
        "item_ids": item_ids,
        "posters": posters,
        "media_types": media_types,
    }


def group_detail(group):
    """Full dict for the group screen: every member serialized like a list item."""
    members = _members_ordered(group.id)
    item_ids = [m.watchlist_item_id for m in members]
    items_by_id = {}
    if item_ids:
        for it in WatchlistItem.query.filter(WatchlistItem.id.in_(item_ids)).all():
            items_by_id[it.id] = it
    ordered_items = [items_by_id[i] for i in item_ids if i in items_by_id]
    return {
        "id": group.id,
        "name": group.name,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "member_count": len(ordered_items),
        "items": [item_to_dict(it) for it in ordered_items],
    }


@groups_bp.route("/", methods=["GET"])
@jwt_required()
def list_groups():
    user_id = int(get_jwt_identity())
    groups = (
        Group.query.filter_by(user_id=user_id)
        .order_by(Group.created_at.desc())
        .all()
    )
    return jsonify([group_summary(g) for g in groups]), 200


@groups_bp.route("/", methods=["POST"])
@jwt_required()
def create_group():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    # Free tier caps collections at 3; Pro is unlimited.
    _me = User.query.get(user_id)
    if _me and not _me.is_pro and Group.query.filter_by(user_id=user_id).count() >= 3:
        return jsonify({
            "message": "Free accounts keep 3 collections. Delete one, or go Pro for unlimited.",
            "code": "limit_reached",
            "limit": "collections",
            "cap": 3,
        }), 402

    item_ids = data.get("item_ids") or []
    if not isinstance(item_ids, list) or not item_ids:
        return jsonify({"message": "item_ids (non-empty list) is required"}), 400

    items = _owned_items(user_id, item_ids)
    if not items:
        return jsonify({"message": "No valid items to group"}), 400

    name = (data.get("name") or "").strip() or None

    group = Group(user_id=user_id, name=name)
    db.session.add(group)
    db.session.flush()  # assign group.id before adding members

    for idx, it in enumerate(items):
        db.session.add(
            GroupMember(group_id=group.id, watchlist_item_id=it.id, position=idx)
        )
    db.session.commit()

    return jsonify(group_detail(group)), 201


@groups_bp.route("/<int:group_id>", methods=["GET"])
@jwt_required()
def get_group(group_id):
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404
    return jsonify(group_detail(group)), 200


@groups_bp.route("/<int:group_id>/backdrop", methods=["GET"])
@jwt_required()
def group_backdrop(group_id):
    """The collection's franchise backdrop URL, or null. Resolved lazily off
    TMDB and cached on the group (keyed by member set) so repeat loads are free
    and it re-resolves only when the collection's contents change."""
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    members = _members_ordered(group.id)
    item_ids = [m.watchlist_item_id for m in members]
    items = []
    if item_ids:
        by_id = {
            it.id: it
            for it in WatchlistItem.query.filter(
                WatchlistItem.id.in_(item_ids)
            ).all()
        }
        items = [by_id[i] for i in item_ids if i in by_id]

    key = _member_backdrop_key(items)
    if group.backdrop_key == key:
        # Cache hit (including a cached "no franchise" -> null).
        return jsonify({"backdrop": group.backdrop_url}), 200

    backdrop = _resolve_collection_backdrop(items)
    group.backdrop_url = backdrop
    group.backdrop_key = key
    db.session.commit()
    return jsonify({"backdrop": backdrop}), 200


@groups_bp.route("/<int:group_id>", methods=["PATCH"])
@jwt_required()
def rename_group(group_id):
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        group.name = (data.get("name") or "").strip() or None
    db.session.commit()
    return jsonify(group_detail(group)), 200


@groups_bp.route("/<int:group_id>/members", methods=["POST"])
@jwt_required()
def add_members(group_id):
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids") or []
    items = _owned_items(user_id, item_ids)
    if not items:
        return jsonify({"message": "No valid items to add"}), 400

    existing_members = GroupMember.query.filter_by(group_id=group.id).all()
    existing = {m.watchlist_item_id for m in existing_members}
    next_pos = max(
        [m.position for m in existing_members if m.position is not None],
        default=-1,
    ) + 1
    for it in items:
        if it.id not in existing:
            db.session.add(
                GroupMember(
                    group_id=group.id, watchlist_item_id=it.id, position=next_pos
                )
            )
            next_pos += 1
    db.session.commit()
    return jsonify(group_detail(group)), 200


@groups_bp.route("/<int:group_id>/order", methods=["PATCH"])
@jwt_required()
def reorder_group(group_id):
    """Persist a manual member order (item_ids in the desired sequence)."""
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids")
    if not isinstance(item_ids, list):
        return jsonify({"message": "item_ids (ordered list) is required"}), 400

    members = {
        m.watchlist_item_id: m
        for m in GroupMember.query.filter_by(group_id=group.id).all()
    }
    seen = set()
    pos = 0
    for raw in item_ids:
        try:
            iid = int(raw)
        except (TypeError, ValueError):
            continue
        m = members.get(iid)
        if m and iid not in seen:
            m.position = pos
            seen.add(iid)
            pos += 1
    # Any members not named in the payload keep after, in their prior order.
    for m in sorted(members.values(), key=lambda x: x.id):
        if m.watchlist_item_id not in seen:
            m.position = pos
            pos += 1
    db.session.commit()
    return jsonify(group_detail(group)), 200


@groups_bp.route("/<int:group_id>/members/<int:item_id>", methods=["DELETE"])
@jwt_required()
def remove_member(group_id, item_id):
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    member = GroupMember.query.filter_by(
        group_id=group.id, watchlist_item_id=item_id
    ).first()
    if member:
        db.session.delete(member)
        db.session.flush()

    # Auto-dissolve a group that has no members left.
    remaining = GroupMember.query.filter_by(group_id=group.id).count()
    if remaining == 0:
        db.session.delete(group)
        db.session.commit()
        return jsonify({"message": "Group dissolved", "dissolved": True}), 200

    db.session.commit()
    return jsonify(group_detail(group)), 200


@groups_bp.route("/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    user_id = int(get_jwt_identity())
    group = Group.query.filter_by(id=group_id, user_id=user_id).first()
    if not group:
        return jsonify({"message": "Group not found"}), 404

    # ?delete_items=1 also removes the member movies from the user's list.
    # Default keeps them (only the collection is dissolved).
    delete_items = request.args.get("delete_items") in ("1", "true", "yes")
    if delete_items:
        member_ids = [
            m.watchlist_item_id
            for m in GroupMember.query.filter_by(group_id=group.id).all()
        ]
        if member_ids:
            WatchlistItem.query.filter(
                WatchlistItem.user_id == user_id,
                WatchlistItem.id.in_(member_ids),
            ).delete(synchronize_session=False)  # group_members cascade via FK

    db.session.delete(group)  # membership rows cascade; items kept unless above
    db.session.commit()
    return jsonify({"message": "Group deleted"}), 200
