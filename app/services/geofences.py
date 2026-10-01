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
            if key in geofence_map:
                geofence_map[key].in_teslamate = True
            elif r["latitude"] is not None and r["longitude"] is not None:
                geofence_map[key] = GeofenceItem(
                    id=f"tm-{r['id']}",
                    name=name,
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    radius_meters=int(r["radius"] or 350),
                    address_aliases=[],
                    in_teslamate=True
                )
    except Exception as e:
        print(f"[Geofences] Note: Could not query native geofences: {e}")

    return list(geofence_map.values())


async def sync_geofences_with_teslamate(db: Database, config: AppConfig) -> Tuple[List[GeofenceItem], Dict[str, int]]:
    """
    Bi-directionally synchronizes geofences between TeslaMate-Digest and TeslaMate's PostgreSQL database:
    1. Reads all native geofences from TeslaMate (`geofences` table).
       Any geofence created in TeslaMate is imported into Digest config (preserving any aliases).
    2. Writes any custom geofences created in TeslaMate-Digest back into TeslaMate's `geofences` table,
       so TeslaMate itself recognizes them for tracking and charging.
    """
    stats = {"imported": 0, "pushed": 0, "updated": 0, "total": 0}
    if not config:
        return [], stats

    # Map existing Digest geofences by lower-cased name
    digest_map: Dict[str, GeofenceItem] = {}
    for g in getattr(config, "geofences", []):
        if g.name and g.name.strip():
            digest_map[g.name.strip().lower()] = g

    # 1. Fetch from TeslaMate PostgreSQL
    tm_rows = []
    try:
        tm_rows = await db.fetch("SELECT id, name, latitude, longitude, radius FROM geofences WHERE name IS NOT NULL;")
    except Exception as e:
        print(f"[GeofenceSync] Note: Could not query native TeslaMate geofences: {e}")

    tm_names = set()
    for r in tm_rows:
        r_name = str(r["name"]).strip()
        key = r_name.lower()
        tm_names.add(key)
        lat = float(r["latitude"]) if r["latitude"] is not None else 0.0
        lon = float(r["longitude"]) if r["longitude"] is not None else 0.0
        rad = int(r["radius"] or 350)

        if key in digest_map:
            existing = digest_map[key]
            existing.in_teslamate = True
            # If coordinates were missing or default in Digest, take from TeslaMate
            if existing.latitude == 0 and existing.longitude == 0:
                existing.latitude = lat
                existing.longitude = lon
                existing.radius_meters = rad
                stats["updated"] += 1
        else:
            # Import new geofence from TeslaMate into Digest
            new_item = GeofenceItem(
                id=f"tm-{r['id']}",
                name=r_name,
                latitude=lat,
                longitude=lon,
                radius_meters=rad,
                address_aliases=[],
                in_teslamate=True
            )
            digest_map[key] = new_item
            stats["imported"] += 1

    # 2. Push any Digest geofences into TeslaMate if not already present
    for key, g in digest_map.items():
        if key not in tm_names:
            try:
                existing_pg = await db.fetchrow("SELECT id FROM geofences WHERE lower(name) = lower($1);", g.name.strip())
                if existing_pg:
                    await db.fetch("""
                        UPDATE geofences 
                        SET latitude = $1, longitude = $2, radius = $3, updated_at = NOW() 
                        WHERE id = $4;
                    """, g.latitude, g.longitude, g.radius_meters, existing_pg["id"])
                    g.in_teslamate = True
                    stats["updated"] += 1
                else:
                    await db.fetch("""
                        INSERT INTO geofences (name, latitude, longitude, radius, billing_type, inserted_at, updated_at)
                        VALUES ($1, $2, $3, $4, 'per_kwh', NOW(), NOW());
                    """, g.name.strip(), g.latitude, g.longitude, g.radius_meters)
                    g.in_teslamate = True
                    stats["pushed"] += 1
            except Exception as e:
                print(f"[GeofenceSync] Error pushing geofence '{g.name}' to TeslaMate: {e}")
        else:
            g.in_teslamate = True

    config.geofences = list(digest_map.values())
    stats["total"] = len(config.geofences)
    stats["imported_from_teslamate"] = stats["imported"]
    stats["exported_to_teslamate"] = stats["pushed"]

    # Persist updated config in SQLite
    from app.config import save_config
    try:
        save_config(config)
    except Exception as e:
        print(f"[GeofenceSync] Error saving config after sync: {e}")

    return config.geofences, stats


