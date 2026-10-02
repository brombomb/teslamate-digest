import pytest
from datetime import datetime, timedelta
from app.config import AppConfig, UnitSettings
from app.services.units import (
    get_effective_units,
    convert_distance,
    convert_speed,
    convert_elevation,
    convert_pressure,
    convert_temperature,
)
from app.report import get_jinja_env


def test_unit_conversions():
    # Distance: km to mi
    assert convert_distance(100.0, "mi") == 62.1
    assert convert_distance(100.0, "km") == 100.0

    # Speed: km/h to mph
    assert convert_speed(100.0, "mph") == 62.1
    assert convert_speed(100.0, "km/h") == 100.0

    # Elevation: m to ft
    assert convert_elevation(1000.0, "ft") == 3281
    assert convert_elevation(1000.0, "m") == 1000

    # Pressure: bar to psi
    assert convert_pressure(2.9, "psi") == 42.1
    assert convert_pressure(2.9, "bar") == 2.9

    # Temperature: C to F
    assert convert_temperature(20.0, "F") == 68.0
    assert convert_temperature(20.0, "C") == 20.0


@pytest.mark.anyio
async def test_get_effective_units_imperial():
    cfg = AppConfig()
    cfg.units = UnitSettings(unit_system="imperial", currency="$")
    units = await get_effective_units(None, cfg)

    assert units["unit_system"] == "imperial"
    assert units["length"] == "mi"
    assert units["speed"] == "mph"
    assert units["pressure"] == "psi"
    assert units["temp"] == "F"
    assert units["elevation"] == "ft"
    assert units["consumption"] == "Wh/mi"
    assert units["is_imperial"] is True
    assert units["is_metric"] is False
    assert units["currency"] == "$"


@pytest.mark.anyio
async def test_get_effective_units_metric():
    cfg = AppConfig()
    cfg.units = UnitSettings(unit_system="metric", currency="€")
    units = await get_effective_units(None, cfg)

    assert units["unit_system"] == "metric"
    assert units["length"] == "km"
    assert units["speed"] == "km/h"
    assert units["pressure"] == "bar"
    assert units["temp"] == "C"
    assert units["elevation"] == "m"
    assert units["consumption"] == "Wh/km"
    assert units["is_imperial"] is False
    assert units["is_metric"] is True
    assert units["currency"] == "€"


@pytest.mark.anyio
async def test_get_effective_units_auto_mock_db():
    class MockDb:
        async def fetchrow(self, query, *args):
            return {
                "unit_of_length": "mi",
                "unit_of_temperature": "F",
                "unit_of_pressure": "bar"
            }

    cfg = AppConfig()
    cfg.units = UnitSettings(unit_system="auto")
    units = await get_effective_units(MockDb(), cfg)

    assert units["unit_system"] == "auto"
    assert units["length"] == "mi"
    assert units["pressure"] == "bar"
    assert units["temp"] == "F"
    assert units["speed"] == "mph"
    assert units["db_length"] == "mi"
    assert units["db_pressure"] == "bar"


@pytest.mark.anyio
async def test_get_effective_units_custom():
    cfg = AppConfig()
    cfg.units = UnitSettings(unit_system="custom", length="km", temp="C", pressure="psi", currency="£")
    units = await get_effective_units(None, cfg)

    assert units["unit_system"] == "custom"
    assert units["length"] == "km"
    assert units["temp"] == "C"
    assert units["pressure"] == "psi"
    assert units["speed"] == "km/h"
    assert units["currency"] == "£"


