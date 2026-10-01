import math
import re
from typing import List, Dict, Tuple, Optional, Any
from app.db import Database
from app.config import AppConfig, GeofenceItem


def haversine_distance_m(lat1: Optional[float], lon1: Optional[float], lat2: Optional[float], lon2: Optional[float]) -> float:
    """
    Computes great-circle distance between two GPS coordinates in meters.
    Returns infinity if any coordinate is missing.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float("inf")
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c
    except Exception:
        return float("inf")


async def load_effective_geofences(db: Database, config: Optional[AppConfig] = None) -> List[GeofenceItem]:
    """
    Loads all active geofences from:
    1. TeslaMate-Digest configuration (`config.geofences`).
    2. Native TeslaMate PostgreSQL `geofences` table (if any defined).
    """
    geofence_map: Dict[str, GeofenceItem] = {}

    # 1. Load from app config
    if config:
        for g in getattr(config, "geofences", []):
            if g.name and g.name.strip():
                geofence_map[g.name.strip().lower()] = g

    # 2. Query TeslaMate native geofences table
    try:
        rows = await db.fetch("SELECT id, name, latitude, longitude, radius FROM geofences WHERE name IS NOT NULL;")
        for r in rows:
            name = str(r["name"]).strip()
            key = name.lower()
            if key not in geofence_map and r["latitude"] is not None and r["longitude"] is not None:
                geofence_map[key] = GeofenceItem(
                    id=f"tm-{r['id']}",
                    name=name,
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    radius_meters=int(r["radius"] or 350),
                    address_aliases=[]
                )
    except Exception as e:
        print(f"[Geofences] Note: Could not query native geofences: {e}")

    return list(geofence_map.values())


async def load_address_coordinates_cache(db: Database) -> Dict[str, Tuple[float, float]]:
    """
    Returns an in-memory dictionary mapping address strings/roads to (latitude, longitude)
    so that even raw street addresses can be matched using coordinate proximity.
    """
    cache: Dict[str, Tuple[float, float]] = {}
    try:
        rows = await db.fetch("""
            SELECT 
                lower(coalesce(name, road)) as loc_name,
                lower(coalesce(city, '')) as city,
                avg(latitude) as lat,
                avg(longitude) as lon
            FROM addresses
            WHERE coalesce(name, road) IS NOT NULL AND latitude IS NOT NULL
            GROUP BY 1, 2;
        """)
        for r in rows:
            name = (r["loc_name"] or "").strip()
            city = (r["city"] or "").strip()
            if name and r["lat"] is not None and r["lon"] is not None:
                coords = (float(r["lat"]), float(r["lon"]))
                cache[name] = coords
                if city:
                    cache[f"{name} {city}"] = coords
                    cache[f"{name}, {city}"] = coords
    except Exception as e:
        print(f"[Geofences] Error loading address coordinates cache: {e}")
    return cache


def matches_location_point(
    target: str,
    drive_lat: Optional[float],
    drive_lon: Optional[float],
    drive_name: str,
    drive_city: str,
    geofences: List[GeofenceItem],
    addr_cache: Optional[Dict[str, Tuple[float, float]]] = None
) -> bool:
    """
    Determines if a drive start or end matches a target location string.
    Matches across:
    1. Geofence radius proximity (Haversine distance <= radius).
    2. Geofence name and configured address aliases.
    3. Direct street/address substring matching.
    4. Address coordinate proximity (if target is a street in the cache, within 350m).
    """
    if not target or not target.strip():
        return False

    t_clean = target.strip().lower()
    # Strip any trailing parenthesized details, e.g. "11th Street (Golden)" -> "11th street"
    t_bare = re.sub(r"\s*\(.*?\)\s*", "", t_clean).strip()

    d_name_clean = (drive_name or "").strip().lower()
    d_city_clean = (drive_city or "").strip().lower()
    full_loc_clean = f"{d_name_clean} {d_city_clean}".strip()

    # 1. CHECK GEOFENCES
    for g in geofences:
        g_name_lower = g.name.strip().lower()
        aliases_lower = [a.strip().lower() for a in g.address_aliases if a.strip()]

        # Target matches this geofence by name or alias
        target_matches_geo = (
            t_clean == g_name_lower or
            t_bare == g_name_lower or
            t_clean in aliases_lower or
            t_bare in aliases_lower or
            g_name_lower in t_clean or
            g_name_lower in t_bare
        )

        if target_matches_geo:
            # Check coordinate distance to geofence center
            if drive_lat is not None and drive_lon is not None:
                dist = haversine_distance_m(drive_lat, drive_lon, g.latitude, g.longitude)
                if dist <= g.radius_meters:
                    return True

            # Check if any alias is in the drive's address string
            for alias in aliases_lower:
                if alias in d_name_clean or alias in full_loc_clean:
                    return True

            # Check if geofence name itself is in drive's name
            if g_name_lower in full_loc_clean:
                return True

        # Reverse check: if drive is inside geofence G, does target match any alias of G?
        if drive_lat is not None and drive_lon is not None:
            dist = haversine_distance_m(drive_lat, drive_lon, g.latitude, g.longitude)
            if dist <= g.radius_meters:
                # Drive is inside geofence G! If target is the geofence name or any of its aliases -> MATCH!
                if (t_clean == g_name_lower or t_bare == g_name_lower or
                    any(t_clean == a or t_bare == a or t_clean in a or a in t_clean for a in aliases_lower)):
                    return True

    # 2. DIRECT SUBSTRING MATCH
    if t_clean in d_name_clean or t_clean in full_loc_clean:
        return True
    if t_bare and (t_bare in d_name_clean or t_bare in full_loc_clean):
        return True

    # 3. ADDRESS COORDINATE PROXIMITY (e.g. user typed a street name, vehicle parked 1 block over)
    if addr_cache and drive_lat is not None and drive_lon is not None:
        matched_coords = addr_cache.get(t_clean) or addr_cache.get(t_bare)
        if not matched_coords:
            # Try partial lookup
            for c_name, coords in addr_cache.items():
                if t_bare and (t_bare == c_name or t_bare in c_name or c_name in t_bare):
                    matched_coords = coords
                    break

        if matched_coords:
            dist = haversine_distance_m(drive_lat, drive_lon, matched_coords[0], matched_coords[1])
            if dist <= 350.0:  # 350m neighborhood radius
                return True

    return False
