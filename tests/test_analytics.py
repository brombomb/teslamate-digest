import pytest
from app.config import RatesSettings


def test_tou_calculations():
    rates = RatesSettings(
        off_peak_kwh_cost=0.09,
        on_peak_kwh_cost=0.16,
        supercharger_fallback_cost=0.36,
        gas_price_per_gal=3.50,
        baseline_ice_mpg=26.0
    )

    # 500 kWh off-peak, 100 kWh on-peak, 50 kWh supercharger
    home_spend = (500 * rates.off_peak_kwh_cost) + (100 * rates.on_peak_kwh_cost)
    assert home_spend == 45.0 + 16.0  # $61.00

    sc_spend = 50 * rates.supercharger_fallback_cost
    assert sc_spend == 18.0

    total_spend = home_spend + sc_spend
    assert total_spend == 79.0

    # 2,000 miles driven
    miles_driven = 2000.0
    gallons_avoided = miles_driven / rates.baseline_ice_mpg
    assert round(gallons_avoided, 1) == 76.9

    gas_spend_equivalent = gallons_avoided * rates.gas_price_per_gal
    assert round(gas_spend_equivalent, 2) == 269.23

    net_savings = gas_spend_equivalent - total_spend
    assert round(net_savings, 2) == 190.23


def test_battery_health_formula():
    # Model X example: 285.8 mi rated range at 100%
    # If end_rated_range_km = 414.0 at 90% battery
    end_rated_range_km = 414.0
    end_battery_level = 90
    rated_100_km = (end_rated_range_km / end_battery_level) * 100
    rated_100_mi = rated_100_km * 0.621371
    assert round(rated_100_mi, 1) == 285.8

    # Degradation from 295.0 mi baseline
    baseline = 295.0
    degradation_pct = ((baseline - rated_100_mi) / baseline) * 100.0
    capacity_retained = 100.0 - degradation_pct
    assert round(capacity_retained, 1) == 96.9


def test_tpms_thresholds():
    def get_status(psi: float):
        if 40.0 <= psi <= 44.5:
            return "Good"
        elif 38.0 <= psi < 40.0 or 44.5 < psi <= 47.0:
            return "Acceptable"
        else:
            return "Warning"

    assert get_status(42.1) == "Good"
    assert get_status(39.0) == "Acceptable"
    assert get_status(35.5) == "Warning"


def test_tire_rotation_counter():
    interval = 6250
    current_odometer = 94300
    last_rotation = 90000

    miles_since = current_odometer - last_rotation
    assert miles_since == 4300

    remaining = interval - miles_since
    assert remaining == 1950

    pct_used = (miles_since / interval) * 100
    assert round(pct_used, 1) == 68.8
    assert miles_since < interval


def test_eco_green_theme_validity():
    import matplotlib.colors as mcolors
    from app.themes import EMAIL_THEMES
    from app.charts import _get_chart_colors

    assert "eco_green" in EMAIL_THEMES
    eco = EMAIL_THEMES["eco_green"]
    assert eco["card_bg"] == "#232f2e"
    assert eco["accent_green"] == "#4b9d43"
    assert eco["accent_red"] == "#ef4444"

    # All chart theme colors must be directly valid in matplotlib
    chart_colors = _get_chart_colors(eco)
    for key, color_val in chart_colors.items():
        # Will raise ValueError if matplotlib cannot parse
        rgba = mcolors.to_rgba(color_val)
        assert len(rgba) == 4


def test_charts_clean_color():
    from app.charts import _clean_color
    assert _clean_color("rgb(75, 157, 67)") == "#4b9d43"
    assert _clean_color("rgb(35, 47, 46)") == "#232f2e"
    assert _clean_color("#e82127") == "#e82127"
    rgba_tuple = _clean_color("rgba(75, 157, 67, 0.5)")
    assert isinstance(rgba_tuple, tuple)
    assert rgba_tuple[3] == 0.5


def test_achievements_structure_and_evaluation():
    import asyncio
    from datetime import datetime, timedelta
    from app.analytics.achievements import ACHIEVEMENT_DEFINITIONS, get_achievements_analytics

    assert len(ACHIEVEMENT_DEFINITIONS) >= 40
    for ach in ACHIEVEMENT_DEFINITIONS:
        assert "id" in ach
        assert "category" in ach
        assert "name" in ach
        assert "icon" in ach
        assert "description" in ach

    # Mock Database
    class MockDB:
        async def fetchrow(self, query, *args):
            return {
                "total_drives": 50,
                "total_dist": 12000.0,
                "max_dist": 450.0,
                "total_drive_min": 15000,
                "weekend_dist": 4000.0,
                "weekday_dist": 8000.0,
                "night_dist": 200.0,
                "hypermiler": True,
                "night_rider": True,
                "period_hypermiler": True,
                "period_night_rider": False,
                "period_dist": 800.0,
                "total_charges": 30,
                "total_charge_min": 1200,
                "total_charge_kwh": 600.0,
                "free_charge_kwh": 200.0,
                "early_charges": 15,
                "offpeak_charges": 25,
                "opt_charges": 20,
                "full_cycle": False,
                "ac_charges": 26,
                "fast_charges": 4,
                "period_full_cycle": False,
                "speedster": False,
                "inferno_rider": True,
                "ice_road_trucker": False,
                "first_spark": True,
                "cities": 8,
                "counties": 12,
                "states": 2,
                "max_home_dist_km": 350.0,
                "total_climb_m": 12000,
                "sc_junkie": True,
                "period_sc_junkie": True,
                "living_on_edge": True,
                "sub_zero": False,
            }

    db = MockDB()
    now = datetime.now()
    res = asyncio.run(get_achievements_analytics(db, now - timedelta(days=30), now, car_id=1))

    assert res["has_data"] is True
    assert res["total_unlocked"] > 0
    assert res["total_achievements"] == len(ACHIEVEMENT_DEFINITIONS)
    assert 0 < res["unlocked_pct"] <= 100
    assert len(res["highlighted"]) > 0
    assert len(res["categories"]) > 0

    # Verify specific unlocks from our mock
    unlocked_ids = {b["id"] for b in res["all_badges"] if b["unlocked"]}
    assert "hypermiler" in unlocked_ids
    assert "supercharger_junkie" in unlocked_ids
    assert "local_explorer" in unlocked_ids
    assert "regional_explorer" in unlocked_ids
    assert "total_marathoner" in unlocked_ids
    assert "adventurer" in unlocked_ids
    assert "mountaineer" in unlocked_ids


