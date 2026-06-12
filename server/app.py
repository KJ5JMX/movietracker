import sqlite3

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from sqlalchemy import event
from sqlalchemy.engine import Engine

from models import db
from config import Config


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Production-sane SQLite settings (no-op for Postgres):
    - WAL: readers don't block the writer, far fewer 'database is locked'
      errors with multiple gunicorn workers/threads.
    - busy_timeout: writers wait up to 5s for a lock instead of failing fast.
    - foreign_keys: SQLite doesn't enforce FKs unless told to.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
from auth_routes import auth_bp
from watchlist_routes import watchlist_bp
from movie_routes import movie_bp
from social_routes import social_bp
from night_routes import night_bp
from media_routes import songs_bp, books_bp
from feed_routes import feed_bp
from iap_routes import iap_bp
from discussion_routes import discussion_bp
from push_routes import push_bp
from wrapped_routes import wrapped_bp


app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(auth_bp)
app.register_blueprint(watchlist_bp)
app.register_blueprint(movie_bp)
app.register_blueprint(social_bp)
app.register_blueprint(night_bp)
app.register_blueprint(songs_bp)
app.register_blueprint(books_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(iap_bp)
app.register_blueprint(discussion_bp)
app.register_blueprint(push_bp)
app.register_blueprint(wrapped_bp)
CORS(app, resources={r"/*": {"origins": "*"}})

db.init_app(app)
Migrate(app, db)
JWTManager(app)


@app.route("/")
def home():
    return {"message": "Movie Tracker backend is running!"}


if __name__ == "__main__":
    app.run(debug=True, port=5555)
