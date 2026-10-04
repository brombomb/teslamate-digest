from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_battery_health_analytics(
    db: Database,
    end_date: datetime,
    car_id: Optional[int] = None,
    length_unit: str = "mi"
) -> Dict[str, Any]:
    if car_id:
        car_filter = "WHERE cp.car_id = $1 AND"
        date_param = "$2"
        args = [car_id, end_date]
    else:
        car_filter = "WHERE"
        date_param = "$1"
        args = [end_date]

    # Get degradation timeseries data
    query = f"""
        SELECT 
            cp.car_id,
            c.name as car_name,
            c.model,
            cp.start_date,
            round((cp.end_rated_range_km / cp.end_battery_level * 100 * 0.621371)::numeric, 1) as rated_100_range_mi,
            p.odometer * 0.621371 as odometer_mi
        FROM charging_processes cp
        JOIN cars c ON cp.car_id = c.id
        LEFT JOIN positions p ON cp.position_id = p.id
        {car_filter} cp.duration_min > 10 
          AND cp.end_battery_level >= 50
          AND cp.start_date <= {date_param}
        ORDER BY cp.start_date ASC;
    """
    records = await db.fetch(query, *args)

    # Group by car
    cars_data: Dict[int, Dict[str, Any]] = {}
    for r in records:
        cid = r["car_id"]
        if cid not in cars_data:
            cars_data[cid] = {
                "car_id": cid,
                "car_name": r["car_name"],
                "model": r["model"],
                "data_points": []
            }
        cars_data[cid]["data_points"].append({
            "date": r["start_date"],
            "range_mi": float(r["rated_100_range_mi"]),
            "odometer_mi": float(r["odometer_mi"] or 0)
        })

    one_month_ago = end_date - timedelta(days=30)
    two_months_ago = end_date - timedelta(days=60)

    fleet_results = []
    for cid, car_info in cars_data.items():
        points = car_info["data_points"]
        if not points:
            continue

        all_time_max = max(p["range_mi"] for p in points)
        latest_point = points[-1]
        latest_odometer = latest_point["odometer_mi"]

        # Points in current 30 days
        current_points = [p["range_mi"] for p in points if p["date"] >= one_month_ago]
        prev_points = [p["range_mi"] for p in points if two_months_ago <= p["date"] < one_month_ago]

        current_avg = sum(current_points) / len(current_points) if current_points else latest_point["range_mi"]
        prev_avg = sum(prev_points) / len(prev_points) if prev_points else current_avg

        degradation_pct = ((all_time_max - current_avg) / all_time_max * 100.0) if all_time_max > 0 else 0.0
        degradation_pct = max(0.0, degradation_pct)
        capacity_retained_pct = 100.0 - degradation_pct

        if capacity_retained_pct >= 95.0:
            health_grade = "Excellent"
            health_color = "#10b981"  # green
        elif capacity_retained_pct >= 90.0:
            health_grade = "Good"
            health_color = "#3b82f6"  # blue
        elif capacity_retained_pct >= 85.0:
            health_grade = "Fair"
            health_color = "#f59e0b"  # amber
        else:
            health_grade = "Service Recommended"
            health_color = "#ef4444"  # red

        month_over_month_delta = current_avg - prev_avg

        # Monthly timeseries for sparkline/chart
        # Group into monthly averages
        monthly_trend = {}
        for p in points:
            m_key = p["date"].strftime("%Y-%m")
            if m_key not in monthly_trend:
                monthly_trend[m_key] = []
            monthly_trend[m_key].append(p["range_mi"])

        trend_series = [
            {
                "month": m,
                "avg_range_mi": round(sum(vals) / len(vals), 1),
                "avg_range_km": round((sum(vals) / len(vals)) / 0.621371, 1),
                "avg_range": round(sum(vals) / len(vals), 1) if length_unit == "mi" else round((sum(vals) / len(vals)) / 0.621371, 1)
            }
            for m, vals in sorted(monthly_trend.items())
        ]

        fleet_results.append({
            "car_id": cid,
            "car_name": car_info["car_name"],
            "model": car_info["model"],
            "unit": length_unit,
            "current_estimated_range": round(current_avg, 1) if length_unit == "mi" else round(current_avg / 0.621371, 1),
            "current_estimated_range_mi": round(current_avg, 1),
            "current_estimated_range_km": round(current_avg / 0.621371, 1),
            "prev_estimated_range_mi": round(prev_avg, 1),
            "prev_estimated_range_km": round(prev_avg / 0.621371, 1),
            "month_over_month_delta_mi": round(month_over_month_delta, 1),
            "month_over_month_delta_km": round(month_over_month_delta / 0.621371, 1),
            "factory_baseline_range": round(all_time_max, 1) if length_unit == "mi" else round(all_time_max / 0.621371, 1),
            "factory_baseline_range_mi": round(all_time_max, 1),
            "factory_baseline_range_km": round(all_time_max / 0.621371, 1),
            "degradation_pct": round(degradation_pct, 1),
            "capacity_retained_pct": round(capacity_retained_pct, 1),
            "health_grade": health_grade,
            "health_color": health_color,
            "latest_odometer": round(latest_odometer) if length_unit == "mi" else round(latest_odometer / 0.621371),
            "latest_odometer_mi": round(latest_odometer),
            "latest_odometer_km": round(latest_odometer / 0.621371),
            "trend_series": trend_series[-6:]  # Last 6 months
        })

    return {
        "cars": fleet_results,
        "fleet_avg_capacity_retained_pct": round(
            sum(c["capacity_retained_pct"] for c in fleet_results) / len(fleet_results), 1
        ) if fleet_results else 100.0
    }
