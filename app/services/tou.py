from datetime import datetime
from typing import Dict, Any, Tuple

TARIFF_PRESETS: Dict[str, Dict[str, Any]] = {
    "xcel_colorado_tou": {
        "name": "Xcel Energy Colorado (Schedule RE-TOU)",
        "description": "Off-Peak 9 PM – 9 AM weekdays & ALL weekends. Shoulder 9 AM – 1 PM & 7 PM – 9 PM. On-Peak 1 PM – 7 PM weekdays.",
        "off_peak_kwh_cost": 0.09,
        "shoulder_kwh_cost": 0.13,
        "on_peak_kwh_cost": 0.19,
        "average_kwh_cost": 0.11,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True
    },
    "flat_rate": {
        "name": "Flat Electric Rate Plan",
        "description": "Fixed electricity rate across all hours and days.",
        "off_peak_kwh_cost": 0.11,
        "shoulder_kwh_cost": 0.11,
        "on_peak_kwh_cost": 0.11,
        "average_kwh_cost": 0.11,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True
    }
}


def determine_tou_tier(
    dt: datetime,
    off_peak_start: int = 21,
    off_peak_end: int = 9,
    peak_start: int = 13,
    peak_end: int = 19,
    weekends_are_off_peak: bool = True
) -> str:
    """
    Determines whether a timestamp falls into:
    - 'off_peak'
    - 'shoulder'
    - 'on_peak'
    """
    # Check weekend (Saturday = 5, Sunday = 6)
    if weekends_are_off_peak and dt.weekday() >= 5:
        return "off_peak"

    hour = dt.hour

    # Off-peak overnight check (e.g. 21 to 9)
    if off_peak_start > off_peak_end:
        if hour >= off_peak_start or hour < off_peak_end:
            return "off_peak"
    else:
        if off_peak_start <= hour < off_peak_end:
            return "off_peak"

    # Peak window check (e.g. 13 to 19)
    if peak_start <= hour < peak_end:
        return "on_peak"

    # Everything else on weekdays is Shoulder / Mid-Peak (e.g. 9-13 and 19-21)
    return "shoulder"
