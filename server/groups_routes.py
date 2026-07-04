"""User-created groups (collections) of watchlist items.

A group is an organizational overlay shown as a single fan-of-posters card in
the list. Members keep their own ratings/detail. Many-to-many: an item can live
in several groups. Grouped items are hidden from the flat list because the Lists
screen fetches /watchlist/?exclude_grouped=1.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Group, GroupMember, WatchlistItem
from watchlist_routes import item_to_dict

groups_bp = Blueprint("groups", __name__, url_prefix="/groups")

# How many member posters to surface for the fan effect on the list card.
FAN_POSTER_LIMIT = 5


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
