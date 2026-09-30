from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database


async def get_vampire_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    kwh_cost: float = 0.11
) -> Dict[str, Any]:
    car_filter = "AND car_id = $3" if car_id else ""
    args = [start_date, end_date]
    if car_id:
        args.append(car_id)

    query = f"""
        SELECT 
            state,
            sum(
                extract(epoch from (
                    least(coalesce(end_date, now()), $2) - greatest(start_date, $1)
                ))
            ) as duration_sec
        FROM states
        WHERE start_date < $2 AND coalesce(end_date, now()) > $1
          {car_filter}
        GROUP BY state;
    """
    rows = await db.fetch(query, *args)

    hours_by_state = {}
    for r in rows:
        st = r["state"]
        sec = float(r["duration_sec"] or 0)
        hours_by_state[st] = round(sec / 3600.0, 1)

    asleep_hours = hours_by_state.get("asleep", 0.0)
    online_hours = hours_by_state.get("online", 0.0)
    suspended_hours = hours_by_state.get("suspended", 0.0)

    # Idle parked hours = asleep + online + suspended
    parked_hours = asleep_hours + online_hours + suspended_hours

    # Sleep efficiency
    sleep_efficiency_pct = (asleep_hours / parked_hours * 100.0) if parked_hours > 0 else 100.0

    # Standby drain estimate:
    # Asleep: ~0.015 kW (15W)
    # Online/Sentry: ~0.25 kW (250W)
    # Suspended: ~0.05 kW (50W)
    estimated_drain_kwh = (asleep_hours * 0.015) + (online_hours * 0.25) + (suspended_hours * 0.05)
    estimated_drain_cost = estimated_drain_kwh * kwh_cost

    return {
        "parked_hours": round(parked_hours, 1),
        "total_idle_hours": round(parked_hours, 1),
        "asleep_hours": round(asleep_hours, 1),
        "online_hours": round(online_hours, 1),
        "suspended_hours": round(suspended_hours, 1),
        "sleep_efficiency_pct": round(sleep_efficiency_pct, 1),
        "estimated_drain_kwh": round(estimated_drain_kwh, 1),
        "estimated_loss_kwh": round(estimated_drain_kwh, 1),
        "estimated_drain_cost": round(estimated_drain_cost, 2),
        "estimated_cost": round(estimated_drain_cost, 2)
    }
