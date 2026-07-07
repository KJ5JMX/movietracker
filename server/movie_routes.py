import json
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from config import Config
from models import db, StreamingCache, StreamingServiceTap


IMPORT_MAX_LINES = 50  # Cap to protect the OMDb quota + keep latency sane


movie_bp = Blueprint("movies", __name__, url_prefix="/movies")

STREAMING_CACHE_DAYS = 30


OMDB_TYPE_MAP = {"movie": "movie", "tv": "series"}
INTERNAL_TYPE_MAP = {"movie": "movie", "series": "tv"}


def _na_to_none(value):
    """OMDb returns the literal string 'N/A' for missing fields."""
    if value in (None, "N/A", ""):
        return None
    return value


def _query_variants(query):
    """Forgiving-search fallbacks, tried in order until OMDb returns results.

    OMDb's search is rigid about punctuation: "bobs burgers" misses
    "Bob's Burgers" and vice versa. Variants generated:
      1. the query as typed
      2. punctuation stripped            (bob's -> bobs)
      3. possessive repair, per word     (bobs -> bob's)
    Capped at 5 variants; each one only costs an extra OMDb call when the
    previous returned nothing.
    """
    q = (query or "").strip()
    if not q:
        return []
    variants = [q]

    stripped = re.sub(r"[^\w\s]", "", q)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and stripped.lower() != q.lower():
        variants.append(stripped)

    words = (stripped or q).split()
    for i, w in enumerate(words):
        if len(variants) >= 5:
            break
        if len(w) > 2 and w.lower().endswith("s") and not w.lower().endswith("ss"):
            repaired = list(words)
            repaired[i] = w[:-1] + "'s"
            candidate = " ".join(repaired)
            if candidate.lower() not in [v.lower() for v in variants]:
                variants.append(candidate)
    return variants


def _omdb_search_forgiving(query, omdb_type, default_media_type):
    """_omdb_search with punctuation/possessive fallbacks on empty results."""
    for variant in _query_variants(query):
        results = _omdb_search(variant, omdb_type, default_media_type)
        if results:
            return results
    return []


def _omdb_search(query, omdb_type, default_media_type):
    """Run a single OMDb search. Returns normalized result dicts (movie + series only)."""
    params = {"apikey": Config.OMDB_API_KEY, "s": query}
    if omdb_type:
        params["type"] = omdb_type
    try:
        response = requests.get(Config.OMDB_BASE_URL, params=params, timeout=10)
        data = response.json()
    except (requests.RequestException, ValueError):
        return []
    if data.get("Response") == "False":
        return []
    return [
        {
            "imdb_id": item.get("imdbID"),
            "title": item.get("Title"),
            "year": item.get("Year"),
            "movie_type": item.get("Type"),
            "media_type": INTERNAL_TYPE_MAP.get(item.get("Type"), default_media_type),
            "poster": _na_to_none(item.get("Poster")),
        }
        for item in data.get("Search", []) or []
        if item.get("Type") in (None, "movie", "series")  # skip episodes
    ]


