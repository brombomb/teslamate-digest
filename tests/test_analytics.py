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

