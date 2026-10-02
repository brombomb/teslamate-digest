from typing import Dict, Any, Optional
from app.db import Database
from app.config import AppConfig


async def query_teslamate_units(db: Database) -> Dict[str, str]:
    """Queries unit preferences configured directly inside TeslaMate PostgreSQL database."""
    detected = {
        "unit_of_length": "mi",
        "unit_of_temperature": "F",
        "unit_of_pressure": "psi"
    }
    try:
        row = await db.fetchrow("SELECT unit_of_length, unit_of_temperature, unit_of_pressure FROM settings LIMIT 1;")
        if row:
            if row.get("unit_of_length"):
                detected["unit_of_length"] = str(row["unit_of_length"]).strip().lower()
            if row.get("unit_of_temperature"):
                detected["unit_of_temperature"] = str(row["unit_of_temperature"]).strip().upper()
            if row.get("unit_of_pressure"):
                detected["unit_of_pressure"] = str(row["unit_of_pressure"]).strip().lower()
    except Exception as e:
        print(f"[Units] Error querying TeslaMate settings units: {e}")
    return detected


async def get_effective_units(db: Optional[Database], config: AppConfig) -> Dict[str, Any]:
    """
    Resolves the active units (length, temp, pressure, speed, elevation, consumption)
    based on application configuration and TeslaMate DB mirroring.
    """
    unit_system = getattr(config.units, "unit_system", "auto") or "auto"
    currency = getattr(config.units, "currency", "$") or "$"

    db_units = {"unit_of_length": "mi", "unit_of_temperature": "F", "unit_of_pressure": "psi"}
    if db:
        try:
            db_units = await query_teslamate_units(db)
        except Exception:
            pass

    if unit_system == "imperial":
        length = "mi"
        temp = "F"
        pressure = "psi"
    elif unit_system == "metric":
        length = "km"
        temp = "C"
        pressure = "bar"
    elif unit_system == "custom":
        length = getattr(config.units, "length", "mi") or "mi"
        temp = getattr(config.units, "temp", "F") or "F"
        pressure = getattr(config.units, "pressure", "psi") or "psi"
    else:  # auto - mirror TeslaMate DB settings
        length = db_units.get("unit_of_length") or getattr(config.units, "length", "mi") or "mi"
        temp = db_units.get("unit_of_temperature") or getattr(config.units, "temp", "F") or "F"
        pressure = db_units.get("unit_of_pressure") or getattr(config.units, "pressure", "psi") or "psi"

    # Normalize values
    length = "km" if length.lower() == "km" else "mi"
    temp = "C" if temp.upper() == "C" else "F"
    pressure = "bar" if pressure.lower() == "bar" else "psi"

    speed = "mph" if length == "mi" else "km/h"
    elevation = "ft" if length == "mi" else "m"
    consumption = "Wh/mi" if length == "mi" else "Wh/km"

    return {
        "unit_system": unit_system,
        "length": length,
        "distance": length,
        "speed": speed,
        "pressure": pressure,
        "temp": temp,
        "temp_display": f"°{temp}",
        "elevation": elevation,
        "consumption": consumption,
        "currency": currency,
        "is_imperial": (length == "mi"),
        "is_metric": (length == "km"),
        "db_length": db_units.get("unit_of_length", "mi"),
        "db_temp": db_units.get("unit_of_temperature", "F"),
        "db_pressure": db_units.get("unit_of_pressure", "psi"),
    }


def convert_distance(km_val: float, length_unit: str = "mi") -> float:
    if length_unit == "mi":
        return round(km_val * 0.621371, 1)
    return round(km_val, 1)


def convert_speed(kmh_val: float, speed_unit: str = "mph") -> float:
    if speed_unit == "mph":
        return round(kmh_val * 0.621371, 1)
    return round(kmh_val, 1)


def convert_elevation(m_val: float, elevation_unit: str = "ft") -> float:
    if elevation_unit == "ft":
        return round(m_val * 3.28084)
    return round(m_val)


def convert_pressure(bar_val: float, pressure_unit: str = "psi") -> float:
    if pressure_unit == "psi":
        return round(bar_val * 14.5038, 1)
    return round(bar_val, 1)


def convert_temperature(c_val: float, temp_unit: str = "F") -> float:
    if temp_unit == "F":
        return round(c_val * 9.0 / 5.0 + 32.0, 1)
    return round(c_val, 1)
