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
