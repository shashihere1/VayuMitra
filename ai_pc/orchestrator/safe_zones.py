"""Clean-air 'safe zones' and nearest-zone lookup by haversine distance.

Coordinates are real Mumbai open/green spaces (good for a Mumbai-set demo).
Swap these for the venue's coordinates on site.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

# name / lat / lon — 4-5 real clean-air spots.
SAFE_ZONES: List[Dict[str, float]] = [
    {"name": "Sanjay Gandhi National Park", "lat": 19.2147, "lon": 72.9106},
    {"name": "Shivaji Park (open ground)", "lat": 19.0281, "lon": 72.8397},
    {"name": "Hanging Gardens, Malabar Hill", "lat": 18.9560, "lon": 72.8050},
    {"name": "Maharashtra Nature Park", "lat": 19.0490, "lon": 72.8560},
    {"name": "Powai Lake promenade", "lat": 19.1273, "lon": 72.9057},
]

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def nearest(lat: float, lon: float,
            zones: Optional[List[Dict[str, float]]] = None) -> Optional[Dict[str, float]]:
    """Return the nearest zone as ``{name, lat, lon, distance_m}`` or None."""
    zones = zones or SAFE_ZONES
    if not zones:
        return None
    best: Optional[Tuple[float, Dict[str, float]]] = None
    for z in zones:
        d = haversine_m(lat, lon, z["lat"], z["lon"])
        if best is None or d < best[0]:
            best = (d, z)
    d, z = best
    return {"name": z["name"], "lat": z["lat"], "lon": z["lon"], "distance_m": round(d, 1)}
