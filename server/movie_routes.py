import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from config import Config


movie_bp = Blueprint("movies", __name__, url_prefix="/movies")


@movie_bp.route("/search", methods=["GET"])
@jwt_required()
def search_movies():
    query = request.args.get("q")
    if not query:
        return jsonify({"message": "Query parameter 'q' is required"}), 400

    response = requests.get(
        Config.OMDB_BASE_URL,
        params={"apikey": Config.OMDB_API_KEY, "s": query, "type": "movie"},
        timeout=10,
    )
    data = response.json()

    if data.get("Response") == "False":
        return jsonify([]), 200

    results = [
        {
            "imdb_id": item.get("imdbID"),
            "title": item.get("Title"),
            "year": item.get("Year"),
            "movie_type": item.get("Type"),
            "poster": item.get("Poster") if item.get("Poster") != "N/A" else None,
        }
        for item in data.get("Search", [])
    ]
    return jsonify(results), 200


@movie_bp.route("/<imdb_id>", methods=["GET"])
@jwt_required()
def get_movie(imdb_id):
    response = requests.get(
        Config.OMDB_BASE_URL,
        params={"apikey": Config.OMDB_API_KEY, "i": imdb_id, "plot": "short"},
        timeout=10,
    )
    data = response.json()

    if data.get("Response") == "False":
        return jsonify({"message": data.get("Error", "Movie not found")}), 404

    return jsonify({
        "imdb_id": data.get("imdbID"),
        "title": data.get("Title"),
        "year": data.get("Year"),
        "movie_type": data.get("Type"),
        "plot": data.get("Plot"),
        "poster": data.get("Poster") if data.get("Poster") != "N/A" else None,
        "runtime": data.get("Runtime"),
        "genre": data.get("Genre"),
    }), 200