def test_digest_template_renders_imperial_and_metric():
    env = get_jinja_env()
    tmpl = env.get_template("digest.html")

    from app.themes import get_theme
    theme = get_theme("dark_modern")

    # Sample mock data
    trips = {
        "drives_count": 10,
        "total_miles": 500.0,
        "total_km": 804.7,
        "total_duration_hours": 12.5,
        "avg_trip_miles": 50.0,
        "avg_trip_km": 80.5,
        "top_speed_mph": 85.0,
        "top_speed_kmh": 136.8,
        "elevation": {
            "ascent_ft": 4500,
            "descent_ft": 4300,
            "ascent_m": 1372,
            "descent_m": 1311,
            "regen_kwh_recaptured": 6.2,
        },
        "longest_drive": {
            "distance_mi": 120.0,
            "distance_km": 193.1,
            "duration_min": 115,
            "start_location": "Home",
            "end_location": "Mountain Resort",
            "ascent_ft": 2500,
            "ascent_m": 762,
            "date": "Sep 15, 2026",
        },
        "top_places": [{"name": "Office", "city": "Denver", "visits": 8}],
    }

    charging = {
        "home_spend": 35.50,
        "home_kwh": 300.0,
        "supercharger_spend": 15.00,
        "supercharger_kwh": 40.0,
        "total_spend": 50.50,
        "total_energy_used_kwh": 340.0,
        "efficiency_pct": 92.4,
        "off_peak_spend": 30.00,
        "off_peak_kwh": 260.0,
        "shoulder_spend": 5.50,
        "shoulder_kwh": 40.0,
        "off_peak_score_pct": 86.7,
        "gas_savings": {
            "gas_spend_equivalent": 140.00,
            "net_savings": 89.50,
        },
    }

    efficiency = {
        "avg_wh_per_mile": 280,
        "avg_wh_per_km": 174,
        "efficiency_pct": 94.5,
        "grade": "Excellent",
        "net_energy_kwh": 140.0,
        "total_drives": 10,
        "cars_breakdown": [
            {
                "name": "Model 3",
                "model": "3",
                "actual_miles": 500.0,
                "actual_km": 804.7,
                "wh_per_mile": 280,
                "wh_per_km": 174,
                "efficiency_pct": 94.5,
            }
        ],
    }

    health = {
        "cars": [
            {
                "car_name": "Model 3",
                "model": "3",
                "tpms": {
                    "front_left": 42.0,
                    "front_right": 42.0,
                    "rear_left": 42.0,
                    "rear_right": 42.0,
                    "unit": "psi",
                    "fl_info": {"color": "#10b981"},
                    "fr_info": {"color": "#10b981"},
                    "rl_info": {"color": "#10b981"},
                    "rr_info": {"color": "#10b981"},
                    "has_alert": False,
                },
                "tire_rotation": {
                    "dist_driven_since": 3200,
                    "interval": 6250,
                    "dist_remaining": 3050,
                    "unit": "mi",
                    "color": "#10b981",
                    "pct_progress": 48.8,
                    "is_due": False,
                },
                "snow_tires": {"reminder": None},
                "updates": [],
            }
        ]
    }

    vampire = {
        "total_idle_hours": 120,
        "estimated_loss_kwh": 14.5,
        "estimated_cost": 1.88,
        "drain_rate_w": 120,
    }

    superchargers = {
        "lifetime_unique_stations": 5,
        "all_time_unique_count": 5,
        "period_sessions": [],
        "recent_sessions": [],
    }

    achievements_with_badges = {
        "has_data": True,
        "total_unlocked": 14,
        "total_achievements": 40,
        "unlocked_pct": 35,
        "earned_this_period": [
            {
                "id": "hypermiler",
                "name": "Hypermiler",
                "icon": "🏅",
                "description": "Drive >50 km with >100% efficiency vs rated range",
            }
        ],
        "has_earned_this_period": True,
        "categories": [],
        "next_milestones": [],
    }

    achievements_fallback = {
        "has_data": True,
        "total_unlocked": 14,
        "total_achievements": 40,
        "unlocked_pct": 35,
        "earned_this_period": [],
        "has_earned_this_period": False,
        "categories": [],
        "next_milestones": [
            {
                "id": "total_marathoner",
                "name": "Total Marathoner",
                "icon": "🏃",
                "progress_text": "3,400 / 6,214 mi • 54%",
            }
        ],
    }

    rates = AppConfig().rates
    modules = AppConfig().modules

    # Test 1: Imperial rendering
    units_imperial = {
        "length": "mi",
        "speed": "mph",
        "pressure": "psi",
        "temp": "F",
        "elevation": "ft",
        "consumption": "Wh/mi",
        "currency": "$",
        "is_imperial": True,
        "is_metric": False,
    }

    html_imp = tmpl.render(
        report_title="Monthly Report",
        date_subtitle="Sep 1 - Sep 30, 2026",
        car_subtitle="Model 3",
        units=units_imperial,
        trips=trips,
        charging=charging,
        superchargers=superchargers,
        vampire=vampire,
        efficiency=efficiency,
        health=health,
        achievements=achievements_with_badges,
        rates=rates,
        modules=modules,
        theme=theme,
    )
    assert "Miles Driven" in html_imp
    assert "500" in html_imp
    assert "Badges Earned This Period (1)" in html_imp
    assert "Hypermiler" in html_imp

    # Test 2: Metric rendering with badge fallback status
    units_metric = {
        "length": "km",
        "speed": "km/h",
        "pressure": "bar",
        "temp": "C",
        "elevation": "m",
        "consumption": "Wh/km",
        "currency": "€",
        "is_imperial": False,
        "is_metric": True,
    }

    html_met = tmpl.render(
        report_title="Monthly Report",
        date_subtitle="Sep 1 - Sep 30, 2026",
        car_subtitle="Model 3",
        units=units_metric,
        trips=trips,
        charging=charging,
        superchargers=superchargers,
        vampire=vampire,
        efficiency=efficiency,
        health=health,
        achievements=achievements_fallback,
        rates=rates,
        modules=modules,
        theme=theme,
    )
    assert "Kilometers Driven" in html_met
    assert "805" in html_met
    assert "No New Badges Earned This Period" in html_met
    assert "Total Marathoner" in html_met
    assert "Next Milestone Targets" in html_met


def test_settings_integrations_endpoint_units():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import load_config

    client = TestClient(app)

    # 1. GET /settings/integrations renders Units card
    resp = client.get("/settings/integrations")
    assert resp.status_code == 200
    assert "Units of Measurement" in resp.text
    assert "unit_system_select" in resp.text

    # 2. POST /settings/integrations with metric units
    post_data = {
        "rate_mode": "tou",
        "average_kwh_cost": "0.13",
        "off_peak_kwh_cost": "0.10",
        "shoulder_kwh_cost": "0.14",
        "on_peak_kwh_cost": "0.20",
        "off_peak_start_hour": "21",
        "off_peak_end_hour": "9",
        "peak_start_hour": "13",
        "peak_end_hour": "19",
        "supercharger_fallback_cost": "0.36",
        "unit_system": "metric",
        "unit_length": "km",
        "unit_temp": "C",
        "unit_pressure": "bar",
        "unit_currency": "€",
    }
    resp_post = client.post("/settings/integrations", data=post_data)
    assert resp_post.status_code == 200
    assert "Rates, commute routes, and integrations updated and saved successfully!" in resp_post.text

    reloaded = load_config()
    assert reloaded.units.unit_system == "metric"
    assert reloaded.units.length == "km"
    assert reloaded.units.currency == "€"

    # 3. Restore to auto
    post_data["unit_system"] = "auto"
    post_data["unit_currency"] = "$"
    resp_restore = client.post("/settings/integrations", data=post_data)
    assert resp_restore.status_code == 200

    reloaded_auto = load_config()
    assert reloaded_auto.units.unit_system == "auto"
    assert reloaded_auto.units.currency == "$"

