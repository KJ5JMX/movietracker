"""
Songs and books search/detail.

Songs use the iTunes Search API (free, no key required).
Books use Open Library (free, no key required).

External IDs are stored in WatchlistItem.imdb_id even though the column name
is movie-specific — the column has always been the generic "external id from
the source platform" slot; renaming it would touch a lot of code for no real
gain. iTunes track IDs and OpenLibrary work keys don't collide with IMDb's
tt-prefixed IDs, so no namespacing is needed.
"""

import re

import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required


songs_bp = Blueprint("songs", __name__, url_prefix="/songs")
books_bp = Blueprint("books", __name__, url_prefix="/books")


# ---------------------------------------------------------------------------
# Songs (iTunes Search API)
# ---------------------------------------------------------------------------

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def _itunes_year(release_date):
    """iTunes returns ISO timestamps like '2010-06-21T07:00:00Z'. Pull the year."""
    if not release_date:
        return None
    match = re.match(r"^(\d{4})", release_date)
    return match.group(1) if match else None


def _itunes_high_res_artwork(url):
    """iTunes returns 100x100. Swap for 300x300 — same URL pattern, bigger image."""
    if not url:
        return None
    return url.replace("100x100", "300x300")


def _itunes_song_to_dict(track):
    """Normalize an iTunes track row to the same shape AddItemScreen expects."""
    return {
        "imdb_id": str(track.get("trackId")) if track.get("trackId") else None,
        "title": track.get("trackName"),
        "year": _itunes_year(track.get("releaseDate")),
        "movie_type": None,
        "media_type": "song",
        "poster": _itunes_high_res_artwork(track.get("artworkUrl100")),
        # Song-specific extras the frontend can store via the existing PATCH fields:
        "artist": track.get("artistName"),
        "album": track.get("collectionName"),
        "genre": track.get("primaryGenreName"),
        "runtime_minutes": (
            round(track["trackTimeMillis"] / 60000)
            if track.get("trackTimeMillis") else None
        ),
        "preview_url": track.get("previewUrl"),
    }


@songs_bp.route("/search", methods=["GET"])
@jwt_required()
def search_songs():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"message": "Query parameter 'q' is required"}), 400

    try:
        response = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": query, "entity": "song", "limit": 20},
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[songs] iTunes search failed: {e}")
        return jsonify([]), 200

    results = []
    for track in data.get("results", []) or []:
        if not track.get("trackId"):
            continue
        results.append(_itunes_song_to_dict(track))
    return jsonify(results), 200


@songs_bp.route("/<song_id>", methods=["GET"])
@jwt_required()
def get_song(song_id):
    """Lookup a single song by iTunes trackId. Returns the same shape as search results."""
    try:
        response = requests.get(
            "https://itunes.apple.com/lookup",
            params={"id": song_id},
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        return jsonify({"message": "Song not found"}), 404

    rows = data.get("results", []) or []
    if not rows:
        return jsonify({"message": "Song not found"}), 404
    return jsonify(_itunes_song_to_dict(rows[0])), 200


# ---------------------------------------------------------------------------
# Books (Open Library)
# ---------------------------------------------------------------------------

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"


def _ol_work_id(key):
    """Open Library returns keys like '/works/OL45883W'. Strip the prefix."""
    if not key:
        return None
    return key.rsplit("/", 1)[-1]


def _ol_cover_url(cover_id, size="M"):
    """Open Library cover URL builder. size = S | M | L."""
    if not cover_id:
        return None
    return f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"


def _ol_doc_to_dict(doc):
    authors = doc.get("author_name") or []
    return {
        "imdb_id": _ol_work_id(doc.get("key")),
        "title": doc.get("title"),
        "year": str(doc.get("first_publish_year")) if doc.get("first_publish_year") else None,
        "movie_type": None,
        "media_type": "book",
        "poster": _ol_cover_url(doc.get("cover_i"), size="M"),
        # Book-specific extras:
        "author": ", ".join(authors) if authors else None,
        # Open Library exposes a sprawling 'subject' array — pick the first few
        # readable ones for a usable genre line. Caps to avoid junk subjects like
        # "nyt:hardcover-fiction=2014-12-07" leaking through.
        "genre": _ol_pick_genre(doc.get("subject")),
        "page_count": doc.get("number_of_pages_median"),
    }


def _ol_pick_genre(subjects):
    if not subjects:
        return None
    clean = []
    for s in subjects:
        if not isinstance(s, str):
            continue
        # Drop machine-y subjects that have colons or look like categories
        if ":" in s or len(s) > 40:
            continue
        clean.append(s)
        if len(clean) >= 3:
            break
    return ", ".join(clean) if clean else None


@books_bp.route("/search", methods=["GET"])
@jwt_required()
def search_books():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"message": "Query parameter 'q' is required"}), 400

    try:
        response = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params={"q": query, "limit": 20, "fields": "key,title,author_name,first_publish_year,cover_i,subject,number_of_pages_median"},
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[books] Open Library search failed: {e}")
        return jsonify([]), 200

    results = []
    for doc in data.get("docs", []) or []:
        if not doc.get("key") or not doc.get("title"):
            continue
        results.append(_ol_doc_to_dict(doc))
    return jsonify(results), 200


@books_bp.route("/<work_id>", methods=["GET"])
@jwt_required()
def get_book(work_id):
    """Lookup a single work by Open Library work id (e.g. 'OL45883W')."""
    try:
        response = requests.get(
            f"https://openlibrary.org/works/{work_id}.json",
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        return jsonify({"message": "Book not found"}), 404

    if not data or data.get("error"):
        return jsonify({"message": "Book not found"}), 404

    # The works endpoint returns richer detail but differs in shape from search.
    # Re-map into the same dict the search results use, plus a description.
    covers = data.get("covers") or []
    cover_id = covers[0] if covers else None

    # Authors come back as references — pull names with a follow-up lookup.
    author_names = []
    for author_ref in (data.get("authors") or [])[:5]:
        author_key = (author_ref.get("author") or {}).get("key")
        if not author_key:
            continue
        try:
            a = requests.get(
                f"https://openlibrary.org{author_key}.json", timeout=5
            ).json()
            if a.get("name"):
                author_names.append(a["name"])
        except (requests.RequestException, ValueError):
            continue

    # Description is sometimes a string, sometimes a {value: ...} object.
    desc = data.get("description")
    if isinstance(desc, dict):
        desc = desc.get("value")

    return jsonify({
        "imdb_id": work_id,
        "title": data.get("title"),
        "year": None,  # works endpoint doesn't reliably give a first-publish year
        "movie_type": None,
        "media_type": "book",
        "poster": _ol_cover_url(cover_id, size="M"),
        "author": ", ".join(author_names) if author_names else None,
        "plot": desc,
        "genre": _ol_pick_genre(data.get("subjects")),
    }), 200
