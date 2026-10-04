import pytest
from app.report import get_jinja_env
from app.themes import EMAIL_THEMES, get_theme


def test_digest_template_responsive_media_queries():
    env = get_jinja_env()
    template = env.get_template("digest.html")
    with open(template.filename, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify presence of @media query for mobile screens (<= 600px)
    assert "@media only screen and (max-width: 600px)" in content

    # Verify responsive structural utility classes
    assert ".main-table" in content
    assert ".grid-col-half" in content
    assert ".table-responsive" in content
    assert ".stack-mobile" in content
    assert ".mobile-hide" in content
    assert ".section-header-table" in content
    assert ".tpms-box" in content

    # Verify fluid max-width and viewport
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in content
    assert "-webkit-text-size-adjust: 100%;" in content


def test_top_kpi_row_uses_two_pair_responsive_grid():
    env = get_jinja_env()
    template = env.get_template("digest.html")
    with open(template.filename, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify the Top KPI row uses the 2x2 responsive wrapping structure with .grid-col-half
    assert "<!-- TOP KPI ROW (EQUAL HEIGHT BOXES, 2x2 ON MOBILE) -->" in content
    assert 'class="grid-col-half"' in content
    assert 'class="kpi-cell"' in content

    # Verify KPI boxes use standard HTML table alignment instead of fragile display: flex
    assert 'valign="middle"' in content
    assert 'align="center"' in content


def test_wrapped_template_responsive_media_queries():
    env = get_jinja_env()
    template = env.get_template("wrapped.html")
    with open(template.filename, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify @media query for mobile screens (<= 600px)
    assert "@media only screen and (max-width: 600px)" in content

    # Verify responsive classes
    assert ".hero-td" in content
    assert ".hero-h1" in content
    assert ".stack-mobile" in content
    assert ".table-responsive" in content
    assert '<table width="100%" cellpadding="0" cellspacing="0" class="table-responsive"' in content


def test_digest_template_renders_all_themes():
    env = get_jinja_env()
    template = env.get_template("digest.html")

    # Mock minimal context for rendering
    mock_context = {
        "report_title": "Monthly Tesla Digest",
        "date_subtitle": "October 2026",
        "car_subtitle": "Shadow",
        "car_id": 1,
        "teslamate_url": "http://localhost:4000",
        "grafana_url": "http://localhost:3000",
        "dashboard_url": "http://localhost:8660",
        "units": {
            "is_metric": False,
            "currency": "$",
            "length": "mi",
            "speed": "mph",
            "elevation": "ft",
            "pressure": "psi"
        },
        "rates": {
            "rate_mode": "tou",
            "gas_price_per_gal": 3.85,
            "baseline_ice_mpg": 28.0
        },
        "modules": {
            "spend_breakdown": True,
            "gas_savings": True,
            "solar_production": True,
            "driving_efficiency": True,
            "charge_limit_compliance": True,
            "work_mileage": True,
            "battery_health": True,
            "top_locations": True,
            "driving_milestones": True,
            "supercharger_explorer": True,
            "achievements": True,
            "maintenance_alerts": True,
            "vampire_drain": True
        },
        "trips": {
            "total_miles": 1250.0,
            "total_km": 2011.0,
            "drives_count": 42,
            "total_duration_hours": 32.5,
            "avg_trip_miles": 18.2,
            "avg_trip_km": 29.3,
            "top_speed_mph": 82.0,
            "top_speed_kmh": 132.0,
            "elevation": {"ascent_ft": 4500, "ascent_m": 1372, "regen_kwh_recaptured": 14.5},
            "longest_drive": None,
            "top_places": []
        },
        "charging": {
            "total_spend": 45.20,
            "efficiency_pct": 94.2,
            "off_peak_spend": 32.10,
            "off_peak_kwh": 280.0,
            "shoulder_spend": 8.10,
            "shoulder_kwh": 45.0,
            "supercharger_spend": 5.00,
            "supercharger_kwh": 20.0,
            "off_peak_score_pct": 88.0,
            "gas_savings": {"net_savings": 125.40, "gas_spend_equivalent": 170.60}
        },
        "solar": {
            "has_data": True,
            "total_solar_kwh": 450.0,
            "solar_savings": 54.00,
            "solar_ev_coverage_pct": 82.0,
            "clean_miles_covered": 1025,
            "grid_export_kwh": 120.0,
            "grid_import_kwh": 65.0,
            "peak_solar_kw": 7.8,
            "self_consumption_pct": 73.0,
            "home_charging_kwh": 320.0,
            "solar_surplus_kwh": 130.0
        },
        "efficiency": {
            "avg_wh_per_mile": 275.0,
            "avg_wh_per_km": 171.0,
            "efficiency_pct": 96.0,
            "grade": "A+",
            "net_energy_kwh": 343.8,
            "total_drives": 42,
            "cars_breakdown": []
        },
        "compliance": {
            "hours_above_80": 12.0,
            "pct_above_80": 4.5,
            "hours_optimal": 220.0,
            "pct_optimal": 82.5,
            "hours_below_20": 3.0,
            "pct_below_20": 1.1,
            "compliance_score": 94,
            "compliance_rating": "Excellent",
            "stress_level": "Low"
        },
        "work_mileage": {"has_routes": False, "routes": []},
        "show_battery_health": True,
        "battery": {"cars": []},
        "superchargers": {
            "lifetime_unique_stations": 15,
            "month_sessions_count": 3,
            "new_stations_this_month": [],
            "recent_visits": []
        },
        "achievements": {
            "has_data": True,
            "total_unlocked": 12,
            "total_achievements": 20,
            "unlocked_pct": 60.0,
            "categories": [],
            "earned_this_period": [],
            "next_milestones": []
        },
        "health": {"cars": []},
        "vampire": {
            "total_idle_hours": 620.0,
            "estimated_loss_kwh": 48.0,
            "estimated_cost": 5.76
        },
        "chart_spend": None,
        "chart_tou": None,
        "chart_solar": None,
        "chart_battery": None
    }

    # Render across multiple themes including cybertruck
    for theme_id in ["frost_blue", "cybertruck", "obsidian_black", "eco_green"]:
        theme = get_theme(theme_id)
        mock_context["theme"] = theme
        rendered = template.render(**mock_context)
        assert len(rendered) > 1000
        assert "@media only screen and (max-width: 600px)" in rendered
        assert "grid-col-half" in rendered
        assert "main-table" in rendered
