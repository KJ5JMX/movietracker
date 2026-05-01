from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from models import db
from config import Config
from auth_routes import auth_bp
from watchlist_routes import watchlist_bp
from movie_routes import movie_bp


app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(auth_bp)
app.register_blueprint(watchlist_bp)
app.register_blueprint(movie_bp)
CORS(app, resources={r"/*": {"origins": "*"}})

db.init_app(app)
Migrate(app, db)
JWTManager(app)


@app.route("/")
def home():
    return {"message": "Movie Tracker backend is running!"}


if __name__ == "__main__":
    app.run(debug=True, port=5555)
