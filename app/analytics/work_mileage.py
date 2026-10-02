from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database
from app.config import AppConfig
from app.services.geofences import load_effective_geofences, load_address_coordinates_cache, matches_location_point


async def get_work_mileage_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    routes: List[Dict[str, Any]],
    car_id: Optional[int] = None,
    irs_rate: float = 0.67,
    commute_target_car_id: Optional[int] = None,
    config: Optional[AppConfig] = None
) -> Dict[str, Any]:
    """
    Computes business / work mileage between pairs of configured points
    (addresses or geofences) for mileage deduction and expense logs.
    If commute_target_car_id is configured, commute tracking only applies to that vehicle.
    Uses coordinate-based geofence radius and address proximity matching to seamlessly
    handle GPS drift and micro-variations in street names.
    """
    if not routes:
        return {
            "has_routes": False,
            "total_routes": 0,
            "total_trips": 0,
            "total_miles": 0.0,
            "total_irs_deduction": 0.0,
            "irs_rate": irs_rate,
            "target_car_id": commute_target_car_id,
            "target_car_name": "",
            "routes": []
        }

    # If commute is restricted to a specific vehicle:
    if commute_target_car_id:
        # If this digest is for a specific car that doesn't match the commute vehicle, omit commute section
        if car_id and car_id != commute_target_car_id:
            return {
                "has_routes": False,
                "total_routes": 0,
                "total_trips": 0,
                "total_miles": 0.0,
                "total_irs_deduction": 0.0,
                "irs_rate": irs_rate,
                "target_car_id": commute_target_car_id,
                "target_car_name": "",
                "routes": []
            }
        effective_car_id = commute_target_car_id
    else:
        effective_car_id = car_id

    car_filter = "AND d.car_id = $3" if effective_car_id else ""
    args = [start_date, end_date]
    if effective_car_id:
        args.append(effective_car_id)

    # Load effective geofences and address coordinate cache
    effective_geofences = await load_effective_geofences(db, config)
    addr_cache = await load_address_coordinates_cache(db)

    # Fetch all drives in the window with resolved start/end names and GPS coordinates
    query = f"""
        SELECT 
            d.id,
            d.car_id,
            d.distance * 0.621371 as distance_mi,
            coalesce(g_start.name, a_start.name, a_start.road, '') as start_name,
            coalesce(a_start.city, '') as start_city,
            coalesce(p_start.latitude, a_start.latitude) as start_lat,
            coalesce(p_start.longitude, a_start.longitude) as start_lon,
            coalesce(g_end.name, a_end.name, a_end.road, '') as end_name,
            coalesce(a_end.city, '') as end_city,
            coalesce(p_end.latitude, a_end.latitude) as end_lat,
            coalesce(p_end.longitude, a_end.longitude) as end_lon
        FROM drives d
        LEFT JOIN geofences g_start ON d.start_geofence_id = g_start.id
        LEFT JOIN addresses a_start ON d.start_address_id = a_start.id
        LEFT JOIN positions p_start ON d.start_position_id = p_start.id
        LEFT JOIN geofences g_end ON d.end_geofence_id = g_end.id
        LEFT JOIN addresses a_end ON d.end_address_id = a_end.id
        LEFT JOIN positions p_end ON d.end_position_id = p_end.id
        WHERE d.start_date >= $1 AND d.start_date < $2
          AND d.distance IS NOT NULL AND d.distance > 0
          {car_filter};
    """
    drives = await db.fetch(query, *args)

    target_car_name = ""
    if commute_target_car_id:
        car_row = await db.fetchrow("SELECT name, model FROM cars WHERE id = $1;", commute_target_car_id)
        if car_row:
            target_car_name = f"{car_row['name']} (Model {car_row['model']})"

    route_results = []
    overall_trips = 0
    overall_miles = 0.0

    for r in routes:
        label = r.get("label", "Commute Route")
        pt_a = (r.get("point_a") or "").strip()
        pt_b = (r.get("point_b") or "").strip()
        bidirectional = r.get("bidirectional", True)
        route_car = r.get("target_car_id")
        if route_car is not None and str(route_car).strip():
            try:
                route_car_id = int(route_car)
            except (ValueError, TypeError):
                route_car_id = None
        else:
            route_car_id = None

        if not pt_a or not pt_b:
            continue

        matching_trips = 0
        matching_miles = 0.0

        for d in drives:
            # If route specifies an individual vehicle, enforce match
            if route_car_id and d.get("car_id") != route_car_id:
                continue

            s_lat = float(d["start_lat"]) if d["start_lat"] is not None else None
            s_lon = float(d["start_lon"]) if d["start_lon"] is not None else None
            e_lat = float(d["end_lat"]) if d["end_lat"] is not None else None
            e_lon = float(d["end_lon"]) if d["end_lon"] is not None else None

            forward_match = (
                matches_location_point(pt_a, s_lat, s_lon, d["start_name"], d["start_city"], effective_geofences, addr_cache) and
                matches_location_point(pt_b, e_lat, e_lon, d["end_name"], d["end_city"], effective_geofences, addr_cache)
            )
            reverse_match = (
                bidirectional and
                matches_location_point(pt_b, s_lat, s_lon, d["start_name"], d["start_city"], effective_geofences, addr_cache) and
                matches_location_point(pt_a, e_lat, e_lon, d["end_name"], d["end_city"], effective_geofences, addr_cache)
            )

            if forward_match or reverse_match:
                matching_trips += 1
                matching_miles += float(d["distance_mi"] or 0)

        deduction = matching_miles * irs_rate
        overall_trips += matching_trips
        overall_miles += matching_miles

        route_results.append({
            "label": label,
            "point_a": pt_a,
            "point_b": pt_b,
            "bidirectional": bidirectional,
            "target_car_id": route_car_id,
            "trip_count": matching_trips,
            "total_miles": round(matching_miles, 1),
            "total_km": round(matching_miles / 0.621371, 1),
            "irs_deduction": round(deduction, 2)
        })

    total_deduction = overall_miles * irs_rate

    return {
        "has_routes": len(route_results) > 0,
        "total_routes": len(route_results),
        "total_trips": overall_trips,
        "total_miles": round(overall_miles, 1),
        "total_km": round(overall_miles / 0.621371, 1),
        "total_irs_deduction": round(total_deduction, 2),
        "irs_rate": irs_rate,
        "target_car_id": commute_target_car_id,
        "target_car_name": target_car_name,
        "routes": route_results
    }


async def get_available_locations_for_work(db: Database) -> List[str]:
    """
    Returns unique addresses and geofences to populate location pickers.
    """
    query = """
        SELECT DISTINCT loc FROM (
            SELECT coalesce(name, road) as loc FROM addresses WHERE coalesce(name, road) IS NOT NULL AND coalesce(name, road) != ''
            UNION
            SELECT name as loc FROM geofences WHERE name IS NOT NULL AND name != ''
        ) t
        ORDER BY loc ASC;
    """
    rows = await db.fetch(query)
    return [r["loc"] for r in rows if r["loc"]]
