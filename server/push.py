"""Push notification fan-out.

One entry point the rest of the codebase calls:

    notify(user_ids, title, body, data=None)

Per-platform transports live behind it:
  - ios: APNs HTTP/2, spoken directly (token-based auth, no third party)
  - android: FCM slot, stubbed until the Android build exists

Everything degrades to a silent no-op when APNs credentials are not
configured, so dev environments and the test suite never need real keys,
and a push failure can never break the request that triggered it.
"""

import json
import threading
import time

import jwt  # PyJWT (already a flask-jwt-extended dependency)
from flask import current_app

from config import Config
from models import db, DeviceToken, User

# Canonical notification categories. The app renders a toggle per category;
# notify() filters recipients who've turned a category off. Missing = on.
NOTIFICATION_CATEGORIES = [
    "friend_requests",
    "recommendations",
    "ratings",
    "movie_nights",
    "discussions",
    "reminders",
    "achievements",
    "festival",
    "likes",
]


def _user_allows(user, category):
    if not category:
        return True
    try:
        settings = json.loads(user.notification_settings) if user.notification_settings else {}
    except (ValueError, TypeError):
        settings = {}
    return settings.get(category, True)  # default ON

# Apple wants provider JWTs refreshed between 20 and 60 minutes
_TOKEN_TTL_SECONDS = 40 * 60
_jwt_cache = {"token": None, "issued": 0.0}
_jwt_lock = threading.Lock()


def apns_configured():
    return bool(
        Config.APNS_KEY_PATH and Config.APNS_KEY_ID and Config.APNS_TEAM_ID
    )


def _apns_jwt():
    with _jwt_lock:
        now = time.time()
        if _jwt_cache["token"] and now - _jwt_cache["issued"] < _TOKEN_TTL_SECONDS:
            return _jwt_cache["token"]
        with open(Config.APNS_KEY_PATH) as f:
            key = f.read()
        token = jwt.encode(
            {"iss": Config.APNS_TEAM_ID, "iat": int(now)},
            key,
            algorithm="ES256",
            headers={"kid": Config.APNS_KEY_ID},
        )
        _jwt_cache["token"] = token
        _jwt_cache["issued"] = now
        return token


def _apns_base_url():
    if Config.APNS_USE_SANDBOX:
        return "https://api.sandbox.push.apple.com"
    return "https://api.push.apple.com"


def _send_ios(app, tokens, title, body, data):
    """Runs on a background thread: HTTP/2 POSTs to APNs, then prunes any
    tokens Apple reports as dead."""
    import httpx

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }
    if data:
        payload.update(data)

    headers = {
        "authorization": f"bearer {_apns_jwt()}",
        "apns-topic": Config.APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }

    dead_tokens = []
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            for token in tokens:
                try:
                    resp = client.post(
                        f"{_apns_base_url()}/3/device/{token}",
                        json=payload,
                        headers=headers,
                    )
                    if resp.status_code in (400, 410):
                        reason = (resp.json() or {}).get("reason", "")
                        if reason in ("BadDeviceToken", "Unregistered",
                                      "DeviceTokenNotForTopic"):
                            dead_tokens.append(token)
                except httpx.HTTPError as e:
                    print(f"[push] APNs send failed: {e}")
    except Exception as e:
        print(f"[push] APNs client error: {e}")

    if dead_tokens:
        try:
            with app.app_context():
                DeviceToken.query.filter(
                    DeviceToken.token.in_(dead_tokens)
                ).delete(synchronize_session=False)
                db.session.commit()
        except Exception as e:
            print(f"[push] dead-token cleanup failed: {e}")


def _send_android(app, tokens, title, body, data):
    # FCM transport lands with the Android build. Architecture is already
    # platform-split so this is the only function that will change.
    pass


def notify(user_ids, title, body, data=None, app=None, category=None):
    """Fan a notification out to every registered device of the given users.

    Safe to call from request handlers (uses current_app) or from the jobs
    process (pass app explicitly). Network I/O happens on a daemon thread so
    the caller never blocks on Apple.

    If `category` is given, recipients who've turned that category off in their
    notification settings are filtered out first.
    """
    if not user_ids:
        return
    try:
        if category:
            users = User.query.filter(
                User.id.in_(list(set(user_ids)))
            ).all()
            allowed = {u.id for u in users if _user_allows(u, category)}
            user_ids = [uid for uid in user_ids if uid in allowed]
            if not user_ids:
                return
        flask_app = app or current_app._get_current_object()
        rows = DeviceToken.query.filter(
            DeviceToken.user_id.in_(list(set(user_ids)))
        ).all()
        ios = [r.token for r in rows if r.platform == "ios"]
        android = [r.token for r in rows if r.platform == "android"]
    except Exception as e:
        print(f"[push] token lookup failed: {e}")
        return

    if ios and apns_configured():
        threading.Thread(
            target=_send_ios, args=(flask_app, ios, title, body, data),
            daemon=True,
        ).start()
    if android:
        threading.Thread(
            target=_send_android, args=(flask_app, android, title, body, data),
            daemon=True,
        ).start()