async def get_effective_service_urls(db: Database, config: Optional[AppConfig] = None) -> Tuple[str, str]:
    """
    Returns (teslamate_url, grafana_url).
    If either is not explicitly configured or points to internal docker network (e.g. grafana:3000),
    auto-detects from TeslaMate PostgreSQL `settings` table.
    """
    teslamate_url = (getattr(config, "teslamate_url", "") or "").strip().rstrip("/")
    grafana_url = (getattr(config, "grafana_url", "") or "").strip().rstrip("/")

    need_tm = not teslamate_url
    need_graf = not grafana_url or "grafana:3000" in grafana_url

    if need_tm or need_graf:
        try:
            row = await db.fetchrow("SELECT base_url, grafana_url FROM settings LIMIT 1;")
            if row:
                if need_tm and row.get("base_url"):
                    teslamate_url = str(row["base_url"]).strip().rstrip("/")
                if need_graf and row.get("grafana_url"):
                    grafana_url = str(row["grafana_url"]).strip().rstrip("/")
        except Exception as e:
            print(f"[URLs] Note: Could not auto-detect URLs from settings table: {e}")

    if not teslamate_url:
        teslamate_url = "http://localhost:4000"
    if not grafana_url or "grafana:3000" in grafana_url:
        teslamate_host = teslamate_url.split(":")[1] if ":" in teslamate_url else "//localhost"
        grafana_url = f"http:{teslamate_host}:3000"

    return teslamate_url, grafana_url


def get_grafana_dashboard_urls(
    grafana_base_url: str,
    car_id: Optional[int] = None,
    dashboards_config: Optional[Any] = None
) -> Dict[str, str]:
    """
    Returns direct URLs for all TeslaMate Grafana dashboards with vehicle filtering.
    Dynamically uses configured or discovered dashboard paths/UIDs.
    """
    base = grafana_base_url.rstrip("/")
    car_param = f"?var-car_id={car_id}" if car_id else ""

    from app.config import GrafanaDashboardsConfig
    cfg = dashboards_config or GrafanaDashboardsConfig()
    if isinstance(cfg, dict):
        cfg = GrafanaDashboardsConfig(**cfg)

    def _url(path: str, add_car: bool = True) -> str:
        p = (path or "").strip().lstrip("/")
        if not p:
            return ""
        if not p.startswith("d/"):
            p = f"d/{p}"
        param = car_param if add_car else ""
        return f"{base}/{p}{param}"

    return {
        "grafana_base_url": base,
        "grafana_charging_url": _url(getattr(cfg, "charging", "-pkIkhmRz/charging-stats")),
        "grafana_charge_level_url": _url(getattr(cfg, "charge_level", "WopVO_mgz/charge-level")),
        "grafana_charges_url": _url(getattr(cfg, "charges", "TSmNYvRRk/charges")),
        "grafana_drives_url": _url(getattr(cfg, "drives", "Y8upc6ZRk/drives")),
        "grafana_drive_stats_url": _url(getattr(cfg, "drive_stats", "_7WkNSyWk/drive-stats")),
        "grafana_efficiency_url": _url(getattr(cfg, "efficiency", "fu4SiQgWz/efficiency")),
        "grafana_battery_url": _url(getattr(cfg, "battery_health", "jchmRiqUfXgTM/battery-health")),
        "grafana_vampire_url": _url(getattr(cfg, "vampire_drain", "zhHx2Fggk/vampire-drain")),
        "grafana_overview_url": _url(getattr(cfg, "overview", "kOuP_Fggz/overview")),
        "grafana_mileage_url": _url(getattr(cfg, "mileage", "NjtMTFggz/mileage")),
        "grafana_trip_url": _url(getattr(cfg, "trip", "FkUpJpQZk/trip")),
        "grafana_locations_url": _url(getattr(cfg, "locations", "ZzhF-aRWz/locations"), add_car=False),
        "grafana_visited_url": _url(getattr(cfg, "visited", "RG_DxSmgk/visited"), add_car=False),
        "grafana_updates_url": _url(getattr(cfg, "updates", "IiC07mgWz/updates")),
        "grafana_timeline_url": _url(getattr(cfg, "timeline", "SUBgwtigz/timeline")),
        "grafana_achievements_url": _url(getattr(cfg, "achievements", "c6020bdb-a2c7-4b1c-ab2c-fd34ab836c6e/achievements")),
    }


