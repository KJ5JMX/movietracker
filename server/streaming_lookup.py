"""
Provider-agnostic streaming availability lookup.

The rest of the app calls `lookup(...)` and never cares which backend answered.
Today the backend is JustWatch (free, unofficial); the day there's revenue,
flip `STREAMING_PROVIDER=watchmode` in the environment and the paid, licensed
source takes over with zero changes to callers. That's the whole point: this is
a bridge, built to be swapped.

Each provider returns a list of normalized source dicts, or None on a hard
failure (network/blocked) so the caller can keep serving the last good cache and
let the crowdsourced reports cover the gap instead of showing an empty shelf.

Normalized source shape (superset of what the app already renders):
    name          e.g. "Netflix"
    type          sub | free | rent | buy   (grouping buckets the app uses)
    region        e.g. "US"
    format        e.g. "HD" / "4K"          (may be None)
    price         e.g. "$3.99"              (may be None)
    web_url       deeplink / watch URL      (may be None)
    ios_url       same URL (universal links route it into the app)
    android_url   same URL
    icon          absolute logo URL for the service (may be None)
"""

from config import Config


_JW_GRAPHQL_URL = "https://apis.justwatch.com/graphql"

# JustWatch refuses the library's bare request from a datacenter IP. Posting with
# browser-like headers gets past that. We still use the library's query builder
# and response parser, so we ride its current schema and only override transport.
_JW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.justwatch.com",
    "Referer": "https://www.justwatch.com/",
}


# JustWatch monetization_type -> the app's grouping buckets. Anything we don't
# recognize (e.g. "cinema") is dropped so it never lands in a wrong group.
_JW_TYPE_MAP = {
    "flatrate": "sub",
    "flatrate_and_buy": "sub",
    "free": "free",
    "ads": "free",
    "fast": "free",
    "rent": "rent",
    "buy": "buy",
}


def _dedupe(sources):
    """Collapse duplicate (service, type) rows, keeping the first (best) one."""
    seen = set()
    out = []
    for s in sources:
        key = (s.get("name"), s.get("type"))
        if not s.get("name") or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# JustWatch provider (free, unofficial — the bridge)
# ---------------------------------------------------------------------------

def _justwatch_fetch(imdb_id, title, year, country):
    """Look a title up on JustWatch and normalize its offers.

    Returns a list (possibly empty = "found it, streaming nowhere") on success,
    or None on a hard failure so the caller falls back instead of caching empty.
    Anchored to imdb_id: among the search hits we pick the one whose IMDb id
    matches, so an ambiguous title never resolves to the wrong film.
    """
    if not title:
        return None
    try:
        import httpx
        from simplejustwatchapi.query import (
            prepare_search_request,
            parse_search_response,
        )
    except ImportError:
        print("[streaming] simple-justwatch-python-api not installed")
        return None

    try:
        request = prepare_search_request(title, country, "en", 5, True)
        resp = httpx.post(
            _JW_GRAPHQL_URL, json=request, headers=_JW_HEADERS, timeout=15
        )
        resp.raise_for_status()
        results = parse_search_response(resp.json()) or []
    except Exception as e:  # network, blocked, schema drift — treat as failure
        print(f"[streaming] JustWatch lookup failed for {title!r}: {e}")
        return None

    if not results:
        return []  # genuinely nothing found — a valid, cacheable answer

    # Anchor to the exact title by IMDb id; fall back to year, then first hit.
    entry = next((r for r in results if r.imdb_id and r.imdb_id == imdb_id), None)
    if entry is None and year:
        try:
            y = int(str(year)[:4])
            entry = next((r for r in results if r.release_year == y), None)
        except (TypeError, ValueError):
            pass
    if entry is None:
        entry = results[0]

    sources = []
    for o in entry.offers or []:
        bucket = _JW_TYPE_MAP.get((o.monetization_type or "").lower())
        if not bucket:
            continue
        sources.append({
            "name": o.name,
            "type": bucket,
            "region": country,
            "format": o.presentation_type or None,
            # Numeric price (app formats it as $X.XX). price_string can be
            # oddly formatted per-locale, so prefer the raw value.
            "price": o.price_value,
            "web_url": o.url or None,
            "ios_url": o.url or None,
            "android_url": o.url or None,
            "icon": o.icon or None,
        })
    return _dedupe(sources)


