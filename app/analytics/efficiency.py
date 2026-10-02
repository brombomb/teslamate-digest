from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_driving_efficiency_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Computes net driving efficiency, Wh/mi consumption, and rated vs. actual efficiency.
    """
    car_filter = "AND d.car_id = $3" if car_id else ""
    args = [start_date, end_date]
    if car_id:
        args.append(car_id)

    query = f"""
        SELECT 
            c.id as car_id,
            c.name as car_name,
            c.model as car_model,
            c.efficiency as rated_kwh_per_km,
            count(d.id) as drives_count,
            coalesce(sum(d.distance), 0) as total_km,
            coalesce(sum(d.start_rated_range_km - d.end_rated_range_km), 0) as rated_km_consumed,
            coalesce(sum((d.start_rated_range_km - d.end_rated_range_km) * c.efficiency), 0) as net_energy_kwh
        FROM drives d
        JOIN cars c ON d.car_id = c.id
        WHERE d.start_date >= $1 AND d.start_date < $2
          AND d.distance IS NOT NULL AND d.distance > 0
          AND d.start_rated_range_km IS NOT NULL 
          AND d.end_rated_range_km IS NOT NULL
          AND d.start_rated_range_km >= d.end_rated_range_km
          {car_filter}
        GROUP BY c.id, c.name, c.model, c.efficiency
        ORDER BY c.id;
    """
    rows = await db.fetch(query, *args)

    total_km = 0.0
    total_rated_km = 0.0
    total_energy_kwh = 0.0
    total_drives = 0
    cars_breakdown: List[Dict[str, Any]] = []

    for r in rows:
        d_km = float(r["total_km"])
        r_km = float(r["rated_km_consumed"])
        e_kwh = float(r["net_energy_kwh"])
        cnt = int(r["drives_count"])

        d_mi = d_km * 0.621371
        r_mi = r_km * 0.621371
        wh_mi = round((e_kwh * 1000.0) / d_mi) if d_mi > 0 else 0
        wh_km = round((e_kwh * 1000.0) / d_km) if d_km > 0 else 0
        eff_pct = round((d_km / r_km) * 100.0, 1) if r_km > 0 else 100.0

        total_km += d_km
        total_rated_km += r_km
        total_energy_kwh += e_kwh
        total_drives += cnt

        cars_breakdown.append({
            "car_id": r["car_id"],
            "name": r["car_name"],
            "model": r["car_model"],
            "drives_count": cnt,
            "actual_miles": round(d_mi, 1),
            "actual_km": round(d_km, 1),
            "rated_miles_consumed": round(r_mi, 1),
            "rated_km_consumed": round(r_km, 1),
            "net_energy_kwh": round(e_kwh, 1),
            "wh_per_mile": wh_mi,
            "wh_per_km": wh_km,
            "efficiency_pct": eff_pct
        })

    total_miles = total_km * 0.621371
    total_rated_miles = total_rated_km * 0.621371
    avg_wh_per_mile = round((total_energy_kwh * 1000.0) / total_miles) if total_miles > 0 else 0
    avg_wh_per_km = round((total_energy_kwh * 1000.0) / total_km) if total_km > 0 else 0
    overall_eff_pct = round((total_km / total_rated_km) * 100.0, 1) if total_rated_km > 0 else 100.0

    # Rating label
    if overall_eff_pct >= 95.0:
        grade = "Excellent"
        grade_desc = "Near-rated efficiency; low aerodynamic drag or optimal ambient conditions."
    elif overall_eff_pct >= 85.0:
        grade = "Good"
        grade_desc = "Typical real-world highway and seasonal climate performance."
    elif overall_eff_pct >= 75.0:
        grade = "Moderate"
        grade_desc = "Higher consumption from mountain ascents, cold temperatures, or highway speeds."
    else:
        grade = "Heavy"
        grade_desc = "Heavy consumption period (significant heating/cabin conditioning or high-speed driving)."

    return {
        "total_drives": total_drives,
        "total_miles": round(total_miles, 1),
        "total_km": round(total_km, 1),
        "rated_miles_consumed": round(total_rated_miles, 1),
        "net_energy_kwh": round(total_energy_kwh, 1),
        "avg_wh_per_mile": avg_wh_per_mile,
        "avg_wh_per_km": avg_wh_per_km,
        "efficiency_pct": overall_eff_pct,
        "grade": grade,
        "grade_desc": grade_desc,
        "cars_breakdown": cars_breakdown
    }
