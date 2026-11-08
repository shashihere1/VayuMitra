"""Geo-bucketing + haversine for the cloud aggregator (P2).

Buckets device/alert coordinates into a coarse grid of named zones so the
dashboard/phone can show city-wide hotspots.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

_EARTH_RADIUS_M = 6_371_000.0
GRID_DEG = 0.02  # ~2.2 km cells


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bucket(lat: float, lon: float) -> Tuple[float, float]:
    """Snap a coordinate to the center of its grid cell."""
    clat = round(lat / GRID_DEG) * GRID_DEG
    clon = round(lon / GRID_DEG) * GRID_DEG
    return round(clat, 4), round(clon, 4)


def level_for_aqi(aqi: float) -> str:
    if aqi < 50:
        return "low"
    if aqi < 100:
        return "moderate"
    if aqi < 150:
        return "high"
    return "critical"


def aggregate(points: List[Dict]) -> List[Dict]:
    """``points`` = list of ``{lat, lon, aqi}``; returns zone dicts with the max
    observed AQI per grid cell.
    """
    cells: Dict[Tuple[float, float], Dict] = {}
    for p in points:
        key = bucket(p["lat"], p["lon"])
        aqi = float(p.get("aqi", 0.0))
        cur = cells.get(key)
        if cur is None or aqi > cur["aqi"]:
            cells[key] = {"lat": key[0], "lon": key[1], "aqi": aqi}
    zones = []
    for i, ((clat, clon), z) in enumerate(sorted(cells.items())):
        zones.append({
            "name": f"Zone {i+1} ({clat:.2f},{clon:.2f})",
            "lat": clat, "lon": clon,
            "aqi": round(z["aqi"], 1),
            "level": level_for_aqi(z["aqi"]),
        })
    return zones
