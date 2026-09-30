from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_supercharger_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None
) -> Dict[str, Any]:
    car_filter_period = "AND cp.car_id = $3" if car_id else ""
    args_period = [start_date, end_date]
    if car_id:
        args_period.append(car_id)

    # 1. Sessions during this reporting period
    query_period = f"""
        SELECT 
            cp.id,
            cp.car_id,
            c_car.name as car_name,
            cp.start_date,
            cp.charge_energy_added,
            cp.duration_min,
            coalesce(g.name, a.name, a.road, 'Supercharger') as location_name,
            coalesce(a.city, '') as city,
            coalesce(a.state, '') as state,
            a.id as address_id,
            max(ch.charger_power) as peak_kw
        FROM charging_processes cp
        JOIN cars c_car ON cp.car_id = c_car.id
        LEFT JOIN geofences g ON cp.geofence_id = g.id
        LEFT JOIN addresses a ON cp.address_id = a.id
        JOIN charges ch ON ch.charging_process_id = cp.id
        WHERE ch.fast_charger_present = true
          AND cp.start_date >= $1 AND cp.start_date < $2
          {car_filter_period}
        GROUP BY cp.id, c_car.name, g.name, a.name, a.road, a.city, a.state, a.id
        ORDER BY cp.start_date DESC;
    """
    period_sessions = await db.fetch(query_period, *args_period)

    # 2. All-time unique superchargers
    car_filter_all = "WHERE cp.car_id = $1" if car_id else ""
    args_all = [car_id] if car_id else []

    query_all = f"""
        SELECT DISTINCT 
            coalesce(g.name, a.name, a.road, 'Supercharger') as location_name,
            coalesce(a.city, '') as city,
            coalesce(a.state, '') as state,
            min(cp.start_date) as first_visited
        FROM charging_processes cp
        LEFT JOIN geofences g ON cp.geofence_id = g.id
        LEFT JOIN addresses a ON cp.address_id = a.id
        JOIN charges ch ON ch.charging_process_id = cp.id
        WHERE ch.fast_charger_present = true
        GROUP BY 1, 2, 3;
    """
    all_time_stations = await db.fetch(query_all)
    all_time_count = len(all_time_stations)

    # 3. Identify new superchargers visited during this period
    new_superchargers = []
    recent_visits = []

    for s in period_sessions:
        loc_name = s["location_name"]
        city = s["city"]
        state = s["state"]
        s_date = s["start_date"]

        # Check if first visited date matches this period
        is_first_time = False
        for st in all_time_stations:
            if st["location_name"] == loc_name and st["city"] == city:
                if st["first_visited"] >= start_date:
                    is_first_time = True
                break

        visit_data = {
            "car_name": s["car_name"],
            "location_name": loc_name,
            "city": city,
            "state": state,
            "date": s_date.strftime("%b %d, %Y"),
            "energy_added_kwh": round(float(s["charge_energy_added"] or 0), 1),
            "peak_kw": int(s["peak_kw"] or 0),
            "duration_min": int(s["duration_min"] or 0),
            "is_new": is_first_time
        }
        recent_visits.append(visit_data)
        if is_first_time and not any(n["location_name"] == loc_name and n["city"] == city for n in new_superchargers):
            new_superchargers.append(visit_data)

    return {
        "period_session_count": len(period_sessions),
        "all_time_unique_count": all_time_count,
        "new_superchargers_count": len(new_superchargers),
        "new_superchargers": new_superchargers,
        "recent_visits": recent_visits
    }