# ---------------------------------------------------------------------------
# Watchmode provider (paid, licensed — the graduation target, stubbed live)
# ---------------------------------------------------------------------------

def _watchmode_fetch(imdb_id, title, year, country):
    """Licensed Watchmode source. Wired and ready; only pays off once you buy a
    commercial key (Config.WATCHMODE_API_KEY). Same normalized shape as JustWatch
    so switching providers is purely a config flip."""
    if not Config.WATCHMODE_API_KEY:
        return None
    import requests
    try:
        resp = requests.get(
            f"{Config.WATCHMODE_BASE_URL}/title/{imdb_id}/sources/",
            params={"apiKey": Config.WATCHMODE_API_KEY, "regions": country},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[streaming] Watchmode request failed: {e}")
        return None
    if resp.status_code != 200:
        print(f"[streaming] Watchmode {resp.status_code}: {resp.text[:160]}")
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    # Watchmode "type": sub/free/tve/rent/buy -> our buckets
    wm_map = {"sub": "sub", "free": "free", "tve": "sub", "rent": "rent", "buy": "buy"}
    sources = []
    for s in data:
        if not s.get("name"):
            continue
        sources.append({
            "name": s.get("name"),
            "type": wm_map.get(s.get("type"), "sub"),
            "region": s.get("region"),
            "format": s.get("format"),
            "price": s.get("price"),
            "web_url": s.get("web_url"),
            "ios_url": s.get("ios_url"),
            "android_url": s.get("android_url"),
            "icon": None,  # Watchmode logos need a separate /sources/ lookup
        })
    return _dedupe(sources)


_PROVIDERS = {
    "justwatch": _justwatch_fetch,
    "watchmode": _watchmode_fetch,
}


def lookup(imdb_id, title=None, year=None, country=None):
    """Fetch streaming sources for a title from the configured provider.

    Returns a list of normalized sources (possibly empty) on success, or None on
    a hard failure so the caller can keep the last good cache and lean on the
    crowdsourced reports.
    """
    country = country or getattr(Config, "STREAMING_REGION", "US")
    provider = getattr(Config, "STREAMING_PROVIDER", "justwatch")
    fetch = _PROVIDERS.get(provider, _justwatch_fetch)
    return fetch(imdb_id, title, year, country)


def debug(title="Back to the Future", country=None):
    """Raw diagnostic: exactly what JustWatch returns before our mapping, so a
    'no offers' result can be told apart from a mapping/anchor bug. Admin-only."""
    country = country or getattr(Config, "STREAMING_REGION", "US")
    out = {"title": title, "country": country, "entries": [], "error": None}
    try:
        import httpx
        from simplejustwatchapi.query import (
            prepare_search_request,
            parse_search_response,
        )
        request = prepare_search_request(title, country, "en", 5, True)
        resp = httpx.post(
            _JW_GRAPHQL_URL, json=request, headers=_JW_HEADERS, timeout=15
        )
        resp.raise_for_status()
        results = parse_search_response(resp.json()) or []
        for r in results:
            offers = r.offers or []
            out["entries"].append({
                "title": r.title,
                "year": r.release_year,
                "imdb_id": r.imdb_id,
                "raw_offer_count": len(offers),
                "monetization_types_raw": sorted(
                    {(o.monetization_type or "?") for o in offers}
                ),
                "services": sorted({(o.name or "?") for o in offers})[:15],
            })
    except Exception as e:
        out["error"] = repr(e)
    return out


def health_check():
    """Canary: does the live provider answer right now? Drives the admin status
    dot. Uses a stable, always-available title (Back to the Future, 1985)."""
    from datetime import datetime

    provider = getattr(Config, "STREAMING_PROVIDER", "justwatch")
    try:
        sources = lookup("tt0088763", "Back to the Future", 1985)
    except Exception as e:  # never let the health check itself throw
        sources = None
        err = str(e)
    else:
        err = None

    ok = sources is not None and len(sources) > 0
    return {
        "ok": ok,
        "provider": provider,
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "sample_count": len(sources) if sources else 0,
        "detail": err or ("healthy" if ok else "no offers returned"),
    }
