from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)

    watchlist_items = db.relationship(
        "WatchlistItem", backref="user", cascade="all, delete-orphan"
    )


class WatchlistItem(db.Model):
    __tablename__ = "watchlist_items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    year = db.Column(db.String)
    imdb_id = db.Column(db.String, nullable=False)
    movie_type = db.Column(db.String)
    plot = db.Column(db.String)
    poster = db.Column(db.String)
    watch_status = db.Column(db.String, default="want_to_watch", nullable=False)
    rating = db.Column(db.Integer)
    notes = db.Column(db.String)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
