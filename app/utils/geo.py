# utils/geo.py
import math
from typing import Tuple, List

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in kilometers."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def bbox_for_radius(lat: float, lng: float, km: float) -> Tuple[float, float, float, float]:
    """Return lat_min, lat_max, lng_min, lng_max for filtering."""
    lat_delta = km / 111.0
    lng_delta = km / (111.320 * math.cos(math.radians(lat)) or 1e-6)
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta
