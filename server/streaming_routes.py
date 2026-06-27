"""Crowdsourced streaming availability ("where can I watch this").

Users report a platform when they rate something they watched. Other users see
the report on the detail screen with its age and can confirm it's still there or
flag it removed. The data is honest about staleness (every report carries a
last_confirmed_at) and unlocks nothing, so there's no incentive to fake it.

Scope notes:
- US only for now (curated by hand); country defaults to "US".
- Platform list is fixed server-side so the data stays clean and groupable.
"""

from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, StreamingAvailabilityReport

streaming_bp = Blueprint("streaming", __name__, url_prefix="/streaming")

# Fixed set keeps the data clean (no "Netflix" vs "netflix" vs "NF" sprawl).
# Mobile sends one of these; anything else is rejected.
ALLOWED_PLATFORMS = {
    "netflix", "hulu", "amazon", "hbo", "disney", "appletv",
    "paramount", "peacock", "starz", "showtime", "amc", "tubi", "crunchyroll",
    "other",
}
DEFAULT_COUNTRY = "US"


def _normalize_platform(raw):
    return (raw or "").strip().lower()


def _normalize_country(raw):
    country = (raw or "").strip().upper()
    return country or DEFAULT_COUNTRY


def report_to_dict(report):
    age_seconds = (datetime.utcnow() - report.last_confirmed_at).total_seconds()
    return {
        "id": report.id,
        "imdb_id": report.imdb_id,
        "country": report.country,
        "platform": report.platform,
        "confirm_count": report.confirm_count,
        "last_confirmed_at": report.last_confirmed_at.isoformat() + "Z",
        # Convenience for the UI so it doesn't have to do date math; drives the
        # "reported 3 weeks ago" label and any stale-styling.
        "days_since_confirmed": int(age_seconds // 86400),
    }


@streaming_bp.route("/reports", methods=["GET"])
@jwt_required()
def get_reports():
    """All active reports for a title in a country, freshest first.

    GET /streaming/reports?imdb_id=tt123&country=US
    """
    imdb_id = request.args.get("imdb_id")
    if not imdb_id:
        return jsonify({"message": "imdb_id is required"}), 400
    country = _normalize_country(request.args.get("country"))

    reports = (
        StreamingAvailabilityReport.query.filter_by(
            imdb_id=imdb_id, country=country, active=True
        )
        .order_by(StreamingAvailabilityReport.last_confirmed_at.desc())
        .all()
    )
    return jsonify([report_to_dict(r) for r in reports]), 200


@streaming_bp.route("/report", methods=["POST"])
@jwt_required()
def create_report():
    """Report a platform for a title (called from the rating flow).

    POST { imdb_id, platform, country? }

    Upserts on (imdb_id, country, platform): a repeat report on an existing row
    just refreshes it and bumps confirm_count rather than duplicating, and
    re-activates a previously-removed row.
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    imdb_id = (data.get("imdb_id") or "").strip()
    if not imdb_id:
        return jsonify({"message": "imdb_id is required"}), 400

    platform = _normalize_platform(data.get("platform"))
    if platform not in ALLOWED_PLATFORMS:
        return (
            jsonify(
                {
                    "message": "Invalid platform",
                    "allowed": sorted(ALLOWED_PLATFORMS),
                }
            ),
            400,
        )
    country = _normalize_country(data.get("country"))

    existing = StreamingAvailabilityReport.query.filter_by(
        imdb_id=imdb_id, country=country, platform=platform
    ).first()

    if existing:
        existing.last_confirmed_at = datetime.utcnow()
        existing.confirm_count += 1
        existing.active = True
        report = existing
        status_code = 200
    else:
        report = StreamingAvailabilityReport(
            imdb_id=imdb_id,
            country=country,
            platform=platform,
            reported_by_user_id=user_id,
        )
        db.session.add(report)
        status_code = 201

    db.session.commit()
    return jsonify(report_to_dict(report)), status_code


@streaming_bp.route("/report/<int:report_id>/confirm", methods=["POST"])
@jwt_required()
def confirm_report(report_id):
    """"Still there" — refresh the freshness timestamp and bump the count."""
    report = StreamingAvailabilityReport.query.get(report_id)
    if not report:
        return jsonify({"message": "Report not found"}), 404

    report.last_confirmed_at = datetime.utcnow()
    report.confirm_count += 1
    report.active = True
    db.session.commit()
    return jsonify(report_to_dict(report)), 200


@streaming_bp.route("/report/<int:report_id>/remove", methods=["POST"])
@jwt_required()
def remove_report(report_id):
    """"Not there anymore" — deactivate. A future report re-activates the row."""
    report = StreamingAvailabilityReport.query.get(report_id)
    if not report:
        return jsonify({"message": "Report not found"}), 404

    report.active = False
    db.session.commit()
    return jsonify({"message": "Report removed", "id": report_id}), 200
