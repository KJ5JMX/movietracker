"""
Apple in-app purchase verification.

The app NEVER decides it's Pro on its own. After a StoreKit purchase (or a
"Restore purchases" tap, or on launch for an existing subscriber), the app
sends Apple's base64 receipt here. We forward it to Apple's verifyReceipt
service with our App-Specific Shared Secret, read the latest subscription
transaction, and set the user's pro_status accordingly. A tampered client
can claim whatever it wants — without a receipt Apple vouches for, nothing
changes.

Endpoints:
  POST /iap/verify-receipt   body: { receipt_data }  (JWT required)
    -> 200 { user, pro, expires_at }      verified (active OR expired-and-downgraded)
    -> 400 invalid receipt / no Pro subscription in it
    -> 409 subscription already linked to a different account
    -> 503 APPLE_SHARED_SECRET not configured yet

Design notes:
- Uses Apple's verifyReceipt endpoint with prod->sandbox fallback (status
  21007 means "sandbox receipt sent to production", which is exactly what
  happens during TestFlight/sandbox testing).
- Lazy expiry instead of webhooks for V1: the app re-sends the receipt on
  launch, and /auth/me downgrades a lapsed paid/trial user. App Store Server
  Notifications can be added later for instant cancellation sync.
- 'comp' users (testers comped via grant_pro.py) are never downgraded here.
"""

from datetime import datetime

import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from config import Config
from models import db, User
from auth_routes import user_to_dict


iap_bp = Blueprint("iap", __name__, url_prefix="/iap")

PRODUCTION_VERIFY_URL = "https://buy.itunes.apple.com/verifyReceipt"
SANDBOX_VERIFY_URL = "https://sandbox.itunes.apple.com/verifyReceipt"

# Must match the product IDs created in App Store Connect and the ones the
# app requests in src/iap.ts. Change in both places or nowhere.
PRO_PRODUCT_IDS = {
    "com.thenobodyprojects.cuedup.pro.monthly",
    "com.thenobodyprojects.cuedup.pro.yearly",
}
EXPECTED_BUNDLE_ID = "com.thenobodyprojects.cuedup"


def _verify_with_apple(receipt_b64):
    """POST the receipt to Apple. Prod first; fall back to sandbox on 21007.
    Returns Apple's response dict, or None on network failure."""
    payload = {
        "receipt-data": receipt_b64,
        "password": Config.APPLE_SHARED_SECRET,
        "exclude-old-transactions": True,
    }
    try:
        resp = requests.post(PRODUCTION_VERIFY_URL, json=payload, timeout=15)
        data = resp.json()
        if data.get("status") == 21007:
            resp = requests.post(SANDBOX_VERIFY_URL, json=payload, timeout=15)
            data = resp.json()
        return data
    except (requests.RequestException, ValueError) as e:
        print(f"[iap] Apple verifyReceipt failed: {e}")
        return None


def _latest_pro_transaction(data):
    """Pick the Pro transaction with the latest expiry from Apple's response.
    Returns (transaction_dict, expires_ms) or (None, 0)."""
    best, best_exp = None, 0
    for t in data.get("latest_receipt_info") or []:
        if t.get("product_id") not in PRO_PRODUCT_IDS:
            continue
        try:
            exp = int(t.get("expires_date_ms") or 0)
        except (TypeError, ValueError):
            continue
        if exp > best_exp:
            best, best_exp = t, exp
    return best, best_exp


def apply_expiry_if_lapsed(user):
    """Lazy downgrade: paid/trial whose Apple expiry has passed becomes free.
    Comp users are exempt. Returns True if the user was changed (NOT committed)."""
    if user.pro_status not in ("paid", "trial"):
        return False
    if user.pro_expires_at and user.pro_expires_at < datetime.utcnow():
        user.pro_status = "free"
        return True
    return False


@iap_bp.route("/verify-receipt", methods=["POST"])
@jwt_required()
def verify_receipt():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    if not Config.APPLE_SHARED_SECRET:
        return jsonify({
            "message": "Purchases aren't enabled on this server yet",
            "code": "iap_not_configured",
        }), 503

    data_in = request.get_json(silent=True) or {}
    receipt = data_in.get("receipt_data")
    if not receipt or not isinstance(receipt, str):
        return jsonify({"message": "receipt_data required"}), 400

    data = _verify_with_apple(receipt)
    if data is None:
        return jsonify({"message": "Could not reach Apple, try again"}), 502

    status = data.get("status")
    if status != 0:
        print(f"[iap] receipt rejected, Apple status={status}")
        return jsonify({"message": "Invalid receipt", "apple_status": status}), 400

    bundle_id = (data.get("receipt") or {}).get("bundle_id")
    if bundle_id != EXPECTED_BUNDLE_ID:
        print(f"[iap] bundle mismatch: {bundle_id}")
        return jsonify({"message": "Receipt is for a different app"}), 400

    txn, expires_ms = _latest_pro_transaction(data)
    if not txn:
        return jsonify({"message": "No ShelfMates Pro subscription in this receipt"}), 400

    original_txn_id = txn.get("original_transaction_id")

    # One Apple subscription unlocks exactly one ShelfMates account. If this
    # subscription is already attached to someone else, refuse — otherwise a
    # single $1.99 sub could be restored onto unlimited accounts.
    if original_txn_id:
        other = User.query.filter(
            User.apple_original_transaction_id == original_txn_id,
            User.id != user.id,
        ).first()
        if other:
            return jsonify({
                "message": "This subscription is already linked to another account",
                "code": "subscription_linked_elsewhere",
            }), 409

    expires_at = datetime.utcfromtimestamp(expires_ms / 1000.0)
    now = datetime.utcnow()

    if expires_at > now:
        # Comp (founding testers) is permanent: a real subscription never
        # overwrites it, so a later lapse can't silently demote them to free.
        is_trial = (txn.get("is_trial_period") == "true")
        if user.pro_status != "comp":
            user.pro_status = "trial" if is_trial else "paid"
        user.pro_expires_at = expires_at
        user.apple_original_transaction_id = original_txn_id
    else:
        # Receipt is real but the subscription lapsed. Record what we know and
        # downgrade paid/trial. Comp testers keep their access.
        user.pro_expires_at = expires_at
        user.apple_original_transaction_id = original_txn_id
        if user.pro_status in ("paid", "trial"):
            user.pro_status = "free"

    db.session.commit()

    return jsonify({
        "user": user_to_dict(user),
        "pro": user.is_pro,
        "expires_at": expires_at.isoformat(),
    }), 200