async def discover_grafana_dashboards(grafana_base_url: str, api_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Dynamically queries Grafana's search API (/api/search?type=dash-db) to find
    all installed dashboards and map their exact UIDs and paths.
    """
    import httpx

    token = (api_token or "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    candidate_hosts = []
    if grafana_base_url:
        candidate_hosts.append(grafana_base_url.rstrip("/"))
    candidate_hosts.append("http://grafana:3000")
    candidate_hosts.append("http://localhost:3000")

    dashboards = []
    error_msg = ""
    async with httpx.AsyncClient(timeout=4.0) as client:
        for host in candidate_hosts:
            url = f"{host}/api/search?type=dash-db"
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        dashboards = data
                        break
                elif resp.status_code == 401:
                    error_msg = "Grafana API requires a Service Account or API Token (401 Unauthorized)."
                    break
                elif resp.status_code == 403:
                    error_msg = "Grafana API token lacks search permissions (403 Forbidden)."
                    break
                else:
                    if not error_msg:
                        error_msg = f"Grafana returned status {resp.status_code}"
            except Exception as e:
                if not error_msg:
                    error_msg = str(e)

    if not dashboards:
        return {"success": False, "error": error_msg or "Could not connect to Grafana API", "dashboards": [], "mapped": {}}

    mapped: Dict[str, str] = {}
    items_list = []
    for d in dashboards:
        uid = d.get("uid")
        title = d.get("title", "")
        slug = d.get("slug") or title.lower().replace(" ", "-")
        d_url = d.get("url", "")
        path = d_url.replace("/d/", "", 1) if d_url.startswith("/d/") else f"{uid}/{slug}"
        items_list.append({"uid": uid, "title": title, "path": path, "url": d_url})

        t_low = title.lower()
        if "charging" in t_low and ("stat" in t_low or "cost" in t_low):
            mapped["charging"] = path
        elif "charge" in t_low and "level" in t_low:
            mapped["charge_level"] = path
        elif "charges" in t_low:
            mapped["charges"] = path
        elif "efficiency" in t_low or "consumption" in t_low:
            mapped["efficiency"] = path
        elif "battery" in t_low or "degradation" in t_low:
            mapped["battery_health"] = path
        elif "drive" in t_low and "stat" in t_low:
            mapped["drive_stats"] = path
        elif "drive" in t_low or "trip" in t_low:
            mapped.setdefault("drives", path)
        elif "vampire" in t_low or "phantom" in t_low:
            mapped["vampire_drain"] = path
        elif "overview" in t_low:
            mapped["overview"] = path
        elif "mileage" in t_low:
            mapped["mileage"] = path
        elif "achievement" in t_low or "gamif" in t_low:
            mapped["achievements"] = path

    return {
        "success": True,
        "count": len(items_list),
        "dashboards": items_list,
        "mapped": mapped
    }


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
