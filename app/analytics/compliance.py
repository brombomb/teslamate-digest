from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_charge_compliance_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyzes battery pack state-of-charge (SoC) dwell time to evaluate pack stress:
    - Time spent >80% (high voltage/cell oxidation stress)
    - Time spent 20-80% (optimal preservation zone)
    - Time spent <20% (low voltage/deep discharge stress)
    """
    car_filter = "AND car_id = $3" if car_id else ""
    args = [start_date, end_date]
    if car_id:
        args.append(car_id)

    query = f"""
        WITH pos AS (
            SELECT 
                car_id,
                battery_level,
                date,
                lead(date) OVER (PARTITION BY car_id ORDER BY date) AS next_date
            FROM positions
            WHERE date >= $1 AND date < $2
              AND battery_level IS NOT NULL
              {car_filter}
        )
        SELECT 
            car_id,
            coalesce(sum(case when battery_level > 80 then extract(epoch from (next_date - date))/3600.0 else 0 end), 0) as hours_above_80,
            coalesce(sum(case when battery_level between 20 and 80 then extract(epoch from (next_date - date))/3600.0 else 0 end), 0) as hours_optimal,
            coalesce(sum(case when battery_level < 20 then extract(epoch from (next_date - date))/3600.0 else 0 end), 0) as hours_below_20,
            coalesce(sum(extract(epoch from (next_date - date))/3600.0), 0) as total_hours
        FROM pos
        WHERE next_date IS NOT NULL
        GROUP BY car_id;
    """
    rows = await db.fetch(query, *args)

    cars = await db.get_cars()
    car_names = {c["id"]: f"{c['name']} (Model {c['model']})" for c in cars}

    total_hours_above_80 = 0.0
    total_hours_optimal = 0.0
    total_hours_below_20 = 0.0
    total_hours = 0.0
    cars_breakdown: List[Dict[str, Any]] = []

    for r in rows:
        cid = r["car_id"]
        h_above = float(r["hours_above_80"])
        h_opt = float(r["hours_optimal"])
        h_below = float(r["hours_below_20"])
        h_tot = float(r["total_hours"])

        total_hours_above_80 += h_above
        total_hours_optimal += h_opt
        total_hours_below_20 += h_below
        total_hours += h_tot

        pct_above = round((h_above / h_tot * 100.0), 1) if h_tot > 0 else 0.0
        pct_opt = round((h_opt / h_tot * 100.0), 1) if h_tot > 0 else 100.0
        pct_below = round((h_below / h_tot * 100.0), 1) if h_tot > 0 else 0.0

        compliance_score = max(0.0, min(100.0, round(100.0 - (pct_above + pct_below * 1.5), 1)))

        cars_breakdown.append({
            "car_id": cid,
            "name": car_names.get(cid, f"Vehicle #{cid}"),
            "hours_above_80": round(h_above, 1),
            "hours_optimal": round(h_opt, 1),
            "hours_below_20": round(h_below, 1),
            "total_hours": round(h_tot, 1),
            "pct_above_80": pct_above,
            "pct_optimal": pct_opt,
            "pct_below_20": pct_below,
            "compliance_score": compliance_score
        })

    overall_pct_above = round((total_hours_above_80 / total_hours * 100.0), 1) if total_hours > 0 else 0.0
    overall_pct_opt = round((total_hours_optimal / total_hours * 100.0), 1) if total_hours > 0 else 100.0
    overall_pct_below = round((total_hours_below_20 / total_hours * 100.0), 1) if total_hours > 0 else 0.0
    overall_score = max(0.0, min(100.0, round(100.0 - (overall_pct_above + overall_pct_below * 1.5), 1)))

    if overall_score >= 95.0:
        compliance_rating = "Excellent"
        stress_level = "Very Low"
    elif overall_score >= 85.0:
        compliance_rating = "Good"
        stress_level = "Low"
    elif overall_score >= 70.0:
        compliance_rating = "Moderate"
        stress_level = "Moderate"
    else:
        compliance_rating = "Attention Needed"
        stress_level = "High"

    return {
        "hours_above_80": round(total_hours_above_80, 1),
        "hours_optimal": round(total_hours_optimal, 1),
        "hours_below_20": round(total_hours_below_20, 1),
        "total_hours": round(total_hours, 1),
        "pct_above_80": overall_pct_above,
        "pct_optimal": overall_pct_opt,
        "pct_below_20": overall_pct_below,
        "compliance_score": overall_score,
        "compliance_rating": compliance_rating,
        "stress_level": stress_level,
        "cars_breakdown": cars_breakdown
    }
