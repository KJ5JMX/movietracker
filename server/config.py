import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Fall back to a persistent on-disk SQLite file (resolved under the Flask
    # instance/ folder) when DATABASE_URL is unset. Without this, Flask-SQLAlchemy
    # silently uses an in-memory DB that is wiped on every restart/deploy.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///watchlist.db"
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=30)
    OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
    OMDB_BASE_URL = "https://www.omdbapi.com/"
    WATCHMODE_API_KEY = os.environ.get("WATCHMODE_API_KEY")
    WATCHMODE_BASE_URL = "https://api.watchmode.com/v1"
    # App-Specific Shared Secret from App Store Connect (App Information ->
    # App-Specific Shared Secret). Required by /iap/verify-receipt; while it's
    # unset, that endpoint returns 503 and the app's purchase UI stays in
    # "not available yet" mode.
    APPLE_SHARED_SECRET = os.environ.get("APPLE_SHARED_SECRET")

    # APNs push (token-based auth). Until all three are set, push silently
    # no-ops everywhere -- safe for dev and tests.
    #   APNS_KEY_PATH: path to the .p8 auth key from the developer portal
    #   APNS_KEY_ID:   the 10-char Key ID shown next to that key
    #   APNS_TEAM_ID:  your Apple Developer Team ID
    APNS_KEY_PATH = os.environ.get("APNS_KEY_PATH")
    APNS_KEY_ID = os.environ.get("APNS_KEY_ID")
    APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID")
    APNS_BUNDLE_ID = os.environ.get(
        "APNS_BUNDLE_ID", "com.thenobodyprojects.cuedup"
    )
    # TestFlight and App Store builds use production APNs; set to "1" only
    # when testing a development (Xcode-run) build.
    APNS_USE_SANDBOX = os.environ.get("APNS_USE_SANDBOX") == "1"

    # Password reset via emailed link. While RESEND_API_KEY is unset, the
    # forgot-password endpoint still responds normally but no mail is sent
    # (safe for dev/tests). Get the key from resend.com and verify the sending
    # domain there first.
    #   RESEND_API_KEY:   API key from the Resend dashboard
    #   RESET_FROM_EMAIL: verified sender, e.g. 'ShelfMates <noreply@thenobodyprojects.com>'
    #   APP_PUBLIC_URL:   public base URL the reset link points at (this backend)
    #   RESET_TOKEN_TTL_MINUTES: how long a reset link stays valid
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    RESET_FROM_EMAIL = os.environ.get(
        "RESET_FROM_EMAIL", "ShelfMates <noreply@thenobodyprojects.com>"
    )
    APP_PUBLIC_URL = os.environ.get(
        "APP_PUBLIC_URL", "https://cuedup-api.thenobodyprojects.com"
    ).rstrip("/")
    RESET_TOKEN_TTL_MINUTES = int(os.environ.get("RESET_TOKEN_TTL_MINUTES", "60"))

    # Social sign-in. The backend verifies the provider's identity token and
    # accepts it only if its audience matches one of these client IDs. Until
    # they're set, /auth/apple and /auth/google return 503 (feature off), the
    # same pattern as IAP.
    #
    # Apple: for native iOS the token's `aud` is your app bundle ID. Add a
    # Services ID too if you later add web/Android Apple sign-in.
    #   APPLE_CLIENT_IDS: comma-separated, e.g. 'com.thenobodyprojects.cuedup'
    # Google: the token's `aud` is the OAuth *web/server* client ID configured
    # in the app (react-native-google-signin's webClientId). List every client
    # ID that can mint tokens for you (iOS, web, Android).
    #   GOOGLE_CLIENT_IDS: comma-separated OAuth client IDs
    APPLE_CLIENT_IDS = [
        s.strip()
        for s in os.environ.get(
            "APPLE_CLIENT_IDS", "com.thenobodyprojects.cuedup"
        ).split(",")
        if s.strip()
    ]
    GOOGLE_CLIENT_IDS = [
        s.strip()
        for s in os.environ.get("GOOGLE_CLIENT_IDS", "").split(",")
        if s.strip()
    ]

    # ShelfMates Movie Fest admin panel (/admin). Protected at the edge by
    # Cloudflare Access; the app double-checks the authenticated email Cloudflare
    # injects against this allowlist. ADMIN_TOKEN is a local-only fallback for
    # hitting /admin directly on the box (e.g. curl) without Cloudflare in front.
    #   ADMIN_EMAILS: comma-separated emails allowed into /admin
    #   ADMIN_TOKEN:  optional shared secret accepted via X-Admin-Token header
    ADMIN_EMAILS = [
        s.strip().lower()
        for s in os.environ.get("ADMIN_EMAILS", "").split(",")
        if s.strip()
    ]
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")