@movie_bp.route("/search", methods=["GET"])
@jwt_required()
def search_movies():
    query = request.args.get("q")
    if not query:
        return jsonify({"message": "Query parameter 'q' is required"}), 400

    media_type = request.args.get("media_type", "movie")
    if media_type not in ("all", "movie", "tv"):
        return jsonify({"message": f"Invalid media_type: {media_type}"}), 400

    # "all" fans out to OMDb (movies + TV), iTunes (songs), and Open Library
    # (books) so the user gets a true cross-media result set. The per-source
    # endpoints (/songs/search, /books/search) are still used when a specific
    # media chip is selected.
    if media_type == "all":
        # Lazy import the song/book normalizers + URLs to avoid a circular
        # blueprint import at module load.
        from media_routes import (
            _itunes_song_to_dict,
            _ol_doc_to_dict,
            ITUNES_SEARCH_URL,
            OPEN_LIBRARY_SEARCH_URL,
        )

        movies_results = _omdb_search_forgiving(query, None, "movie")

        songs_results = []
        try:
            r = requests.get(
                ITUNES_SEARCH_URL,
                params={"term": query, "entity": "song", "limit": 10},
                timeout=10,
            )
            for track in (r.json().get("results") or []):
                if track.get("trackId"):
                    songs_results.append(_itunes_song_to_dict(track))
        except (requests.RequestException, ValueError):
            pass

        books_results = []
        try:
            r = requests.get(
                OPEN_LIBRARY_SEARCH_URL,
                params={
                    "q": query, "limit": 10,
                    "fields": "key,title,author_name,first_publish_year,cover_i,subject,number_of_pages_median",
                },
                timeout=10,
            )
            for doc in (r.json().get("docs") or []):
                if doc.get("key") and doc.get("title"):
                    books_results.append(_ol_doc_to_dict(doc))
        except (requests.RequestException, ValueError):
            pass

        # Interleave so users don't see "all movies, then all songs, then all books"
        return jsonify(
            _interleave_results(movies_results, songs_results, books_results)
        ), 200

    # Single-type search: just OMDb (with punctuation-forgiving fallbacks)
    omdb_type = OMDB_TYPE_MAP[media_type]
    return jsonify(_omdb_search_forgiving(query, omdb_type, media_type)), 200


def _interleave_results(*lists):
    """Round-robin merge so the All view feels balanced across media types."""
    merged = []
    iters = [iter(lst) for lst in lists if lst]
    while iters:
        next_iters = []
        for it in iters:
            try:
                merged.append(next(it))
                next_iters.append(it)
            except StopIteration:
                continue
        iters = next_iters
    return merged


def _expand_csv_export(lines):
    """Detect a pasted Letterboxd/Goodreads CSV export and reduce it to
    plain "Title (Year)" lines. Anything that doesn't look like one of
    those exports passes through untouched."""
    if not lines or not isinstance(lines, list):
        return lines
    header = str(lines[0]).lower()
    looks_letterboxd = "letterboxd uri" in header
    looks_goodreads = "title" in header and "author" in header and "," in header
    looks_generic_csv = "name" in header and "year" in header and "," in header
    if not (looks_letterboxd or looks_goodreads or looks_generic_csv):
        return lines
    try:
        rows = list(csv.reader(io.StringIO("\n".join(str(l) for l in lines))))
    except csv.Error:
        return lines
    if len(rows) < 2:
        return lines
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return None

    title_i = col("name", "title")
    year_i = col("year", "original publication year", "year published")
    if title_i is None:
        return lines
    out = []
    for row in rows[1:]:
        if len(row) <= title_i:
            continue
        title = row[title_i].strip()
        if not title:
            continue
        year = ""
        if year_i is not None and len(row) > year_i:
            year = row[year_i].strip()
        out.append(f"{title} ({year})" if year else title)
    return out or lines


def _clean_import_line(raw):
    """Strip common list-prefix junk (numbers, bullets, dashes) from a line."""
    if not isinstance(raw, str):
        return ""
    # Drop leading list prefixes: "1.", "- ", "* ", "• ", "1)" etc.
    cleaned = re.sub(r"^[\s\d\.\)\(\-\*•#]+", "", raw)
    # Drop trailing parenthetical years so OMDb can match more loosely.
    # e.g. "Inception (2010)" -> "Inception"
    cleaned = re.sub(r"\s*\(\d{4}\)\s*$", "", cleaned)
    return cleaned.strip()


