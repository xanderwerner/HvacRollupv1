"""Google Places API client (legacy Text Search + Place Details).

Uses only the stdlib (urllib) so the data run has zero pip dependencies
beyond openpyxl. This is v1's discovery + sizing engine.
"""
import json
import ssl
import time
import urllib.parse
import urllib.request
from typing import Optional

import config

_TEXT_SEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

# macOS framework Python ships without a CA bundle — use certifi's if present.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


def _get(url: str, params: dict) -> dict:
    params = {**params, "key": config.GOOGLE_PLACES_API_KEY}
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=25, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def text_search(query: str) -> list[dict]:
    """Return raw Places results for a text query (one page = up to 20)."""
    data = _get(_TEXT_SEARCH, {"query": query})
    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(
            f"Places Text Search failed: {status} — {data.get('error_message','')}"
        )
    return data.get("results", [])


def place_details(place_id: str) -> dict:
    """Fetch website / phone / address detail for a single place."""
    fields = "name,website,formatted_phone_number,formatted_address,business_status"
    data = _get(_DETAILS, {"place_id": place_id, "fields": fields})
    if data.get("status") != "OK":
        return {}
    return data.get("result", {})


def discover(cities: list[str], trades: dict[str, str], pause: float = 0.1) -> list[dict]:
    """Sweep every (trade x city) combo; tag each raw result with our trade/city."""
    out = []
    for trade_label, term in trades.items():
        for city in cities:
            query = f"{term} in {city} AZ"
            try:
                results = text_search(query)
            except Exception as exc:  # keep sweeping even if one query fails
                print(f"  ! query failed [{query}]: {exc}")
                continue
            for r in results:
                r["_trade"] = trade_label
                r["_city"] = city
            out.extend(results)
            print(f"  · {query:38s} -> {len(results):2d} results")
            time.sleep(pause)
    return out
