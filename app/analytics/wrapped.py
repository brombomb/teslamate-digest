from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database
from app.config import RatesSettings
from app.analytics.charging import get_charging_analytics
from app.analytics.trips import get_trip_analytics
from app.analytics.superchargers import get_supercharger_analytics
from app.analytics.battery import get_battery_health_analytics


async def get_year_in_review_analytics(
    db: Database,
    year: int,
    car_id: Optional[int] = None,
    rates: Optional[RatesSettings] = None,
    excluded_locations: Optional[List[str]] = None
) -> Dict[str, Any]:
    if rates is None:
        rates = RatesSettings()

    start_date = datetime(year, 1, 1, 0, 0, 0)
    end_date = datetime(year, 12, 31, 23, 59, 59)

    trips = await get_trip_analytics(db, start_date, end_date, car_id, excluded_locations)
    charging = await get_charging_analytics(db, start_date, end_date, car_id, rates, trips["total_miles"])
    superchargers = await get_supercharger_analytics(db, start_date, end_date, car_id)
    battery = await get_battery_health_analytics(db, end_date, car_id)

    total_miles = trips["total_miles"]
    earth_circumnavigations = round(total_miles / 24901.0, 2)
    ascent_ft = trips["elevation"]["ascent_ft"]
    everest_equivalents = round(ascent_ft / 29032.0, 1)

    # Award Persona Badges
    badges = []
    if charging["off_peak_score_pct"] >= 80.0:
        badges.append({
            "title": "Night Owl Charger",
            "icon": "🦉",
            "desc": f"{charging['off_peak_score_pct']}% of home charging was done overnight during off-peak hours."
        })

    if ascent_ft >= 30000:
        badges.append({
            "title": "Colorado Peak Bagger",
            "icon": "🏔️",
            "desc": f"Climbed {ascent_ft:,} vertical feet in the mountains ({everest_equivalents}x Mt. Everest!)."
        })

    if trips["longest_drive"] and trips["longest_drive"]["distance_mi"] >= 80.0:
        badges.append({
            "title": "Road Warrior",
            "icon": "🛣️",
            "desc": f"Conquered a {trips['longest_drive']['distance_mi']} mi road trip to {trips['longest_drive']['end_location']}."
        })

    if superchargers["all_time_unique_count"] >= 3:
        badges.append({
            "title": "Supercharger Explorer",
            "icon": "⚡",
            "desc": f"Visited {superchargers['all_time_unique_count']} unique Tesla Supercharger stations."
        })

    if charging["gas_savings"]["net_savings"] >= 300.0:
        badges.append({
            "title": "Wallet Defender",
            "icon": "💰",
            "desc": f"Pocketed ${charging['gas_savings']['net_savings']:,.2f} in net gas savings!"
        })

    if charging["gas_savings"]["co2_lbs_prevented"] >= 1000.0:
        badges.append({
            "title": "Carbon Crusher",
            "icon": "🌱",
            "desc": f"Prevented {charging['gas_savings']['co2_lbs_prevented']:,.0f} lbs of CO2 emissions from entering the air."
        })

    return {
        "year": year,
        "total_miles": total_miles,
        "earth_circumnavigations": earth_circumnavigations,
        "ascent_ft": ascent_ft,
        "everest_equivalents": everest_equivalents,
        "trips": trips,
        "charging": charging,
        "superchargers": superchargers,
        "battery": battery,
        "badges": badges
    }
