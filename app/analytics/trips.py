from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_trip_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None
) -> Dict[str, Any]:
    car_filter = "AND d.car_id = $3" if car_id else ""
    args = [start_date, end_date]
    if car_id:
        args.append(car_id)

    # 1. Overall stats
    query_stats = f"""
        SELECT 
            count(d.id) as drives_count,
            coalesce(sum(d.distance), 0) as total_km,
            coalesce(sum(d.duration_min), 0) as total_duration_min,
            coalesce(max(d.speed_max), 0) as top_speed_kmh,
            coalesce(sum(d.ascent), 0) as total_ascent_m,
            coalesce(sum(d.descent), 0) as total_descent_m
        FROM drives d
        WHERE d.start_date >= $1 AND d.start_date < $2
        {car_filter};
    """
    stats = await db.fetchrow(query_stats, *args)

    drives_count = int(stats["drives_count"])
    total_km = float(stats["total_km"])
    total_miles = total_km * 0.621371
    duration_min = int(stats["total_duration_min"])
    top_speed_kmh = int(stats["top_speed_kmh"])
    top_speed_mph = top_speed_kmh * 0.621371

    ascent_m = float(stats["total_ascent_m"])
    descent_m = float(stats["total_descent_m"])
    ascent_ft = ascent_m * 3.28084
    descent_ft = descent_m * 3.28084

    # Estimated regen recapture on mountain descent (~4.5 kWh per 1000m descent for EV mass ~2200kg)
    regen_kwh_recaptured = (descent_m / 1000.0) * 4.5

    # 2. Longest Single Drive
    query_longest = f"""
        SELECT 
            d.id,
            d.start_date,
            d.distance * 0.621371 as distance_mi,
            d.duration_min,
            d.speed_max * 0.621371 as speed_max_mph,
            d.ascent * 3.28084 as ascent_ft,
            d.descent * 3.28084 as descent_ft,
            coalesce(g_start.name, a_start.name, a_start.road, 'Starting point') as start_location,
            a_start.city as start_city,
            coalesce(g_end.name, a_end.name, a_end.road, 'Destination') as end_location,
            a_end.city as end_city
        FROM drives d
        LEFT JOIN geofences g_start ON d.start_geofence_id = g_start.id
        LEFT JOIN addresses a_start ON d.start_address_id = a_start.id
        LEFT JOIN geofences g_end ON d.end_geofence_id = g_end.id
        LEFT JOIN addresses a_end ON d.end_address_id = a_end.id
        WHERE d.start_date >= $1 AND d.start_date < $2
          AND d.distance IS NOT NULL AND d.distance > 0
        {car_filter}
        ORDER BY d.distance DESC NULLS LAST
        LIMIT 1;
    """
    longest = await db.fetchrow(query_longest, *args)
    longest_drive = None
    if longest and longest["distance_mi"] is not None:
        longest_drive = {
            "distance_mi": round(float(longest["distance_mi"] or 0), 1),
            "duration_min": int(longest["duration_min"] or 0),
            "start_location": f"{longest['start_location']}" + (f", {longest['start_city']}" if longest['start_city'] else ""),
            "end_location": f"{longest['end_location']}" + (f", {longest['end_city']}" if longest['end_city'] else ""),
            "ascent_ft": round(float(longest["ascent_ft"] or 0)),
            "descent_ft": round(float(longest["descent_ft"] or 0)),
            "date": longest["start_date"].strftime("%b %d, %Y")
        }

    # 3. Top Visited Destinations
    query_top_places = f"""
        SELECT 
            coalesce(g.name, a.name, a.road, 'Unknown') as location_name,
            coalesce(a.city, '') as city,
            count(d.id) as visit_count
        FROM drives d
        LEFT JOIN geofences g ON d.end_geofence_id = g.id
        LEFT JOIN addresses a ON d.end_address_id = a.id
        WHERE d.start_date >= $1 AND d.start_date < $2
        {car_filter}
        GROUP BY 1, 2
        ORDER BY visit_count DESC
        LIMIT 5;
    """
    top_places_raw = await db.fetch(query_top_places, *args)
    top_places = [
        {
            "name": p["location_name"],
            "city": p["city"],
            "visits": int(p["visit_count"])
        }
        for p in top_places_raw if p["location_name"] != "Unknown"
    ]

    return {
        "drives_count": drives_count,
        "total_miles": round(total_miles, 1),
        "total_km": round(total_km, 1),
        "total_duration_hours": round(duration_min / 60.0, 1),
        "avg_trip_miles": round(total_miles / drives_count, 1) if drives_count > 0 else 0.0,
        "top_speed_mph": round(top_speed_mph, 1),
        "elevation": {
            "ascent_ft": round(ascent_ft),
            "descent_ft": round(descent_ft),
            "ascent_m": round(ascent_m),
            "descent_m": round(descent_m),
            "regen_kwh_recaptured": round(regen_kwh_recaptured, 1)
        },
        "longest_drive": longest_drive,
        "top_places": top_places
    }
