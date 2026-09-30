from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database
from app.config import load_maintenance_log


async def get_health_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    rotation_interval_mi: int = 6250
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
                coalesce(odometer, 0) * 0.621371 as odometer_mi
            FROM positions
            WHERE car_id = $1 AND tpms_pressure_fl IS NOT NULL
            ORDER BY date DESC
            LIMIT 1;
        """
        latest_pos = await db.fetchrow(tpms_query, cid)

        tpms_data = None
        current_odometer = 0.0

        if latest_pos:
            current_odometer = round(float(latest_pos["odometer_mi"]), 1)
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
                if 40.0 <= psi <= 44.5:
                    return {"status": "Good", "color": "#10b981"}
                elif 38.0 <= psi < 40.0 or 44.5 < psi <= 47.0:
                    return {"status": "Acceptable", "color": "#f59e0b"}
                else:
                    return {"status": "Warning", "color": "#ef4444"}

            imbalance_front = abs(fl_psi - fr_psi) >= 2.0
            imbalance_rear = abs(rl_psi - rr_psi) >= 2.0
            has_alert = fl_psi < 38.0 or fr_psi < 38.0 or rl_psi < 38.0 or rr_psi < 38.0 or imbalance_front or imbalance_rear

            tpms_data = {
                "fl_psi": fl_psi,
                "fr_psi": fr_psi,
                "rl_psi": rl_psi,
                "rr_psi": rr_psi,
                "fl_bar": round(fl_bar, 1),
                "fr_bar": round(fr_bar, 1),
                "rl_bar": round(rl_bar, 1),
                "rr_bar": round(rr_bar, 1),
                "fl_info": get_tpms_status(fl_psi),
                "fr_info": get_tpms_status(fr_psi),
                "rl_info": get_tpms_status(rl_psi),
                "rr_info": get_tpms_status(rr_psi),
                "has_alert": has_alert,
                "alert_msg": "Tire pressure low or imbalanced!" if has_alert else "All tires optimal"
            }

        # 2. Tire Rotation Tracker
        m_entry = maintenance_log.get(str(cid), {})
        last_rot_odo = float(m_entry.get("last_tire_rotation_odometer", 0))
        last_rot_date = m_entry.get("last_tire_rotation_date", "Unknown")

        if last_rot_odo > 0 and current_odometer > last_rot_odo:
            miles_since = round(current_odometer - last_rot_odo, 1)
        else:
            miles_since = 0.0

        miles_remaining = max(0.0, rotation_interval_mi - miles_since)
        pct_used = min(100.0, round((miles_since / rotation_interval_mi) * 100.0, 1)) if rotation_interval_mi > 0 else 0.0
        due = miles_since >= rotation_interval_mi

        rotation_data = {
            "last_rotation_odometer": round(last_rot_odo),
            "last_rotation_date": last_rot_date,
            "miles_since_rotation": miles_since,
            "miles_remaining": round(miles_remaining),
            "pct_used": pct_used,
            "is_due": due,
            "status_text": "Tire Rotation Overdue!" if due else f"{round(miles_remaining):,} mi remaining"
        }

        # 3. Firmware Updates Installed in this period
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
            "odometer_mi": current_odometer,
            "tpms": tpms_data,
            "tire_rotation": rotation_data,
            "updates": updates
        })

    return {
        "cars": car_reports
    }
