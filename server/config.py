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
