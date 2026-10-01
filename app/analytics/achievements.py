import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.db import Database

logger = logging.getLogger(__name__)

ACHIEVEMENT_DEFINITIONS = [
    # 🌿 Efficiency & Energy
    {
        "id": "hypermiler",
        "category": "Efficiency & Energy",
        "category_icon": "🌿",
        "icon": "🏅",
        "name": "Hypermiler",
        "description": "Drive >50 km with >100% efficiency vs rated range",
    },
    {
        "id": "supercharger_junkie",
        "category": "Efficiency & Energy",
        "category_icon": "🌿",
        "icon": "⚡",
        "name": "Supercharger Junkie",
        "description": "Fast charge at peak speeds over 120 kW",
    },
    {
        "id": "living_on_edge",
        "category": "Efficiency & Energy",
        "category_icon": "🌿",
        "icon": "⚠️",
        "name": "Living on the Edge",
        "description": "Complete a drive arriving with < 5% battery",
    },
    {
        "id": "efficiency_master",
        "category": "Efficiency & Energy",
        "category_icon": "🌿",
        "icon": "🍃",
        "name": "Efficiency Master",
        "description": "Lifetime drive efficiency > 100% vs rated range",
    },
    # 🌍 Exploration & Geography
    {
        "id": "local_explorer",
        "category": "Exploration & Geography",
        "category_icon": "🌍",
        "icon": "🏙️",
        "name": "Local Explorer",
        "description": "Visit 5 or more unique cities",
    },
    {
        "id": "regional_explorer",
        "category": "Exploration & Geography",
        "category_icon": "🌍",
        "icon": "🗺️",
        "name": "Regional Explorer",
        "description": "Visit 10 or more unique counties/regions",
    },
    {
        "id": "national_explorer",
        "category": "Exploration & Geography",
        "category_icon": "🌍",
        "icon": "🧭",
        "name": "National Explorer",
        "description": "Visit 15 or more unique states/provinces",
    },
    {
        "id": "adventurer",
        "category": "Exploration & Geography",
        "category_icon": "🌍",
        "icon": "🎒",
        "name": "Adventurer",
        "description": "Travel more than 300 km (186 mi) from home",
    },
    {
        "id": "globetrotter",
        "category": "Exploration & Geography",
        "category_icon": "🌍",
        "icon": "🌍",
        "name": "Globetrotter",
        "description": "Travel more than 500 km (310 mi) from home",
    },
    # ⏱️ Time & Weather
    {
        "id": "night_rider",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "🦇",
        "name": "Night Rider",
        "description": "Complete a drive between 02:00 AM and 05:00 AM",
    },
    {
        "id": "night_owl",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "🌙",
        "name": "Night Owl",
        "description": "Accumulate > 100 km driving at night (00:00 - 06:00)",
    },
    {
        "id": "midnight_warrior",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "🦉",
        "name": "Midnight Warrior",
        "description": "Accumulate > 500 km driving at night (00:00 - 06:00)",
    },
    {
        "id": "early_bird",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "🌅",
        "name": "Early Bird",
        "description": "Start 10 or more charging sessions before 7:00 AM",
    },
    {
        "id": "rise_and_shine",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "🐓",
        "name": "Rise and Shine",
        "description": "Start 50 or more charging sessions before 7:00 AM",
    },
    {
        "id": "sub_zero",
        "category": "Time & Weather",
        "category_icon": "⏱️",
        "icon": "❄️",
        "name": "Sub-Zero",
        "description": "Charge while ambient temperature is below 0°C (32°F)",
    },
    # 🏎️ Endurance & Performance
    {
        "id": "total_marathoner",
        "category": "Endurance & Performance",
        "category_icon": "🏎️",
        "icon": "🏃",
        "name": "Total Marathoner",
        "description": "Accumulate > 10,000 km (6,213 mi) total distance",
    },
    {
        "id": "daily_marathoner",
        "category": "Endurance & Performance",
        "category_icon": "🏎️",
        "icon": "👟",
        "name": "Daily Marathoner",
        "description": "Drive > 500 km (310 mi) in a single day",
    },
    {
        "id": "iron_butt",
        "category": "Endurance & Performance",
        "category_icon": "🏎️",
        "icon": "🍑",
        "name": "Iron Butt",
        "description": "Drive > 400 km (248 mi) in a single continuous trip",
    },
    {
        "id": "speedster",
        "category": "Endurance & Performance",
        "category_icon": "🏎️",
        "icon": "🚀",
        "name": "Speedster",
        "description": "Reach a peak speed over 180 km/h (112 mph)",
    },
    # 💰 Savings & Habits
    {
        "id": "first_spark",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🔓",
        "name": "First Spark",
        "description": "First telemetry record logged in TeslaMate",
    },
    {
        "id": "bounty_hunter",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🆓",
        "name": "Bounty Hunter",
        "description": "Charge 100 kWh for free ($0 cost recorded)",
    },
    {
        "id": "freeloader",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🏴‍☠️",
        "name": "Freeloader",
        "description": "Charge 1,000 kWh for free ($0 cost recorded)",
    },
    {
        "id": "night_planner",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🌙",
        "name": "Night Planner",
        "description": "Complete 50 charging sessions off-peak (00:00 - 08:00)",
    },
    {
        "id": "thrifty",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🐖",
        "name": "Thrifty",
        "description": "Save estimated > $500 vs gasoline",
    },
    {
        "id": "green_tycoon",
        "category": "Savings & Charging Habits",
        "category_icon": "💰",
        "icon": "🤑",
        "name": "Green Tycoon",
        "description": "Save estimated > $1,000 vs gasoline",
    },
    # 🔋 Battery Tech & Strategy
    {
        "id": "patient_lvl1",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "🧘",
        "name": "Patient Lvl 1",
        "description": "Spend 10 cumulative hours charging",
    },
    {
        "id": "patient_lvl2",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "🧘",
        "name": "Patient Lvl 2",
        "description": "Spend 50 cumulative hours charging",
    },
    {
        "id": "patient_lvl3",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "🧘",
        "name": "Patient Lvl 3",
        "description": "Spend 100 cumulative hours charging",
    },
    {
        "id": "ac_devotee",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "🔌",
        "name": "AC Devotee",
        "description": "Over 80% of charging sessions are AC / Level 2",
    },
    {
        "id": "the_optimizer",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "📐",
        "name": "The Optimizer",
        "description": "Complete 100 charges ending between 80% and 90% SoC",
    },
    {
        "id": "full_cycle",
        "category": "Battery Tech & Strategy",
        "category_icon": "🔋",
        "icon": "🔋",
        "name": "Full Cycle",
        "description": "Charge from < 10% to > 95% battery level",
    },
    # 🌿 Ecology & Impact
    {
        "id": "planet_guardian",
        "category": "Ecology & Impact",
        "category_icon": "🌿",
        "icon": "🛡️",
        "name": "Planet Guardian",
        "description": "Prevent 1,000 kg of CO2 emissions vs ICE vehicle",
    },
    {
        "id": "climate_hero",
        "category": "Ecology & Impact",
        "category_icon": "🌿",
        "icon": "🦸",
        "name": "Climate Hero",
        "description": "Prevent 5,000 kg of CO2 emissions vs ICE vehicle",
    },
    {
        "id": "personal_forest",
        "category": "Ecology & Impact",
        "category_icon": "🌿",
        "icon": "🌳",
        "name": "Personal Forest",
        "description": "Offset emissions equal to planting 50 mature trees",
    },
    {
        "id": "amazon_rainforest",
        "category": "Ecology & Impact",
        "category_icon": "🌿",
        "icon": "🦜",
        "name": "Amazon Rainforest",
        "description": "Offset emissions equal to planting 200 mature trees",
    },
    # 🚀 Space & Time Continuum
    {
        "id": "around_the_world",
        "category": "Space & Time Continuum",
        "category_icon": "🚀",
        "icon": "🌍",
        "name": "Around the World",
        "description": "Drive 40,075 km (24,901 mi) - Earth circumference",
    },
    {
        "id": "iss_orbiter",
        "category": "Space & Time Continuum",
        "category_icon": "🚀",
        "icon": "🛰️",
        "name": "ISS Orbiter",
        "description": "Drive 42,500 km - One full International Space Station orbit",
    },
    {
        "id": "lemans_24h",
        "category": "Space & Time Continuum",
        "category_icon": "🚀",
        "icon": "🏎️",
        "name": "24h Le Mans",
        "description": "Spend 24 cumulative hours behind the wheel",
    },
    {
        "id": "road_tourist",
        "category": "Space & Time Continuum",
        "category_icon": "🚀",
        "icon": "📸",
        "name": "Road Tourist",
        "description": "Spend 100 cumulative hours behind the wheel",
    },
    {
        "id": "week_on_road",
        "category": "Space & Time Continuum",
        "category_icon": "🚀",
        "icon": "📅",
        "name": "A Week on the Road",
        "description": "Spend 168 cumulative hours (1 full week) driving",
    },
    # 🏔️ Habits & Extremes
    {
        "id": "weekender",
        "category": "Habits & Extremes",
        "category_icon": "🏔️",
        "icon": "🏖️",
        "name": "Weekender",
        "description": "Over 60% of all driving completed on weekends",
    },
    {
        "id": "workaholic",
        "category": "Habits & Extremes",
        "category_icon": "🏔️",
        "icon": "💼",
        "name": "Workaholic",
        "description": "Over 60% of all driving completed on weekdays",
    },
    {
        "id": "inferno_rider",
        "category": "Habits & Extremes",
        "category_icon": "🏔️",
        "icon": "🔥",
        "name": "Inferno Rider",
        "description": "Drive in scorching heat above 40°C (104°F)",
    },
    {
        "id": "ice_road_trucker",
        "category": "Habits & Extremes",
        "category_icon": "🏔️",
        "icon": "❄️",
        "name": "Ice Road Trucker",
        "description": "Drive in freezing conditions below -10°C (14°F)",
    },
    {
        "id": "mountaineer",
        "category": "Habits & Extremes",
        "category_icon": "🏔️",
        "icon": "⛰️",
        "name": "Mountaineer",
        "description": "Climb 10,000 meters (32,800 ft) cumulative elevation",
    },
]


