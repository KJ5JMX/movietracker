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
    # Subscription bookkeeping, set by /iap/verify-receipt after Apple confirms
    # a purchase. pro_expires_at lets us lazily downgrade lapsed subscribers
    # without webhooks; the original transaction id ties an Apple subscription
    # to exactly one account (prevents one purchase unlocking many accounts).
    pro_expires_at = db.Column(db.DateTime, nullable=True)
    apple_original_transaction_id = db.Column(db.String, nullable=True, index=True)
    # Genre preferences — JSON-encoded list of genre strings ("Comedy", "Drama", ...).
    # Drives the discovery feed's filtering. Stored as text to keep this SQLite-safe
    # without needing a JSON column type.
    genres = db.Column(db.Text, nullable=True)
    # Social sign-in. Stable per-provider subject ids ('sub' claim). A social
    # user has no usable password (a random hash is stored). Unique so one
    # Apple/Google identity maps to exactly one account; NULL for accounts that
    # never used that provider.
    apple_sub = db.Column(db.String, nullable=True, unique=True, index=True)
    google_sub = db.Column(db.String, nullable=True, unique=True, index=True)
    # False only for a brand-new social account that hasn't picked a username
    # yet; the app routes those to the onboarding screen. Everyone else
    # (email/password signups, existing users) is onboarded by default.
    onboarded = db.Column(
        db.Boolean, default=True, server_default="1", nullable=False
    )
    # Gamification: cosmetic "plot points" balance, the equipped flair title, and
    # whether to show points + flair next to the user's name.
    points = db.Column(db.Integer, default=0, server_default="0", nullable=False)
    flair_selected = db.Column(db.String, nullable=True)  # flair key, or null
    show_flair = db.Column(
        db.Boolean, default=True, server_default="1", nullable=False
    )

    @property
    def is_pro(self):
        return self.pro_status in ("comp", "paid", "trial")

    watchlist_items = db.relationship(
        "WatchlistItem",
        backref="user",
        cascade="all, delete-orphan",
        foreign_keys="WatchlistItem.user_id",
    )


class PasswordResetToken(db.Model):
    """A single-use, time-limited password reset token.

    We store only the SHA-256 hash of the token, never the raw value, so a
    leak of this table can't be used to reset anyone's password. The raw token
    lives only in the emailed link. A row is consumed (used_at set) on a
    successful reset and ignored once expired.
    """

    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash = db.Column(db.String, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
    # Reading progress for books (chapter number). Drives the spoiler gate on
    # friend discussions: you only see comments tagged <= your progress.
    chapter_progress = db.Column(db.Integer, nullable=True)
    watch_status = db.Column(db.String, default="want_to_watch", nullable=False)
    rating = db.Column(db.Integer)
    notes = db.Column(db.String)
    # "Remind me when this comes out" — the jobs process pushes on release
    # day and flips release_reminded so it only ever fires once.
    remind_release = db.Column(
        db.Boolean, default=False, server_default="0", nullable=False
    )
    release_reminded = db.Column(
        db.Boolean, default=False, server_default="0", nullable=False
    )
    # Timestamps powering That's a Wrap. Nullable: rows from before this
    # column existed have unknown dates.
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    watched_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # When this item was added by accepting a recommendation, points to the friend who sent it.
    # Named FK so SQLite batch-mode add_column can apply it on existing tables.
    recommended_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_watchlist_recommended_by_user_id"),
        nullable=True,
    )


class DiscussionComment(db.Model):
    """Chapter-tagged comment on a book (Sierra's spoiler-safe book club).

    Visibility rules live in discussion_routes, enforced server-side:
    - readers see comments from THEIR friends (and themselves) only
    - readers see comments tagged <= their own chapter_progress
    - posters can't tag a chapter above their own progress
    """

    __tablename__ = "discussion_comments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_discussion_comment_user"),
        nullable=False,
        index=True,
    )
    # External id + media type of the item being discussed (book work ids for
    # now; the imdb_id column convention matches watchlist_items).
    imdb_id = db.Column(db.String, nullable=False)
    media_type = db.Column(
        db.String, default="book", server_default="book", nullable=False
    )
    chapter = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_discussion_item", "imdb_id", "media_type"),
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
    )  # scheduled, active, ended, abandoned

    # Scheduled nights: set when the host plans ahead. The jobs process sends
    # a reminder push shortly before scheduled_for.
    scheduled_for = db.Column(db.DateTime, nullable=True)
    reminder_sent = db.Column(
        db.Boolean, default=False, server_default="0", nullable=False
    )

    # Snapshot of the picked item (the watchlist item itself may be added/removed
    # independently). Nullable because a scheduled night has no pick yet.
    picked_imdb_id = db.Column(db.String, nullable=True)
    picked_title = db.Column(db.String, nullable=True)
    picked_year = db.Column(db.String, nullable=True)
    picked_poster = db.Column(db.String, nullable=True)
    picked_media_type = db.Column(db.String, nullable=False, default="movie")

    # Filters used for the roll (kept for audit / "re-roll with same filters")
    filter_max_runtime = db.Column(db.Integer, nullable=True)
    filter_mood = db.Column(db.String, nullable=True)


class DeviceToken(db.Model):
    """One row per registered push device. A token follows whichever account
    registered it most recently (sign-out/sign-in on a shared phone)."""

    __tablename__ = "device_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_device_token_user"),
        nullable=False,
        index=True,
    )
    token = db.Column(db.String, unique=True, nullable=False)
    platform = db.Column(
        db.String, default="ios", server_default="ios", nullable=False
    )  # ios | android
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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


