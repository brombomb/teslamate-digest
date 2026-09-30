from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database
from app.config import RatesSettings


async def get_charging_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    rates: Optional[RatesSettings] = None,
    miles_driven: float = 0.0
) -> Dict[str, Any]:
    if rates is None:
        rates = RatesSettings()

    car_filter = "AND cp.car_id = $3" if car_id else ""
    args = [start_date, end_date]
    if car_id:
        args.append(car_id)

    query = f"""
        SELECT 
            cp.id,
            cp.car_id,
            cp.start_date,
            cp.end_date,
            coalesce(cp.charge_energy_added, 0) as energy_added,
            coalesce(cp.charge_energy_used, cp.charge_energy_added, 0) as energy_used,
            coalesce(cp.duration_min, 0) as duration_min,
            cp.cost as direct_cost,
            coalesce(g.name, a.name, a.road, 'Unknown') as location_name,
            a.city,
            bool_or(coalesce(c.fast_charger_present, false)) as is_fast_charger,
            max(c.fast_charger_brand) as fast_charger_brand,
            max(c.charger_power) as max_power_kw
        FROM charging_processes cp
        LEFT JOIN geofences g ON cp.geofence_id = g.id
        LEFT JOIN addresses a ON cp.address_id = a.id
        LEFT JOIN charges c ON c.charging_process_id = cp.id
        WHERE cp.start_date >= $1 AND cp.start_date < $2
        {car_filter}
        GROUP BY cp.id, g.name, a.name, a.road, a.city
        ORDER BY cp.start_date ASC;
    """

    sessions = await db.fetch(query, *args)

    total_sessions = len(sessions)
    total_energy_added = 0.0
    total_energy_used = 0.0
    total_duration_min = 0

    home_kwh = 0.0
    home_spend = 0.0
    off_peak_kwh = 0.0
    on_peak_kwh = 0.0

    supercharger_kwh = 0.0
    supercharger_spend = 0.0
    supercharger_sessions = 0

    other_kwh = 0.0
    other_spend = 0.0

    # Hourly distribution for TOU chart (0 to 23)
    hourly_kwh = [0.0] * 24

    for s in sessions:
        kwh_added = float(s["energy_added"])
        kwh_used = float(s["energy_used"])
        duration = int(s["duration_min"])
        s_date: datetime = s["start_date"]
        start_hour = s_date.hour

        total_energy_added += kwh_added
        total_energy_used += kwh_used
        total_duration_min += duration

        # Add to hourly distribution
        hourly_kwh[start_hour] += kwh_used

        is_fast = s["is_fast_charger"]
        brand = (s["fast_charger_brand"] or "").lower()
        loc = (s["location_name"] or "").lower()

        is_supercharger = is_fast and ("tesla" in brand or "supercharger" in loc)

        if is_supercharger:
            supercharger_sessions += 1
            supercharger_kwh += kwh_used
            if s["direct_cost"] is not None and float(s["direct_cost"]) > 0:
                supercharger_spend += float(s["direct_cost"])
            else:
                supercharger_spend += kwh_used * rates.supercharger_fallback_cost
        elif is_fast:
            # Other DC Fast charger
            other_kwh += kwh_used
            if s["direct_cost"] is not None and float(s["direct_cost"]) > 0:
                other_spend += float(s["direct_cost"])
            else:
                other_spend += kwh_used * rates.supercharger_fallback_cost
        else:
            # AC Charging (Home vs Public)
            # Check TOU time
            is_off_peak = False
            if rates.off_peak_start_hour > rates.off_peak_end_hour:
                # Overnight e.g. 21 to 9
                is_off_peak = (start_hour >= rates.off_peak_start_hour or start_hour < rates.off_peak_end_hour)
            else:
                is_off_peak = (rates.off_peak_start_hour <= start_hour < rates.off_peak_end_hour)

            rate = rates.off_peak_kwh_cost if is_off_peak else rates.on_peak_kwh_cost
            if rates.rate_mode == "flat":
                rate = rates.average_kwh_cost

            cost = kwh_used * rate
            home_kwh += kwh_used
            home_spend += cost

            if is_off_peak:
                off_peak_kwh += kwh_used
            else:
                on_peak_kwh += kwh_used

    total_spend = home_spend + supercharger_spend + other_spend
    efficiency_pct = (total_energy_added / total_energy_used * 100.0) if total_energy_used > 0 else 0.0

    off_peak_score_pct = (off_peak_kwh / home_kwh * 100.0) if home_kwh > 0 else 100.0

    # Gas Savings calculation
    gallons_avoided = (miles_driven / rates.baseline_ice_mpg) if rates.baseline_ice_mpg > 0 else 0.0
    gas_spend_equivalent = gallons_avoided * rates.gas_price_per_gal
    net_savings = max(0.0, gas_spend_equivalent - total_spend) if miles_driven > 0 else 0.0
    co2_lbs_prevented = gallons_avoided * 19.64

    return {
        "total_sessions": total_sessions,
        "total_energy_added_kwh": round(total_energy_added, 2),
        "total_energy_used_kwh": round(total_energy_used, 2),
        "total_duration_hours": round(total_duration_min / 60.0, 1),
        "efficiency_pct": round(efficiency_pct, 1),
        "total_spend": round(total_spend, 2),
        "home_kwh": round(home_kwh, 2),
        "home_spend": round(home_spend, 2),
        "off_peak_kwh": round(off_peak_kwh, 2),
        "on_peak_kwh": round(on_peak_kwh, 2),
        "off_peak_score_pct": round(off_peak_score_pct, 1),
        "supercharger_sessions": supercharger_sessions,
        "supercharger_kwh": round(supercharger_kwh, 2),
        "supercharger_spend": round(supercharger_spend, 2),
        "other_kwh": round(other_kwh, 2),
        "other_spend": round(other_spend, 2),
        "hourly_kwh": [round(h, 2) for h in hourly_kwh],
        "gas_savings": {
            "gallons_avoided": round(gallons_avoided, 1),
            "gas_spend_equivalent": round(gas_spend_equivalent, 2),
            "net_savings": round(net_savings, 2),
            "co2_lbs_prevented": round(co2_lbs_prevented, 1),
        }
    }