def _omdb_search_top(query, omdb_type=None, limit=3):
    """Return up to `limit` movie/series candidates from OMDb for `query`."""
    params = {"apikey": Config.OMDB_API_KEY, "s": query}
    if omdb_type:
        params["type"] = omdb_type
    try:
        response = requests.get(Config.OMDB_BASE_URL, params=params, timeout=10)
        data = response.json()
    except (requests.RequestException, ValueError):
        return []
    if data.get("Response") != "True":
        return []
    candidates = []
    for item in data.get("Search", []) or []:
        if item.get("Type") not in ("movie", "series"):
            continue
        candidates.append({
            "imdb_id": item.get("imdbID"),
            "title": item.get("Title"),
            "year": item.get("Year"),
            "movie_type": item.get("Type"),
            "media_type": INTERNAL_TYPE_MAP.get(item.get("Type"), "movie"),
            "poster": _na_to_none(item.get("Poster")),
        })
        if len(candidates) >= limit:
            break
    return candidates


def _omdb_search_top_forgiving(query, omdb_type=None, limit=3):
    """_omdb_search_top with the same punctuation fallbacks as live search."""
    for variant in _query_variants(query):
        results = _omdb_search_top(variant, omdb_type=omdb_type, limit=limit)
        if results:
            return results
    return []


def _books_search_top(query, limit=3):
    """Top Open Library book candidates for `query` (normalized dicts).

    Lazy-imports the media_routes normalizer to avoid a circular blueprint
    import at module load, same pattern as the cross-media /movies/search.
    """
    from media_routes import _ol_doc_to_dict, OPEN_LIBRARY_SEARCH_URL

    try:
        r = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params={
                "q": query,
                "limit": limit,
                "fields": "key,title,author_name,first_publish_year,cover_i,subject,number_of_pages_median",
            },
            timeout=10,
        )
        docs = r.json().get("docs") or []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for doc in docs:
        if doc.get("key") and doc.get("title"):
            out.append(_ol_doc_to_dict(doc))
        if len(out) >= limit:
            break
    return out


def _songs_search_top(query, limit=3):
    """Top iTunes song candidates for `query` (normalized dicts)."""
    from media_routes import _itunes_song_to_dict, ITUNES_SEARCH_URL

    try:
        r = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": query, "entity": "song", "limit": limit},
            timeout=10,
        )
        rows = r.json().get("results") or []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for track in rows:
        if track.get("trackId"):
            out.append(_itunes_song_to_dict(track))
        if len(out) >= limit:
            break
    return out


def _import_candidates(query, media_type):
    """Candidate matches for one import line, honoring the requested type.

    A specific type hits only its own source. 'all'/'auto' probes every source
    and returns a merged list with the most likely guess first (movies/TV, then
    a book, then a song), so a mis-detected line can be corrected in the review
    UI with one 'Try next match' tap instead of silently adding the wrong item.
    """
    if media_type in OMDB_TYPE_MAP:  # 'movie' or 'tv'
        return _omdb_search_top_forgiving(
            query, omdb_type=OMDB_TYPE_MAP[media_type], limit=3
        )
    if media_type == "book":
        return _books_search_top(query, limit=3)
    if media_type == "song":
        return _songs_search_top(query, limit=3)
    # auto / all
    merged = []
    merged.extend(_omdb_search_top_forgiving(query, omdb_type=None, limit=2))
    merged.extend(_books_search_top(query, limit=1))
    merged.extend(_songs_search_top(query, limit=1))
    return merged


IMPORT_MEDIA_TYPES = {"all", "movie", "tv", "book", "song"}


