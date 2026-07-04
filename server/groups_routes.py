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
    """Membership rows for a group, oldest first (stable fan/swapper order)."""
    return (
        GroupMember.query.filter_by(group_id=group_id)
        .order_by(GroupMember.id.asc())
        .all()
    )


def group_summary(group):
    """Light dict for the list card: name, count, and a few posters for the fan."""
    members = _members_ordered(group.id)
    item_ids = [m.watchlist_item_id for m in members]
    posters = []
    if item_ids:
        items = {
            it.id: it
            for it in WatchlistItem.query.filter(
                WatchlistItem.id.in_(item_ids)
            ).all()
        }
        for iid in item_ids:
            it = items.get(iid)
            if it and it.poster:
                posters.append(it.poster)
            if len(posters) >= FAN_POSTER_LIMIT:
                break
    return {
        "id": group.id,
        "name": group.name,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "member_count": len(item_ids),
        "item_ids": item_ids,
        "posters": posters,
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

    for it in items:
        db.session.add(
            GroupMember(group_id=group.id, watchlist_item_id=it.id)
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

    existing = {
        m.watchlist_item_id for m in GroupMember.query.filter_by(group_id=group.id).all()
    }
    for it in items:
        if it.id not in existing:
            db.session.add(
                GroupMember(group_id=group.id, watchlist_item_id=it.id)
            )
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

    db.session.delete(group)  # membership rows cascade; items are untouched
    db.session.commit()
    return jsonify({"message": "Group deleted"}), 200
