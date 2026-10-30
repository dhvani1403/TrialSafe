"""Distance helpers, geocoding (OpenStreetMap Nominatim, cached) and US regions."""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import httpx

from .db import execute, fetch_one, jsonb

EARTH_MI = 3958.8

# Census regions, used by the fairness audit to group states.
CENSUS_REGION = {
    **dict.fromkeys(["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont",
                     "New Jersey", "New York", "Pennsylvania"], "Northeast"),
    **dict.fromkeys(["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota",
                     "Missouri", "Nebraska", "North Dakota", "South Dakota"], "Midwest"),
    **dict.fromkeys(["Delaware", "Florida", "Georgia", "Maryland", "North Carolina", "South Carolina", "Virginia",
                     "District of Columbia", "West Virginia", "Alabama", "Kentucky", "Mississippi", "Tennessee",
                     "Arkansas", "Louisiana", "Oklahoma", "Texas"], "South"),
    **dict.fromkeys(["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah", "Wyoming",
                     "Alaska", "California", "Hawaii", "Oregon", "Washington"], "West"),
}

# Reference points for the geographic audit: (label, lat, lon, setting, region)
AUDIT_LOCATIONS = [
    ("Philadelphia, PA", 39.9526, -75.1652, "urban", "Northeast"),
    ("New York, NY", 40.7128, -74.0060, "urban", "Northeast"),
    ("Boston, MA", 42.3601, -71.0589, "urban", "Northeast"),
    ("Bangor, ME", 44.8016, -68.7712, "rural", "Northeast"),
    ("Scranton, PA", 41.4090, -75.6624, "small city", "Northeast"),
    ("Chicago, IL", 41.8781, -87.6298, "urban", "Midwest"),
    ("Minneapolis, MN", 44.9778, -93.2650, "urban", "Midwest"),
    ("Sioux Falls, SD", 43.5446, -96.7311, "small city", "Midwest"),
    ("Dodge City, KS", 37.7528, -100.0171, "rural", "Midwest"),
    ("Houston, TX", 29.7604, -95.3698, "urban", "South"),
    ("Atlanta, GA", 33.7490, -84.3880, "urban", "South"),
    ("Jackson, MS", 32.2988, -90.1848, "small city", "South"),
    ("Pikeville, KY", 37.4793, -82.5188, "rural", "South"),
    ("Laredo, TX", 27.5306, -99.4803, "small city", "South"),
    ("Los Angeles, CA", 34.0522, -118.2437, "urban", "West"),
    ("Seattle, WA", 47.6062, -122.3321, "urban", "West"),
    ("Albuquerque, NM", 35.0844, -106.6504, "small city", "West"),
    ("Billings, MT", 45.7833, -108.5007, "small city", "West"),
    ("Elko, NV", 40.8324, -115.7631, "rural", "West"),
]


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_MI * math.asin(math.sqrt(a))


def geocode(query: str) -> List[Dict]:
    q = query.strip().lower()
    if len(q) < 2:
        return []
    cached = fetch_one("SELECT results FROM geocode_cache WHERE query = %s", (q,))
    if cached:
        return cached["results"]
    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "countrycodes": "us", "limit": 6, "addressdetails": 1},
        headers={"User-Agent": "TrialMatch/1.0 (research prototype; contact via repository)"},
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for r in resp.json():
        addr = r.get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or r.get("name")
        state = addr.get("state")
        label = ", ".join(x for x in [city, state] if x) or r.get("display_name", "")[:60]
        if addr.get("postcode") and query.strip().isdigit():
            label = f"{label} {addr['postcode']}"
        results.append({"label": label, "lat": float(r["lat"]), "lon": float(r["lon"]), "state": state})
    execute(
        "INSERT INTO geocode_cache (query, results) VALUES (%s, %s) ON CONFLICT (query) DO NOTHING",
        (q, jsonb(results)),
    )
    return results


def nearest(sites: List[Dict], lat: Optional[float], lon: Optional[float]) -> List[Dict]:
    """Annotate sites with distance and sort nearest first (sites without coordinates last)."""
    out = []
    for s in sites:
        d = None
        if lat is not None and lon is not None and s.get("lat") is not None:
            d = round(haversine_mi(lat, lon, s["lat"], s["lon"]), 1)
        out.append({**s, "distance_mi": d})
    return sorted(out, key=lambda s: (s["distance_mi"] is None, s["distance_mi"] or 0))
