from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database
from app.config import load_maintenance_log


async def get_health_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    rotation_interval_mi: int = 6250,
    pressure_unit: str = "psi",
    length_unit: str = "mi"
) -> Dict[str, Any]:
    car_filter = "WHERE id = $1" if car_id else ""
    args = [car_id] if car_id else []

    cars = await db.fetch(f"SELECT id, name, model FROM cars {car_filter} ORDER BY id ASC;", *args)
    maintenance_log = load_maintenance_log()

    car_reports = []
    for c in cars:
        cid = c["id"]
        c_name = c["name"]
        c_model = c["model"]

        # 1. Latest TPMS & Odometer
        tpms_query = """
            SELECT 
                date,
                tpms_pressure_fl,
                tpms_pressure_fr,
                tpms_pressure_rl,
                tpms_pressure_rr,
                coalesce(odometer, 0) as odometer_km,
                coalesce(odometer, 0) * 0.621371 as odometer_mi
            FROM positions
            WHERE car_id = $1 AND tpms_pressure_fl IS NOT NULL
            ORDER BY id DESC
            LIMIT 1;
        """
        latest_pos = await db.fetchrow(tpms_query, cid)

        tpms_data = None
        current_odometer = 0.0
        odometer_mi = 0.0
        odometer_km = 0.0

        if latest_pos:
            odometer_km = round(float(latest_pos["odometer_km"] or 0), 1)
            odometer_mi = round(float(latest_pos["odometer_mi"] or 0), 1)
            current_odometer = odometer_mi if length_unit == "mi" else odometer_km

            # Convert bar to PSI
            fl_bar = float(latest_pos["tpms_pressure_fl"] or 0)
            fr_bar = float(latest_pos["tpms_pressure_fr"] or 0)
            rl_bar = float(latest_pos["tpms_pressure_rl"] or 0)
            rr_bar = float(latest_pos["tpms_pressure_rr"] or 0)

            fl_psi = round(fl_bar * 14.5038, 1)
            fr_psi = round(fr_bar * 14.5038, 1)
            rl_psi = round(rl_bar * 14.5038, 1)
            rr_psi = round(rr_bar * 14.5038, 1)

            def get_tpms_status(psi: float):
                if 40.5 <= psi <= 44.5:
                    return {"status": "Optimal", "color": "#10b981", "desc": "Optimal cold range"}
                elif 38.0 <= psi < 40.5:
                    return {"status": "Slightly Low", "color": "#f59e0b", "desc": "Slightly low"}
                elif 44.5 < psi <= 46.5:
                    return {"status": "Elevated", "color": "#f59e0b", "desc": "Elevated / warm"}
                elif psi > 46.5:
                    return {"status": "High Pressure", "color": "#ef4444", "desc": "Over-inflated (>46.5 PSI)"}
                else:
                    return {"status": "Low Pressure", "color": "#ef4444", "desc": "Under-inflated (<38 PSI)"}

            all_psi = [fl_psi, fr_psi, rl_psi, rr_psi]
            max_psi = max(all_psi) if all_psi else 0.0
            min_psi = min(all_psi) if all_psi else 0.0
            imbalance_front = abs(fl_psi - fr_psi) >= 2.5
            imbalance_rear = abs(rl_psi - rr_psi) >= 2.5
            is_high = max_psi > 46.5
            is_low = min_psi < 38.0 and min_psi > 0.0
            has_alert = is_high or is_low or imbalance_front or imbalance_rear

            if is_high:
                alert_msg = f"High tire pressure ({max_psi:.1f} PSI) — Target: 42 PSI cold"
            elif is_low:
                alert_msg = f"Low tire pressure ({min_psi:.1f} PSI) — Target: 42 PSI cold"
            elif imbalance_front or imbalance_rear:
                alert_msg = "Axle pressure imbalance (≥2.5 PSI difference)"
            else:
                alert_msg = "All tires optimal (Target: 42 PSI cold)"

            front_left_val = round(fl_bar, 2) if pressure_unit == "bar" else fl_psi
            front_right_val = round(fr_bar, 2) if pressure_unit == "bar" else fr_psi
            rear_left_val = round(rl_bar, 2) if pressure_unit == "bar" else rl_psi
            rear_right_val = round(rr_bar, 2) if pressure_unit == "bar" else rr_psi

            tpms_data = {
                "front_left": front_left_val,
                "front_right": front_right_val,
                "rear_left": rear_left_val,
                "rear_right": rear_right_val,
                "unit": pressure_unit,
                "target_psi": 42.0,
                "target_bar": 2.90,
                "max_psi": max_psi,
                "min_psi": min_psi,
                "is_high": is_high,
                "is_low": is_low,
                "fl_psi": fl_psi,
                "fr_psi": fr_psi,
                "rl_psi": rl_psi,
                "rr_psi": rr_psi,
                "fl_bar": round(fl_bar, 2),
                "fr_bar": round(fr_bar, 2),
                "rl_bar": round(rl_bar, 2),
                "rr_bar": round(rr_bar, 2),
                "fl_info": get_tpms_status(fl_psi),
                "fr_info": get_tpms_status(fr_psi),
                "rl_info": get_tpms_status(rl_psi),
                "rr_info": get_tpms_status(rr_psi),
                "has_alert": has_alert,
                "alert_msg": alert_msg
            }

        # 2. Tire Rotation Tracker
        m_entry = maintenance_log.get(str(cid), {})
        last_rot_odo = float(m_entry.get("last_tire_rotation_odometer", 0))
        last_rot_date = m_entry.get("last_tire_rotation_date", "Unknown")

        effective_interval = rotation_interval_mi if length_unit == "mi" else round(rotation_interval_mi * 1.60934)

        is_uncalibrated = (last_rot_odo <= 0)
        if not is_uncalibrated and current_odometer > last_rot_odo:
            dist_since = round(current_odometer - last_rot_odo, 1)
        else:
            dist_since = 0.0

        dist_remaining = max(0.0, effective_interval - dist_since) if not is_uncalibrated else effective_interval
        # pct_used: progress of the interval driven (0% when freshly rotated, filling towards 100% when due)
        pct_used = min(100.0, round((dist_since / effective_interval) * 100.0, 1)) if (effective_interval > 0 and not is_uncalibrated) else 0.0
        life_remaining_pct = max(0.0, round(100.0 - pct_used, 1)) if not is_uncalibrated else 0.0
        due = (dist_since >= effective_interval) and not is_uncalibrated

        if is_uncalibrated:
            color = "#94a3b8"  # Neutral gray when no calibration on file
            gradient = "#94a3b8"
        elif due or pct_used >= 90.0:
            color = "#ef4444"  # Red when rotation due/overdue or >= 90%
            g_stop = round((80.0 / max(pct_used, 1.0)) * 100.0, 1)
            y_stop = round((90.0 / max(pct_used, 1.0)) * 100.0, 1)
            gradient = f"linear-gradient(90deg, #10b981 0%, #10b981 {g_stop}%, #f59e0b {g_stop}%, #f59e0b {y_stop}%, #ef4444 {y_stop}%, #ef4444 100%)"
        elif pct_used >= 80.0:
            color = "#f59e0b"  # Amber/yellow when >= 80%
            g_stop = round((80.0 / max(pct_used, 1.0)) * 100.0, 1)
            gradient = f"linear-gradient(90deg, #10b981 0%, #10b981 {g_stop}%, #f59e0b {g_stop}%, #f59e0b 100%)"
        else:
            color = "#10b981"  # Optimal green
            gradient = "#10b981"

        rotation_data = {
            "last_rotation_odometer": round(last_rot_odo),
            "last_rotation_date": last_rot_date,
            "dist_driven_since": dist_since,
            "dist_remaining": round(dist_remaining),
            "interval": effective_interval,
            "unit": length_unit,
            "miles_since_rotation": dist_since,
            "miles_driven_since": dist_since,
            "interval_mi": effective_interval,
            "miles_remaining": round(dist_remaining),
            "pct_used": pct_used,
            "pct_progress": pct_used,
            "life_remaining_pct": life_remaining_pct,
            "color": color,
            "gradient": gradient,
            "is_due": due,
            "is_uncalibrated": is_uncalibrated,
            "current_odometer": round(current_odometer),
            "status_text": "Tire Rotation Overdue!" if due else (f"{round(dist_remaining):,} {length_unit} remaining" if not is_uncalibrated else "Calibration Recommended")
        }

        # 3. Seasonal Snow Tire Swap Tracker
        active_tire_set = m_entry.get("active_tire_set", "all_season")
        last_swap_date = m_entry.get("last_tire_swap_date", "Unknown")
        current_month = end_date.month
        snow_reminder = None

        if current_month in [9, 10, 11] and active_tire_set != "winter":
            snow_reminder = {
                "show": True,
                "type": "winter_prep",
                "icon": "❄️",
                "title": "Winter Tire Swap Reminder",
                "msg": "Fall temperatures are dropping and the Colorado I-70 Traction Law is in effect (Sep 1 – May 31). Consider swapping to your snow tires!"
            }
        elif current_month in [4, 5, 6] and active_tire_set == "winter":
            snow_reminder = {
                "show": True,
                "type": "spring_swap",
                "icon": "☀️",
                "title": "Spring Tire Swap Reminder",
                "msg": "Spring temperatures are warming up. Switch back to your all-season set to preserve your soft winter rubber."
            }

        snow_tire_data = {
            "active_set": active_tire_set,
            "active_set_label": "Winter / Snow Tires" if active_tire_set == "winter" else "All-Season / Summer Tires",
            "last_swap_date": last_swap_date,
            "reminder": snow_reminder
        }

        # 4. Firmware Updates Installed in this period
        upd_query = """
            SELECT version, start_date
            FROM updates
            WHERE car_id = $1 AND start_date >= $2 AND start_date < $3
            ORDER BY start_date DESC;
        """
        updates_raw = await db.fetch(upd_query, cid, start_date, end_date)
        updates = [
            {
                "version": u["version"],
                "date": u["start_date"].strftime("%b %d, %Y")
            }
            for u in updates_raw
        ]

        car_reports.append({
            "car_id": cid,
            "car_name": c_name,
            "model": c_model,
            "odometer": current_odometer,
            "odometer_display": f"{round(current_odometer):,} {length_unit}",
            "odometer_unit": length_unit,
            "odometer_mi": odometer_mi,
            "odometer_km": odometer_km,
            "tpms": tpms_data,
            "tire_rotation": rotation_data,
            "snow_tires": snow_tire_data,
            "updates": updates
        })

    return {
        "cars": car_reports
    }
