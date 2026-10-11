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


def test_digest_chart_containers_and_responsive_images():
    env = get_jinja_env()
    template = env.get_template("digest.html")
    with open(template.filename, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify CSS definitions for chart container and responsive image
    assert ".chart-container {" in content
    assert ".chart-img {" in content
    assert "width: 100% !important;" in content

    # Mock context containing all four embedded charts
    mock_context = {
        "report_title": "Monthly Tesla Digest",
        "date_subtitle": "October 2026",
        "car_subtitle": "Shadow",
        "car_id": 1,
        "theme": get_theme("frost_blue"),
        "teslamate_url": "http://localhost:4000",
        "grafana_url": "http://localhost:3000",
        "dashboard_url": "http://localhost:8660",
        "units": {"is_metric": False, "currency": "$", "length": "mi", "speed": "mph", "elevation": "ft", "pressure": "psi"},
        "rates": {"rate_mode": "tou"},
        "modules": {
            "spend_breakdown": True,
            "gas_savings": True,
            "solar_production": True,
            "driving_efficiency": False,
            "charge_limit_compliance": False,
            "work_mileage": False,
            "battery_health": True,
            "top_locations": False,
            "driving_milestones": False,
            "supercharger_explorer": False,
            "achievements": False,
            "maintenance_alerts": False,
            "vampire_drain": False,
        },
        "trips": {"total_miles": 100, "total_km": 160, "drives_count": 5, "total_duration_hours": 2, "avg_trip_miles": 20, "avg_trip_km": 32, "top_speed_mph": 75, "top_speed_kmh": 120, "elevation": {"ascent_ft": 0, "ascent_m": 0, "regen_kwh_recaptured": 0}, "top_places": []},
        "charging": {"total_spend": 25.0, "efficiency_pct": 95.0, "off_peak_spend": 20.0, "off_peak_kwh": 100.0, "shoulder_spend": 5.0, "shoulder_kwh": 20.0, "supercharger_spend": 0, "supercharger_kwh": 0, "off_peak_score_pct": 90.0, "gas_savings": {"net_savings": 50, "gas_spend_equivalent": 75}},
        "solar": {"has_data": True, "total_solar_kwh": 200.0, "solar_savings": 25.0, "solar_ev_coverage_pct": 80.0, "clean_miles_covered": 500, "grid_export_kwh": 50, "grid_import_kwh": 20, "peak_solar_kw": 5.5, "self_consumption_pct": 75.0, "home_charging_kwh": 120.0, "solar_surplus_kwh": 80.0},
        "compliance": {"hours_above_80": 0, "pct_above_80": 0, "hours_optimal": 100, "pct_optimal": 100, "hours_below_20": 0, "pct_below_20": 0, "compliance_score": 100, "compliance_rating": "Excellent", "stress_level": "Low"},
        "efficiency": {"avg_wh_per_mile": 260, "avg_wh_per_km": 161, "efficiency_pct": 96, "grade": "A+", "net_energy_kwh": 100, "total_drives": 5, "cars_breakdown": []},
        "work_mileage": {"has_routes": False, "routes": []},
        "show_battery_health": True,
        "battery": {
            "cars": [{
                "car_name": "Shadow",
                "model": "Y",
                "latest_odometer_mi": 12000,
                "capacity_retained_pct": 98.5,
                "health_grade": "A+",
                "health_color": "#10b981",
                "current_estimated_range_mi": 315,
                "factory_baseline_range_mi": 320,
                "degradation_pct": 1.5,
            }]
        },
        "superchargers": {"lifetime_unique_stations": 0, "month_sessions_count": 0, "new_stations_this_month": [], "recent_visits": []},
        "achievements": {"has_data": False, "total_unlocked": 0, "total_achievements": 0, "unlocked_pct": 0, "categories": [], "earned_this_period": [], "next_milestones": []},
        "health": {"cars": []},
        "vampire": {"total_idle_hours": 0, "estimated_loss_kwh": 0, "estimated_cost": 0},
        "chart_spend": "data:image/png;base64,SPEND_MOCK",
        "chart_tou": "data:image/png;base64,TOU_MOCK",
        "chart_solar": "data:image/png;base64,SOLAR_MOCK",
        "chart_battery": "data:image/png;base64,BATTERY_MOCK",
    }

    rendered = template.render(**mock_context)

    # Verify that all 4 charts are wrapped in .chart-container with 100% width
    assert rendered.count('class="chart-container"') >= 4
    assert 'width="100%" alt="Spend Breakdown"' in rendered
    assert 'width="100%" alt="24-Hour TOU Distribution"' in rendered
    assert 'width="100%" alt="Solar Generation vs EV Charging"' in rendered
    assert 'width="100%" alt="Battery Range Trend"' in rendered


def test_standardized_chart_dimensions_and_export():
    import io
    from PIL import Image
    from app.charts import (
        CHART_FIG_WIDTH,
        CHART_FIG_HEIGHT,
        CHART_DPI,
        CHART_SUBPLOT_ADJUST,
        generate_spend_chart,
        generate_tou_chart,
        generate_solar_chart,
        generate_battery_trend_chart,
        generate_tpms_diagram,
    )

    # Verify constants
    assert CHART_FIG_WIDTH == 8.0
    assert CHART_FIG_HEIGHT == 2.8
    assert CHART_DPI == 140
    expected_px_width = int(CHART_FIG_WIDTH * CHART_DPI)
    expected_px_height = int(CHART_FIG_HEIGHT * CHART_DPI)
    assert (expected_px_width, expected_px_height) == (1120, 392)

    # 1. Spend Chart
    spend_bytes = generate_spend_chart(
        {"off_peak_spend": 24.5, "shoulder_spend": 6.2, "peak_spend": 0.0, "supercharger_spend": 12.0},
        as_bytes=True,
    )
    img_spend = Image.open(io.BytesIO(spend_bytes))
    assert img_spend.size == (1120, 392)

    # 2. TOU Chart
    tou_bytes = generate_tou_chart([1.2] * 24, as_bytes=True)
    img_tou = Image.open(io.BytesIO(tou_bytes))
    assert img_tou.size == (1120, 392)

    # 3. Solar Chart
    solar_bytes = generate_solar_chart(
        {"daily_breakdown": [{"date": "2026-10-01", "kwh": 22.5}], "total_solar_kwh": 22.5, "peak_solar_kw": 6.8},
        as_bytes=True,
    )
    img_solar = Image.open(io.BytesIO(solar_bytes))
    assert img_solar.size == (1120, 392)

    # 4. Battery Trend Chart
    battery_bytes = generate_battery_trend_chart(
        {"cars": [{"car_name": "Model Y", "model": "Y", "trend_series": [{"month": "2026-09", "avg_range_mi": 310}, {"month": "2026-10", "avg_range_mi": 308}]}]},
        as_bytes=True,
    )
    img_battery = Image.open(io.BytesIO(battery_bytes))
    assert img_battery.size == (1120, 392)

    # 5. TPMS Diagram
    tpms_bytes = generate_tpms_diagram(
        {"fl_psi": 42.0, "fr_psi": 41.5, "rl_psi": 42.0, "rr_psi": 42.1},
        as_bytes=True,
    )
    img_tpms = Image.open(io.BytesIO(tpms_bytes))
    assert img_tpms.size == (1120, 392)


def test_digest_template_section_demarcations_and_inline_theming():
    env = get_jinja_env()
    template = env.get_template("digest.html")
    with open(template.filename, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Coherent Pillar Demarcation headers present
    assert "🚘 DRIVING &amp; ACTIVITY" in content
    assert "⚡ ENERGY &amp; CHARGING" in content
    assert "🛡️ HEALTH &amp; MAINTENANCE" in content
    assert "section-demarcation" in content
    assert "demarcation-badge" in content

    # 2. Resilient Inline Styles on critical outer elements to prevent theme loss in email clients
    assert '<body style="margin: 0; padding: 0; background-color: {{ theme.body_bg }}' in content
    assert '<center class="wrapper" style="width: 100%; table-layout: fixed; background-color: {{ theme.wrapper_bg }}' in content
    assert '<table role="presentation" class="main-table" cellpadding="0" cellspacing="0" style="width: 100%; max-width: 660px;' in content

    # 3. All cards have inline background, borders, and shadows
    assert 'class="card" style="background-color: {{ theme.card_bg }}' in content
    assert 'box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.16)' in content

    # 4. Mobile responsiveness includes generous spacing to avoid stuffiness
    assert ".content-td {\n        padding: 18px 14px 20px 14px !important;" in content or "padding: 18px 14px 20px 14px !important;" in content
    assert ".card {\n        padding: 18px 16px !important;\n        margin-bottom: 18px !important;" in content or "margin-bottom: 18px !important;" in content