@movie_bp.route("/import", methods=["POST"])
@jwt_required()
def import_titles():
    """Take a list of free-form titles (e.g. pasted from Notes) and return
    match candidates for each, so the frontend can let the user confirm before
    bulk-adding to their watchlist.

    media_type routes the lookup: 'movie'/'tv' -> OMDb, 'book' -> Open Library,
    'song' -> iTunes, and 'all' (auto-detect) probes every source per line."""
    data = request.get_json() or {}
    lines = _expand_csv_export(data.get("lines") or [])
    media_type = data.get("media_type", "all")

    if media_type not in IMPORT_MEDIA_TYPES:
        return jsonify({"message": f"Invalid media_type: {media_type}"}), 400

    # Clean + dedupe queries, preserving original line text for display
    seen_queries = set()
    queries = []
    for line in lines:
        q = _clean_import_line(line)
        if not q:
            continue
        key = q.lower()
        if key in seen_queries:
            continue
        seen_queries.add(key)
        queries.append({"original": line, "query": q})
        if len(queries) >= IMPORT_MAX_LINES:
            break

    # Fan the lookups out in parallel. Sequentially, 50 lines x 10s worst-case
    # timeout could hold a gunicorn thread for minutes; with 5 concurrent
    # fetches the worst case drops sharply. Order is preserved. In auto ('all')
    # mode each line probes up to three sources, so this is the heaviest path.
    matches = []
    if queries:
        with ThreadPoolExecutor(max_workers=5) as pool:
            candidate_lists = list(
                pool.map(
                    lambda e: _import_candidates(e["query"], media_type),
                    queries,
                )
            )
        for entry, candidates in zip(queries, candidate_lists):
            matches.append({
                "query": entry["original"],
                "cleaned": entry["query"],
                "candidates": candidates,
            })

    return jsonify({
        "matches": matches,
        "truncated": len(queries) >= IMPORT_MAX_LINES,
        "max_lines": IMPORT_MAX_LINES,
    }), 200


