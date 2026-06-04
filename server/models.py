from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class StreamingCache(db.Model):
    __tablename__ = "streaming_cache"

    imdb_id = db.Column(db.String, primary_key=True)
    data = db.Column(db.Text, nullable=False)  # JSON-encoded list of source dicts
    cached_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    email = db.Column(db.String)
    display_name = db.Column(db.String)
    friend_code = db.Column(db.String, index=True)
    notification_prefs = db.Column(db.String, default="all", server_default="all")
    privacy_mode = db.Column(db.String, default="friends", server_default="friends")
    dark_mode = db.Column(db.Boolean, default=False, server_default="0")
    # Pro entitlement: free | comp | paid | trial.
    # `comp` is for testers (set via grant_pro.py); `paid`/`trial` are flipped
    # by App Store webhooks once StoreKit is wired up.
    pro_status = db.Column(
        db.String, default="free", server_default="free", nullable=False
    )
    # Genre preferences — JSON-encoded list of genre strings ("Comedy", "Drama", ...).
    # Drives the discovery feed's filtering. Stored as text to keep this SQLite-safe
    # without needing a JSON column type.
    genres = db.Column(db.Text, nullable=True)

    @property
    def is_pro(self):
        return self.pro_status in ("comp", "paid", "trial")

    watchlist_items = db.relationship(
        "WatchlistItem",
        backref="user",
        cascade="all, delete-orphan",
        foreign_keys="WatchlistItem.user_id",
    )


class Friendship(db.Model):
    __tablename__ = "friendships"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    addressee_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String, default="pending", server_default="pending", nullable=False
    )  # pending, accepted
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)


class Recommendation(db.Model):
    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    to_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # Snapshot of the item being recommended (so we can show it before recipient accepts)
    imdb_id = db.Column(db.String, nullable=False)
    media_type = db.Column(
        db.String, default="movie", server_default="movie", nullable=False
    )
    title = db.Column(db.String, nullable=False)
    year = db.Column(db.String)
    poster = db.Column(db.String)
    genre = db.Column(db.String)
    note = db.Column(db.Text)
    status = db.Column(
        db.String, default="pending", server_default="pending", nullable=False
    )  # pending, accepted, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ReviewShare(db.Model):
    __tablename__ = "review_shares"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    to_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # Optional link back to the original recommendation that prompted this review
    rec_id = db.Column(db.Integer, db.ForeignKey("recommendations.id"), nullable=True)
    imdb_id = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False)
    poster = db.Column(db.String)
    rating = db.Column(db.Integer)
    review_text = db.Column(db.Text)
    status = db.Column(
        db.String, default="unread", server_default="unread", nullable=False
    )  # unread, read
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class StreamingServiceTap(db.Model):
    """Per-user tap counter so the streaming modal can float services the user
    has used before to the top — auto-learned, no settings required."""

    __tablename__ = "streaming_service_taps"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    service_name = db.Column(db.String, nullable=False)
    tap_count = db.Column(db.Integer, default=0, server_default="0", nullable=False)
    last_tapped_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "service_name", name="uq_user_service"),
    )


class WatchlistItem(db.Model):
    __tablename__ = "watchlist_items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    year = db.Column(db.String)
    imdb_id = db.Column(db.String, nullable=False)
    movie_type = db.Column(db.String)
    media_type = db.Column(
        db.String, default="movie", server_default="movie", nullable=False
    )
    plot = db.Column(db.String)
    poster = db.Column(db.String)
    genre = db.Column(db.String)
    director = db.Column(db.String)
    actors = db.Column(db.String)
    imdb_rating = db.Column(db.String)
    rated = db.Column(db.String)
    released = db.Column(db.String)
    # Runtime in minutes (parsed from OMDb's "Runtime" e.g. "148 min"). Nullable for back-compat.
    runtime_minutes = db.Column(db.Integer, nullable=True)
    seasons_watched = db.Column(db.String)  # JSON-encoded list of season numbers, TV only
    watch_status = db.Column(db.String, default="want_to_watch", nullable=False)
    rating = db.Column(db.Integer)
    notes = db.Column(db.String)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # When this item was added by accepting a recommendation, points to the friend who sent it.
    # Named FK so SQLite batch-mode add_column can apply it on existing tables.
    recommended_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_watchlist_recommended_by_user_id"),
        nullable=True,
    )


class MovieNightSession(db.Model):
    """A movie-night picking session — group + chosen item + per-participant ratings."""

    __tablename__ = "movie_night_sessions"

    id = db.Column(db.Integer, primary_key=True)
    host_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_night_session_host"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(
        db.String,
        default="active",
        server_default="active",
        nullable=False,
    )  # active, ended, abandoned

    # Snapshot of the picked item (the watchlist item itself may be added/removed independently)
    picked_imdb_id = db.Column(db.String, nullable=False)
    picked_title = db.Column(db.String, nullable=False)
    picked_year = db.Column(db.String, nullable=True)
    picked_poster = db.Column(db.String, nullable=True)
    picked_media_type = db.Column(db.String, nullable=False, default="movie")

    # Filters used for the roll (kept for audit / "re-roll with same filters")
    filter_max_runtime = db.Column(db.Integer, nullable=True)
    filter_mood = db.Column(db.String, nullable=True)


class MovieNightParticipant(db.Model):
    """One row per (session, user). Tracks who's invited + their post-watch rating."""

    __tablename__ = "movie_night_participants"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "movie_night_sessions.id",
            name="fk_night_participant_session",
        ),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_night_participant_user"),
        nullable=False,
        index=True,
    )
    rating = db.Column(db.Integer, nullable=True)  # 1-5, set after watch
    rated_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("session_id", "user_id", name="uq_session_user"),
    )