async def get_achievements_analytics(
    db: Database,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Evaluates driving achievements and gamification badges from TeslaMate database,
    identifies achievements active/unlocked during this reporting period,
    and returns progress breakdown across categories.
    """
    c_filter = f"WHERE car_id = {car_id}" if car_id else ""
    c_and_d = f"AND d.car_id = {car_id}" if car_id else ""
    c_and_cp = f"AND cp.car_id = {car_id}" if car_id else ""
    c_and_p = f"AND p.car_id = {car_id}" if car_id else ""

    p_filter_d = f"AND d.start_date >= '{start_date.isoformat()}' AND d.start_date < '{end_date.isoformat()}'"
    p_filter_cp = f"AND cp.start_date >= '{start_date.isoformat()}' AND cp.start_date < '{end_date.isoformat()}'"

    sql = f"""
    WITH
      d_stats AS (
        SELECT 
          count(*) as total_drives,
          coalesce(sum(distance), 0) as total_dist,
          coalesce(max(distance), 0) as max_dist,
          coalesce(sum(duration_min), 0) as total_drive_min,
          coalesce(sum(distance) FILTER (WHERE EXTRACT(ISODOW FROM start_date) IN (6,7)), 0) as weekend_dist,
          coalesce(sum(distance) FILTER (WHERE EXTRACT(ISODOW FROM start_date) NOT IN (6,7)), 0) as weekday_dist,
          coalesce(sum(distance) FILTER (WHERE EXTRACT(HOUR FROM start_date) BETWEEN 0 AND 6), 0) as night_dist,
          bool_or(distance > 50 AND (start_rated_range_km - end_rated_range_km) > 0 AND distance > (start_rated_range_km - end_rated_range_km)) as hypermiler,
          bool_or(EXTRACT(HOUR FROM start_date) BETWEEN 2 AND 5) as night_rider,
          -- Period-specific drive milestones
          bool_or(distance > 50 AND (start_rated_range_km - end_rated_range_km) > 0 AND distance > (start_rated_range_km - end_rated_range_km) {p_filter_d}) as period_hypermiler,
          bool_or(EXTRACT(HOUR FROM start_date) BETWEEN 2 AND 5 {p_filter_d}) as period_night_rider,
          coalesce(sum(distance) FILTER (WHERE 1=1 {p_filter_d}), 0) as period_dist
        FROM drives d {c_filter}
      ),
      c_stats AS (
        SELECT
          count(*) as total_charges,
          coalesce(sum(duration_min), 0) as total_charge_min,
          coalesce(sum(charge_energy_added), 0) as total_charge_kwh,
          coalesce(sum(charge_energy_added) FILTER (WHERE cost = 0 OR cost IS NULL), 0) as free_charge_kwh,
          count(*) FILTER (WHERE EXTRACT(HOUR FROM start_date) < 7) as early_charges,
          count(*) FILTER (WHERE EXTRACT(HOUR FROM start_date) BETWEEN 0 AND 8) as offpeak_charges,
          count(*) FILTER (WHERE end_battery_level BETWEEN 80 AND 90) as opt_charges,
          bool_or(start_battery_level < 10 AND end_battery_level > 95) as full_cycle,
          count(*) FILTER (WHERE duration_min > 0 AND (charge_energy_added / NULLIF(duration_min/60.0, 0)) < 22) as ac_charges,
          count(*) FILTER (WHERE duration_min > 0 AND (charge_energy_added / NULLIF(duration_min/60.0, 0)) > 50) as fast_charges,
          -- Period-specific charging
          bool_or(start_battery_level < 10 AND end_battery_level > 95 {p_filter_cp}) as period_full_cycle
        FROM charging_processes cp {c_filter}
      ),
      p_stats AS (
        SELECT
          bool_or(speed > 180) as speedster,
          bool_or(outside_temp > 40) as inferno_rider,
          bool_or(outside_temp < -10) as ice_road_trucker,
          count(*) > 0 as first_spark
        FROM positions p {c_filter}
      ),
      geo_stats AS (
        SELECT
          count(distinct a.city) as cities,
          count(distinct a.county) as counties,
          count(distinct a.state) as states
        FROM addresses a
        JOIN drives d ON d.end_address_id = a.id
        WHERE 1=1 {c_and_d}
      ),
      home_dist AS (
        SELECT coalesce(max(
          6371 * acos(LEAST(1.0, GREATEST(-1.0,
            cos(radians(g.latitude)) * cos(radians(p.latitude)) * cos(radians(p.longitude) - radians(g.longitude)) +
            sin(radians(g.latitude)) * sin(radians(p.latitude))
          )))
        ), 0) as max_home_dist_km
        FROM positions p, geofences g
        WHERE (g.name ILIKE '%Home%' OR g.name ILIKE '%Casa%') {c_and_p}
      ),
      elev_stats AS (
        SELECT coalesce(sum(p_end.elevation - p_start.elevation), 0) as total_climb_m
        FROM drives d
        JOIN positions p_start ON d.start_position_id = p_start.id
        JOIN positions p_end ON d.end_position_id = p_end.id
        WHERE p_end.elevation > p_start.elevation {c_and_d}
      ),
      sc_power AS (
        SELECT 
          bool_or(c.charger_power > 120) as sc_junkie,
          bool_or(c.charger_power > 120 AND cp.start_date >= '{start_date.isoformat()}' AND cp.start_date < '{end_date.isoformat()}') as period_sc_junkie
        FROM charges c
        JOIN charging_processes cp ON cp.id = c.charging_process_id
        WHERE 1=1 {c_and_cp}
      ),
      low_batt AS (
        SELECT bool_or(p.battery_level < 5) as living_on_edge
        FROM drives d
        JOIN positions p ON p.id = d.end_position_id
        WHERE 1=1 {c_and_d}
      ),
      temp_charge AS (
        SELECT bool_or(p.outside_temp < 0) as sub_zero
        FROM charging_processes cp
        JOIN positions p ON p.id = cp.position_id
        WHERE 1=1 {c_and_cp}
      )
    SELECT 
      d.*, c.*, p.*, g.*, h.*, e.*, sc.*, lb.*, tc.*
    FROM d_stats d
    CROSS JOIN c_stats c
    CROSS JOIN p_stats p
    CROSS JOIN geo_stats g
    CROSS JOIN home_dist h
    CROSS JOIN elev_stats e
    CROSS JOIN sc_power sc
    CROSS JOIN low_batt lb
    CROSS JOIN temp_charge tc;
    """

    try:
        row = await db.fetchrow(sql)
    except Exception as e:
        logger.error(f"Error fetching achievements analytics: {e}")
        return {
            "has_data": False,
            "total_unlocked": 0,
            "total_achievements": len(ACHIEVEMENT_DEFINITIONS),
            "unlocked_pct": 0,
            "highlighted": [],
            "recent_unlocked": [],
            "categories": [],
        }

    if not row:
        return {
            "has_data": False,
            "total_unlocked": 0,
            "total_achievements": len(ACHIEVEMENT_DEFINITIONS),
            "unlocked_pct": 0,
            "highlighted": [],
            "recent_unlocked": [],
            "categories": [],
        }

    total_dist = float(row.get("total_dist") or 0.0)
    total_drives = int(row.get("total_drives") or 0)
    weekend_dist = float(row.get("weekend_dist") or 0.0)
    weekday_dist = float(row.get("weekday_dist") or 0.0)
    total_charges = int(row.get("total_charges") or 0)
    ac_charges = int(row.get("ac_charges") or 0)
    co2_kg = total_dist * 0.12  # standard 120g CO2/km saved vs average ICE

    # Calculate status per achievement ID
    unlocked_map = {
        "hypermiler": bool(row.get("hypermiler")),
        "supercharger_junkie": bool(row.get("sc_junkie")),
        "living_on_edge": bool(row.get("living_on_edge")),
        "efficiency_master": total_drives > 10 and bool(row.get("hypermiler")),
        "local_explorer": (row.get("cities") or 0) >= 5,
        "regional_explorer": (row.get("counties") or 0) >= 10,
        "national_explorer": (row.get("states") or 0) >= 15,
        "adventurer": float(row.get("max_home_dist_km") or 0.0) >= 300,
        "globetrotter": float(row.get("max_home_dist_km") or 0.0) >= 500,
        "night_rider": bool(row.get("night_rider")),
        "night_owl": float(row.get("night_dist") or 0.0) >= 100,
        "midnight_warrior": float(row.get("night_dist") or 0.0) >= 500,
        "early_bird": (row.get("early_charges") or 0) >= 10,
        "rise_and_shine": (row.get("early_charges") or 0) >= 50,
        "sub_zero": bool(row.get("sub_zero")),
        "total_marathoner": total_dist >= 10000,
        "daily_marathoner": float(row.get("max_dist") or 0.0) >= 500,
        "iron_butt": float(row.get("max_dist") or 0.0) >= 400,
        "speedster": bool(row.get("speedster")),
        "first_spark": bool(row.get("first_spark")),
        "bounty_hunter": float(row.get("free_charge_kwh") or 0.0) >= 100,
        "freeloader": float(row.get("free_charge_kwh") or 0.0) >= 1000,
        "night_planner": (row.get("offpeak_charges") or 0) >= 50,
        "thrifty": total_dist * 0.08 >= 500,  # rough savings threshold
        "green_tycoon": total_dist * 0.08 >= 1000,
        "patient_lvl1": float(row.get("total_charge_min") or 0.0) >= 600,
        "patient_lvl2": float(row.get("total_charge_min") or 0.0) >= 3000,
        "patient_lvl3": float(row.get("total_charge_min") or 0.0) >= 6000,
        "ac_devotee": total_charges > 5 and (ac_charges / max(total_charges, 1)) >= 0.8,
        "the_optimizer": (row.get("opt_charges") or 0) >= 100,
        "full_cycle": bool(row.get("full_cycle")),
        "planet_guardian": co2_kg >= 1000,
        "climate_hero": co2_kg >= 5000,
        "personal_forest": co2_kg >= (50 * 22),
        "amazon_rainforest": co2_kg >= (200 * 22),
        "around_the_world": total_dist >= 40075,
        "iss_orbiter": total_dist >= 42500,
        "lemans_24h": float(row.get("total_drive_min") or 0.0) >= 1440,
        "road_tourist": float(row.get("total_drive_min") or 0.0) >= 6000,
        "week_on_road": float(row.get("total_drive_min") or 0.0) >= 10080,
        "weekender": total_dist > 500 and (weekend_dist / max(total_dist, 1.0)) > 0.6,
        "workaholic": total_dist > 500 and (weekday_dist / max(total_dist, 1.0)) > 0.6,
        "inferno_rider": bool(row.get("inferno_rider")),
        "ice_road_trucker": bool(row.get("ice_road_trucker")),
        "mountaineer": float(row.get("total_climb_m") or 0.0) >= 10000,
    }

    # Achievements active/seen during this period
    period_active_ids = set()
    if row.get("period_hypermiler"):
        period_active_ids.add("hypermiler")
    if row.get("period_sc_junkie"):
        period_active_ids.add("supercharger_junkie")
    if row.get("period_night_rider"):
        period_active_ids.add("night_rider")
    if row.get("period_full_cycle"):
        period_active_ids.add("full_cycle")
    if float(row.get("period_dist") or 0.0) > 0:
        period_active_ids.add("total_marathoner")

    all_badges = []
    unlocked_count = 0
    categories_dict: Dict[str, Dict[str, Any]] = {}

    for ach in ACHIEVEMENT_DEFINITIONS:
        aid = ach["id"]
        is_unlocked = unlocked_map.get(aid, False)
        is_period = aid in period_active_ids
        if is_unlocked:
            unlocked_count += 1

        badge = {
            **ach,
            "unlocked": is_unlocked,
            "period_active": is_period,
        }
        all_badges.append(badge)

        cat_name = ach["category"]
        if cat_name not in categories_dict:
            categories_dict[cat_name] = {
                "name": cat_name,
                "icon": ach["category_icon"],
                "total": 0,
                "unlocked": 0,
            }
        categories_dict[cat_name]["total"] += 1
        if is_unlocked:
            categories_dict[cat_name]["unlocked"] += 1

    categories_list = []
    for cat in categories_dict.values():
        total = cat["total"]
        unlocked = cat["unlocked"]
        cat["pct"] = int((unlocked / total) * 100) if total > 0 else 0
        categories_list.append(cat)

    # Highlight top unlocked badges (prioritizing period active and iconic badges)
    highlighted = sorted(
        [b for b in all_badges if b["unlocked"]],
        key=lambda x: (x.get("period_active", False), x["category"]),
        reverse=True
    )[:6]

    # Recent period highlights
    recent_unlocked = [b for b in all_badges if b["unlocked"] and b.get("period_active")]

    total_ach = len(ACHIEVEMENT_DEFINITIONS)
    completion_pct = int((unlocked_count / max(total_ach, 1)) * 100)

    return {
        "has_data": total_drives > 0 or total_charges > 0,
        "total_unlocked": unlocked_count,
        "total_achievements": total_ach,
        "unlocked_pct": completion_pct,
        "highlighted": highlighted,
        "recent_unlocked": recent_unlocked,
        "categories": categories_list,
        "all_badges": all_badges,
    }