@movie_bp.route("/<imdb_id>", methods=["GET"])
@jwt_required()
def get_movie(imdb_id):
    try:
        response = requests.get(
            Config.OMDB_BASE_URL,
            params={"apikey": Config.OMDB_API_KEY, "i": imdb_id, "plot": "full"},
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[movies] OMDb lookup failed for {imdb_id}: {e}")
        return jsonify({"message": "Movie lookup failed, try again shortly"}), 502

    if data.get("Response") == "False":
        return jsonify({"message": data.get("Error", "Title not found")}), 404

    # Everything OMDb knows about a title. Ratings arrive as a list of
    # {Source, Value} dicts; flatten the non-IMDb ones.
    ratings = {
        r.get("Source"): r.get("Value")
        for r in data.get("Ratings", [])
        if isinstance(r, dict)
    }

    runtime_str = _na_to_none(data.get("Runtime"))
    runtime_minutes = None
    if runtime_str:
        digits = "".join(ch for ch in runtime_str if ch.isdigit())
        runtime_minutes = int(digits) if digits else None

    omdb_type = data.get("Type")
    return jsonify({
        "imdb_id": data.get("imdbID"),
        "title": data.get("Title"),
        "year": data.get("Year"),
        "movie_type": omdb_type,
        "media_type": INTERNAL_TYPE_MAP.get(omdb_type, "movie"),
        "plot": _na_to_none(data.get("Plot")),
        "poster": _na_to_none(data.get("Poster")),
        "runtime": runtime_str,
        "runtime_minutes": runtime_minutes,
        "genre": _na_to_none(data.get("Genre")),
        "director": _na_to_none(data.get("Director")),
        "writer": _na_to_none(data.get("Writer")),
        "actors": _na_to_none(data.get("Actors")),
        "imdb_rating": _na_to_none(data.get("imdbRating")),
        "imdb_votes": _na_to_none(data.get("imdbVotes")),
        "rotten_tomatoes": _na_to_none(ratings.get("Rotten Tomatoes")),
        "metascore": _na_to_none(data.get("Metascore")),
        "rated": _na_to_none(data.get("Rated")),
        "released": _na_to_none(data.get("Released")),
        "awards": _na_to_none(data.get("Awards")),
        "box_office": _na_to_none(data.get("BoxOffice")),
        "language": _na_to_none(data.get("Language")),
        "country": _na_to_none(data.get("Country")),
        "total_seasons": _na_to_none(data.get("totalSeasons")),
    }), 200


def _clean_source(source):
    """Normalize one Watchmode source row to what the frontend cares about."""
    return {
        "name": source.get("name"),
        "type": source.get("type"),  # sub / free / tve / rent / buy
        "region": source.get("region"),
        "format": source.get("format"),
        "price": source.get("price"),
        "web_url": source.get("web_url"),
        "ios_url": source.get("ios_url"),
        "android_url": source.get("android_url"),
    }


def _fetch_streaming_from_watchmode(imdb_id):
    """Call Watchmode for fresh streaming data. Returns list of cleaned sources."""
    if not Config.WATCHMODE_API_KEY:
        return []

    try:
        response = requests.get(
            f"{Config.WATCHMODE_BASE_URL}/title/{imdb_id}/sources/",
            params={
                "apiKey": Config.WATCHMODE_API_KEY,
                "regions": "US",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[streaming] Watchmode request failed: {e}")
        return []

    if response.status_code != 200:
        print(f"[streaming] Watchmode returned {response.status_code}: {response.text[:200]}")
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    if not isinstance(data, list):
        return []

    return [_clean_source(s) for s in data if s.get("name")]


def _sort_sources_by_user_taps(sources, user_id):
    """Float services the user has tapped before to the top of each type group.
    Keeps the type-group ordering caller already expects (subs/free first, then rent/buy)
    by sorting WITHIN each type by (tap count desc, name)."""
    taps = StreamingServiceTap.query.filter_by(user_id=user_id).all()
    tap_counts = {t.service_name: t.tap_count for t in taps}

    def sort_key(src):
        name = src.get("name") or ""
        # Negative count so higher counts come first; tiebreak alphabetical
        return (-tap_counts.get(name, 0), name.lower())

    by_type = {}
    for s in sources:
        by_type.setdefault(s.get("type"), []).append(s)
    for t in by_type:
        by_type[t].sort(key=sort_key)

    # Preserve the original type ordering (first appearance wins)
    seen_types = []
    for s in sources:
        if s.get("type") not in seen_types:
            seen_types.append(s.get("type"))
    return [s for t in seen_types for s in by_type[t]]


@movie_bp.route("/<imdb_id>/streaming", methods=["GET"])
@jwt_required()
def get_streaming(imdb_id):
    user_id = int(get_jwt_identity())
    force_refresh = request.args.get("refresh") == "true"
    cutoff = datetime.utcnow() - timedelta(days=STREAMING_CACHE_DAYS)

    cache = StreamingCache.query.filter_by(imdb_id=imdb_id).first()
    if cache and cache.cached_at > cutoff and not force_refresh:
        try:
            sources = json.loads(cache.data)
            return jsonify({
                "sources": _sort_sources_by_user_taps(sources, user_id),
                "cached_at": cache.cached_at.isoformat(),
                "cached": True,
            }), 200
        except ValueError:
            pass  # fall through and re-fetch if cached JSON is corrupt

    sources = _fetch_streaming_from_watchmode(imdb_id)

    if cache:
        cache.data = json.dumps(sources)
        cache.cached_at = datetime.utcnow()
    else:
        cache = StreamingCache(
            imdb_id=imdb_id,
            data=json.dumps(sources),
            cached_at=datetime.utcnow(),
        )
        db.session.add(cache)
    db.session.commit()

    return jsonify({
        "sources": _sort_sources_by_user_taps(sources, user_id),
        "cached_at": cache.cached_at.isoformat(),
        "cached": False,
    }), 200


@movie_bp.route("/streaming/tap", methods=["POST"])
@jwt_required()
def log_streaming_tap():
    """Increment the user's tap count for a streaming service so future
    streaming-modal results float their commonly-used services to the top."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    service_name = (data.get("service_name") or "").strip()
    if not service_name:
        return jsonify({"message": "service_name required"}), 400

    tap = StreamingServiceTap.query.filter_by(
        user_id=user_id, service_name=service_name
    ).first()
    if tap:
        tap.tap_count += 1
        tap.last_tapped_at = datetime.utcnow()
    else:
        tap = StreamingServiceTap(
            user_id=user_id,
            service_name=service_name,
            tap_count=1,
        )
        db.session.add(tap)
    db.session.commit()
    return jsonify({
        "service_name": tap.service_name,
        "tap_count": tap.tap_count,
    }), 200