class StreamingAvailabilityReport(db.Model):
    """Crowdsourced "where can I watch this" data.

    One row per (imdb_id, country, platform). Users report a platform when they
    rate something they watched; other users see the report on the detail screen
    with its age ("reported on Netflix, 3 weeks ago") and can confirm it's still
    there or flag it removed. last_confirmed_at is the freshness signal — every
    confirm bumps it, so stale reports are visibly old rather than silently wrong.

    Country matters because streaming rights are regional; defaults to US for now
    since that's the only region being curated. Cheating is low-value by design:
    the data unlocks nothing, so there's no incentive to fake reports.
    """

    __tablename__ = "streaming_availability_reports"

    id = db.Column(db.Integer, primary_key=True)
    imdb_id = db.Column(db.String, nullable=False, index=True)
    country = db.Column(
        db.String, default="US", server_default="US", nullable=False
    )
    platform = db.Column(db.String, nullable=False)  # netflix|hulu|amazon|hbo|disney|other
    reported_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_streaming_report_user"),
        nullable=True,
    )
    # active flips False when a user flags the title as removed; a fresh report
    # re-activates the same row rather than creating a duplicate.
    active = db.Column(
        db.Boolean, default=True, server_default="1", nullable=False
    )
    confirm_count = db.Column(
        db.Integer, default=1, server_default="1", nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_confirmed_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "imdb_id", "country", "platform", name="uq_report_title_country_platform"
        ),
    )


# ---------------------------------------------------------------------------
# ShelfMates Movie Fest — admin-curated Movie of the Week + monthly Battles.
# All curation is hand-set by the admin (no crowd needed); the curated
# `streaming` field is the authoritative where-to-watch for festival titles,
# stored as a JSON list of platform values (netflix|hulu|amazon|hbo|disney|other).
# ---------------------------------------------------------------------------


class MovieOfWeek(db.Model):
    """One curated pick per week. Users complete it (watch + rate + review)
    without adding it to their list; completing it records the completion and
    creates a watched WatchlistItem so it shows in their library + discovery."""

    __tablename__ = "movies_of_week"

    id = db.Column(db.Integer, primary_key=True)
    week_key = db.Column(db.String, nullable=False, unique=True)  # ISO week "2026-W27"
    imdb_id = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False)
    year = db.Column(db.String)
    poster = db.Column(db.String)
    media_type = db.Column(
        db.String, default="movie", server_default="movie", nullable=False
    )
    blurb = db.Column(db.String)  # optional admin note shown on the Fest page
    streaming = db.Column(db.Text)  # JSON list of platform values (admin-entered)
    active = db.Column(db.Boolean, default=True, server_default="1", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class MovieOfWeekCompletion(db.Model):
    """One row per (movie-of-week, user) once they finish it."""

    __tablename__ = "movie_of_week_completions"

    id = db.Column(db.Integer, primary_key=True)
    mow_id = db.Column(
        db.Integer,
        db.ForeignKey("movies_of_week.id", name="fk_mow_completion_mow"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_mow_completion_user"),
        nullable=False,
        index=True,
    )
    rating = db.Column(db.Integer)  # 1-5
    review = db.Column(db.Text)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("mow_id", "user_id", name="uq_mow_user"),
    )


class Battle(db.Model):
    """A head-to-head between two curated movies (monthly). Users rate/review
    both, then vote; the winner is surfaced in discovery as a battle pick. Two
    movies are inlined (a_*/b_*) since a battle is always exactly two."""

    __tablename__ = "battles"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)  # e.g. "July Battle"

    a_imdb_id = db.Column(db.String, nullable=False)
    a_title = db.Column(db.String, nullable=False)
    a_year = db.Column(db.String)
    a_poster = db.Column(db.String)
    a_streaming = db.Column(db.Text)  # JSON platform list

    b_imdb_id = db.Column(db.String, nullable=False)
    b_title = db.Column(db.String, nullable=False)
    b_year = db.Column(db.String)
    b_poster = db.Column(db.String)
    b_streaming = db.Column(db.Text)

    ends_at = db.Column(db.DateTime, nullable=False)  # countdown deadline
    active = db.Column(db.Boolean, default=True, server_default="1", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BattleVote(db.Model):
    """One vote per (battle, user). choice is 'a' or 'b'."""

    __tablename__ = "battle_votes"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(
        db.Integer,
        db.ForeignKey("battles.id", name="fk_battle_vote_battle"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_battle_vote_user"),
        nullable=False,
        index=True,
    )
    choice = db.Column(db.String, nullable=False)  # "a" | "b"
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("battle_id", "user_id", name="uq_battle_user"),
    )


class UserAchievement(db.Model):
    """One row per (user, ladder, tier) once earned. Points were granted at the
    moment of earning (added to User.points)."""

    __tablename__ = "user_achievements"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_user_achievement_user"),
        nullable=False,
        index=True,
    )
    ladder_key = db.Column(db.String, nullable=False)
    tier = db.Column(db.Integer, nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "ladder_key", "tier", name="uq_user_ladder_tier"
        ),
    )


class UserFlair(db.Model):
    """A flair title a user has bought with points. Owned forever once purchased;
    User.flair_selected points at the one currently shown."""

    __tablename__ = "user_flair"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_user_flair_user"),
        nullable=False,
        index=True,
    )
    flair_key = db.Column(db.String, nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "flair_key", name="uq_user_flair"),
    )
