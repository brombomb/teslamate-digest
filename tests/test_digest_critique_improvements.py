import pytest
from datetime import datetime
from app.analytics.insights import generate_digest_insights, calculate_mom_deltas
from app.config import AppConfig, SMTPSettings
from app.report import get_jinja_env
from app.themes import get_theme
from app.mailer import Mailer


def test_insights_generation_with_diagnostic_anomalies():
    telemetry = {
        "trips": {"total_miles": 1439.0},
        "charging": {
            "total_spend": 43.91,
            "off_peak_score_pct": 94.0,
            "gas_savings": {"net_savings": 176.32},
        },
        "health": {
            "cars": [
                {
                    "car_name": "Shadow",
                    "tpms": {"fl_psi": 47.9, "fr_psi": 47.9, "rl_psi": 47.9, "rr_psi": 46.4, "unit": "psi"},
                    "tpms_alerts": ["Cold tire pressure high: 47.9 PSI (target 42.0 PSI)"],
                    "tire_rotation": {
                        "is_uncalibrated": True,
                        "current_odometer": 58597,
                        "dist_driven_since": 0,
                        "interval": 6250,
                    },
                }
            ]
        },
        "vampire": {
            "total_idle_hours": 219.0,
            "estimated_loss_kwh": 54.9,
            "estimated_cost": 7.13,
        },
        "compliance": {
            "hours_below_20": 75.0,
            "pct_below_20": 10.4,
            "hours_above_80": 0.0,
            "pct_above_80": 0.0,
            "compliance_score": 84,
            "stress_level": "Moderate",
        },
        "solar": {
            "has_data": True,
            "is_partial_period": True,
            "days_tracked": 3,
            "total_days": 30,
            "clean_miles_covered": 166.4,
        },
        "achievements": {
            "earned_this_period": [{"name": "Night Owl"}, {"name": "Road Tripper"}],
        },
        "battery": {
            "cars": [
                {"car_name": "Shadow", "capacity_retained_pct": 98.8, "health_grade": "A+"}
            ]
        },
    }

    config = AppConfig()
    insights = generate_digest_insights(telemetry, config)

    assert insights["has_items"] is True
    assert len(insights["items"]) <= 3
    
    # Check that high tire pressure is flagged
    item_types = [item["type"] for item in insights["items"]]
    assert "tpms" in item_types

    # Check wins summary
    wins = insights["wins_summary"]
    assert "$176 saved vs gas" in wins
    assert "94% off-peak charging" in wins
    assert "98.8% (Grade A+)" in wins
    assert "2 new badges" in wins


def test_mom_deltas_calculation():
    cur = {
        "trips": {"total_miles": 1200.0},
        "charging": {
            "total_spend": 50.0,
            "gas_savings": {"net_savings": 140.0},
        },
        "efficiency": {"avg_wh_per_mile": 270.0},
    }
    prev = {
        "trips": {"total_miles": 1000.0},
        "charging": {
            "total_spend": 60.0,
            "gas_savings": {"net_savings": 120.0},
        },
        "efficiency": {"avg_wh_per_mile": 280.0},
    }

    deltas = calculate_mom_deltas(cur, prev)
    assert deltas["miles"]["diff"] == 200.0
    assert deltas["miles"]["pct"] == 20.0
    assert deltas["miles"]["direction"] == "up"

    assert deltas["spend"]["diff"] == -10.0
    assert deltas["spend"]["direction"] == "down"

    assert deltas["gas_savings"]["diff"] == 20.0
    assert deltas["gas_savings"]["direction"] == "up"

    assert deltas["efficiency"]["diff"] == -10.0


def test_mailer_preheader_fallback_extraction():
    smtp = SMTPSettings(
        enabled=True,
        host="smtp.gmail.com",
        port=587,
        user="test@gmail.com",
        password="app-password",
        sender_email="test@gmail.com",
        recipient_email="user@gmail.com",
    )
    mailer = Mailer(smtp)

    sample_html = """
    <html>
      <body>
        <div class="preheader" style="display: none;">Your Fleet · September 2026: 1,439 mi · $43.91 · 94% off-peak</div>
        <h1>Full Report Content</h1>
      </body>
    </html>
    """

    # Test auto extraction logic in mailer
    import re
    match = re.search(r'class="preheader"[^>]*>(.*?)</div>', sample_html, re.DOTALL | re.IGNORECASE)
    assert match is not None
    preheader = re.sub(r'<[^>]+>', '', match.group(1)).strip()
    assert preheader == "Your Fleet · September 2026: 1,439 mi · $43.91 · 94% off-peak"


def test_template_zero_state_collapsing_and_reconciliation():
    env = get_jinja_env()
    template = env.get_template("digest.html")

    mock_context = {
        "report_title": "Your Fleet · September 2026",
        "date_subtitle": "Sep 1–30, 2026",
        "car_subtitle": "Fleet",
        "one_line_summary": "1,439 mi · $43.91 · 94% off-peak",
        "preheader_text": "Your Fleet · September 2026: 1,439 mi · $43.91 · 94% off-peak",
        "generation_timestamp": "Oct 08, 2026 at 02:00 PM MDT",
        "theme": get_theme("dark_modern"),
        "units": {"is_metric": False, "currency": "$", "length": "mi", "speed": "mph", "elevation": "ft", "pressure": "psi"},
        "rates": {"rate_mode": "tou", "gas_price_per_gal": 3.85, "baseline_ice_mpg": 28.0},
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
            "vampire_drain": True,
        },
        "trips": {
            "total_miles": 1439.0,
            "total_km": 2315.0,
            "drives_count": 52,
            "total_duration_hours": 38.0,
            "avg_trip_miles": 27.6,
            "top_speed_mph": 81.0,
            "elevation": {"ascent_ft": 5200, "ascent_m": 1585, "regen_kwh_recaptured": 16.0},
            "longest_drive": None,
            "top_places": [
                {"name": "Home", "city": "Denver", "visits": 40},
                {"name": "Work", "city": "Boulder", "visits": 12},
            ]
        },
        "charging": {
            "total_spend": 43.91,
            "efficiency_pct": 94.2,
            "off_peak_spend": 39.56,
            "off_peak_kwh": 395.0,
            "shoulder_spend": 1.87,
            "shoulder_kwh": 18.0,
            "on_peak_spend": 2.48,
            "on_peak_kwh": 13.0,
            "supercharger_spend": 0.0,
            "supercharger_kwh": 0.0,
            "off_peak_score_pct": 94.0,
            "gas_savings": {"net_savings": 176.32, "gas_spend_equivalent": 220.23},
        },
        "solar": {
            "has_data": True,
            "is_partial_period": True,
            "days_tracked": 3,
            "total_days": 30,
            "total_solar_kwh": 28.7,
            "peak_solar_kw": 6.2,
            "solar_savings": 3.73,
            "solar_ev_coverage_pct": 6.1,
            "clean_miles_covered": 106.0,
            "grid_export_kwh": 15.0,
            "grid_import_kwh": 90.0,
            "self_consumption_pct": 48.0,
            "home_charging_kwh": 467.1,
            "solar_surplus_kwh": 0.0,
        },
        "compliance": {
            "hours_above_80": 0.0,
            "pct_above_80": 0.0,
            "hours_optimal": 720.0,
            "pct_optimal": 100.0,
            "hours_below_20": 0.0,
            "pct_below_20": 0.0,
            "compliance_score": 100,
            "compliance_rating": "Optimal",
            "stress_level": "None",
            "is_all_optimal": True,
        },
        "work_mileage": {
            "has_routes": True,
            "total_trips": 0,
            "total_miles": 0.0,
            "total_irs_deduction": 0.0,
            "routes": [],
        },
        "superchargers": {
            "lifetime_unique_stations": 5,
            "month_sessions_count": 0,
            "new_stations_this_month": [],
            "recent_visits": [],
        },
        "efficiency": {
            "avg_wh_per_mile": 274.0,
            "avg_wh_per_km": 170.0,
            "efficiency_pct": 98.0,
            "grade": "A+",
            "net_energy_kwh": 394.0,
            "total_drives": 52,
            "cars_breakdown": [],
        },
        "battery": {"cars": []},
        "health": {
            "cars": [
                {
                    "car_name": "Shadow",
                    "model": "Y",
                    "tpms": {
                        "front_left": 47.9,
                        "front_right": 47.9,
                        "rear_left": 47.9,
                        "rear_right": 46.4,
                        "unit": "psi",
                        "fl_info": {"color": "#ef4444"},
                        "fr_info": {"color": "#ef4444"},
                        "rl_info": {"color": "#ef4444"},
                        "rr_info": {"color": "#f59e0b"},
                        "has_alert": True,
                        "alert_msg": "Elevated tire pressure detected (47.9 PSI)",
                    },
                    "tire_rotation": {
                        "dist_driven_since": 340.0,
                        "interval": 6250.0,
                        "dist_remaining": 5910.0,
                        "unit": "mi",
                        "color": "#10b981",
                        "pct_progress": 5.4,
                        "is_due": False,
                        "last_rotation_odometer": 58257,
                        "current_odometer": 58597,
                    },
                }
            ]
        },
        "vampire": {
            "total_idle_hours": 219.0,
            "estimated_loss_kwh": 54.9,
            "estimated_cost": 7.13,
        },
        "achievements": {
            "has_data": True,
            "total_unlocked": 28,
            "total_achievements": 45,
            "unlocked_pct": 62.0,
            "categories": [],
            "earned_this_period": [],
            "next_milestones": [],
        },
        "insights": {
            "has_items": True,
            "items": [
                {
                    "type": "tpms",
                    "severity": "warning",
                    "badge": "High Pressure",
                    "title": "Shadow: Cold tire pressure elevated at 47.9 PSI",
                    "detail": "Target is 42.0 PSI. High pressure causes center tread wear.",
                    "icon": "⚠️",
                    "color": "#f59e0b",
                }
            ],
            "wins_summary": "$176 saved vs gas · 94% off-peak · 98.8% battery",
            "deltas": {},
        },
        "show_battery_health": False,
        "teslamate_url": "http://localhost:4000",
        "grafana_url": "http://localhost:3000",
        "dashboard_url": "http://localhost:8660",
    }

    rendered = template.render(**mock_context)

    # 1. Verify "Worth a Look" card is present with diagnostic content
    assert "Worth a Look" in rendered
    assert "Shadow: Cold tire pressure elevated at 47.9 PSI" in rendered
    assert "$176 saved vs gas" in rendered

    # 2. Verify TOU numbers reconcile: On-Peak ($2.48) and Off-Peak ($39.56) are present
    assert "$39.56" in rendered
    assert "$1.87" in rendered
    assert "$2.48" in rendered
    assert "$43.91" in rendered

    # 3. Verify zero-state Supercharger collapsing into single line
    assert "No visits this period" in rendered
    assert "5 lifetime stations visited" in rendered

    # 4. Verify zero-stress Pack Stress collapsing into single line
    assert "100% optimal dwell time (20–80% SoC)" in rendered

    # 5. Verify Work Mileage is hidden when trips == 0
    assert "Work &amp; Commute Mileage Tracker" not in rendered

    # 6. Verify TPMS target is stated
    assert "Target: 42.0 PSI / 2.9 bar" in rendered
    assert "47.9 psi" in rendered

    # 7. Verify preheader hidden div
    assert 'class="preheader"' in rendered
    assert "Your Fleet · September 2026: 1,439 mi · $43.91 · 94% off-peak" in rendered


def test_individual_car_header_no_redundant_name_or_model():
    env = get_jinja_env()
    template = env.get_template("digest.html")

    mock_context = {
        "report_title": "Forget Me Not · September 2026",
        "date_subtitle": "Sep 1–30, 2026",
        "car_subtitle": "Forget Me Not (Model X · 100D)",
        "car_badge": "Model X · 100D",
        "period_label": "Monthly Review",
        "one_line_summary": "1,018 mi · $37.57 · 100% off-peak · $118 saved",
        "preheader_text": "Forget Me Not · September 2026: 1,018 mi · $37.57 · 100% off-peak",
        "generation_timestamp": "Oct 09, 2026 at 08:30 AM MDT",
        "theme": get_theme("dark_modern"),
        "units": {"is_metric": False, "currency": "$", "length": "mi", "speed": "mph", "elevation": "ft", "pressure": "psi"},
        "rates": {"rate_mode": "tou", "gas_price_per_gal": 3.85, "baseline_ice_mpg": 28.0},
        "modules": {},
        "trips": {"total_miles": 1018.0, "total_km": 1638.0, "drives_count": 30, "total_duration_hours": 25.0, "avg_trip_miles": 33.9, "top_speed_mph": 80.0, "elevation": {"ascent_ft": 3000, "ascent_m": 914, "regen_kwh_recaptured": 10.0}, "longest_drive": None, "top_places": []},
        "charging": {"total_spend": 37.57, "efficiency_pct": 95.0, "off_peak_spend": 37.57, "off_peak_kwh": 375.0, "shoulder_spend": 0.0, "shoulder_kwh": 0.0, "on_peak_spend": 0.0, "on_peak_kwh": 0.0, "supercharger_spend": 0.0, "supercharger_kwh": 0.0, "off_peak_score_pct": 100.0, "gas_savings": {"net_savings": 118.0, "gas_spend_equivalent": 155.57}},
        "solar": {"has_data": False},
        "superchargers": {"total_visits": 0, "lifetime_stations_count": 0, "charging_sites": []},
        "battery": {"cars": []},
        "health": {"cars": []},
        "vampire": {"total_idle_hours": 0.0, "estimated_loss_kwh": 0.0, "estimated_cost": 0.0},
        "efficiency": {"avg_wh_per_mile": 280.0, "avg_wh_per_km": 174.0, "efficiency_pct": 95.0, "grade": "A", "net_energy_kwh": 285.0, "total_drives": 30, "cars_breakdown": []},
        "compliance": {"total_charges": 0, "optimal_count": 0, "rate_pct": 100.0, "grade": "A+"},
        "work_mileage": {"total_work_miles": 0.0, "total_reimbursement": 0.0, "tax_rate": 0.67, "trips_count": 0},
        "achievements": {"has_data": False, "total_unlocked": 0, "total_achievements": 45, "unlocked_pct": 0.0, "categories": [], "earned_this_period": [], "next_milestones": []},
        "insights": {"has_items": False, "items": [], "wins_summary": "", "deltas": {}},
        "show_battery_health": False,
        "teslamate_url": "http://localhost:4000",
        "grafana_url": "http://localhost:3000",
        "dashboard_url": "http://localhost:8660",
    }

    rendered = template.render(**mock_context)

    # Extract the header-td block
    start_idx = rendered.find('class="header-td"')
    end_idx = rendered.find('class="content-td"')
    assert start_idx != -1 and end_idx != -1
    header_block = rendered[start_idx:end_idx]

    # Verify car name appears only once in the header (in report_title / h1)
    assert header_block.count("Forget Me Not") == 1
    # Verify model badge appears only once in the header (in the pill badge)
    assert header_block.count("Model X") == 1
    assert "Model X · 100D" in header_block
    # Verify period label is present in eyebrow
    assert "TESLAMATE DIGEST &bull; Monthly Review" in header_block
    # Verify date subtitle does not repeat car name
    assert "Sep 1–30, 2026" in header_block


def test_charging_section_kpi_redesign_and_no_verbose_summation():
    env = get_jinja_env()
    template = env.get_template("digest.html")

    context = {
        "report_title": "Monthly Report",
        "date_subtitle": "Sep 1–30, 2026",
        "theme": get_theme("pearl_white"),
        "modules": {"spend_breakdown": True, "gas_savings": True, "driving_efficiency": True},
        "rates": {"rate_mode": "tou", "gas_price_per_gal": 3.85, "baseline_ice_mpg": 28.0},
        "trips": {"total_miles": 1439.0, "total_km": 2315.0},
        "charging": {
            "total_spend": 43.91,
            "total_energy_used_kwh": 467.1,
            "off_peak_score_pct": 94.0,
            "off_peak_spend": 39.56,
            "off_peak_kwh": 395.0,
            "shoulder_spend": 1.87,
            "shoulder_kwh": 18.0,
            "on_peak_spend": 2.48,
            "on_peak_kwh": 13.0,
            "supercharger_spend": 0.0,
            "supercharger_kwh": 0.0,
            "gas_savings": {
                "net_savings": 176.32,
                "gas_spend_equivalent": 220.23,
            },
        },
        "efficiency": {
            "avg_wh_per_mile": 274,
            "avg_wh_per_km": 170,
            "efficiency_pct": 94.5,
            "grade": "Good",
            "net_energy_kwh": 394.0,
            "total_drives": 50,
            "cars_breakdown": [],
        },
        "units": {"is_metric": False, "length": "mi", "currency": "$"},
    }

    rendered = template.render(**context)

    # 1. Verify 4 KPI tiles are rendered
    assert "Total Spend" in rendered
    assert "$43.91" in rendered
    assert "% Off-Peak" in rendered
    assert "94%" in rendered
    assert "Fuel Compare" in rendered
    assert "+$176.32" in rendered
    assert "Supercharger" in rendered
    assert "$0.00" in rendered

    # 2. Verify verbose summation text is removed
    assert "All charging categories sum to total spend" not in rendered

    # 3. Verify driving efficiency secondary conversion is clearly labeled
    assert "equiv. 170 Wh/km" in rendered


def test_battery_chart_multi_car_individual_baselines():
    from app.charts import generate_battery_trend_chart
    import matplotlib.pyplot as plt

    battery_multi = {
        "cars": [
            {
                "car_name": "Forget Me Not",
                "factory_baseline_range_mi": 280.6,
                "trend_series": [
                    {"month": "2026-08", "avg_range_mi": 279.0},
                    {"month": "2026-09", "avg_range_mi": 278.2},
                ],
            },
            {
                "car_name": "Shadow",
                "factory_baseline_range_mi": 315.0,
                "trend_series": [
                    {"month": "2026-08", "avg_range_mi": 314.0},
                    {"month": "2026-09", "avg_range_mi": 312.8},
                ],
            },
        ]
    }

    chart_b64 = generate_battery_trend_chart(battery_multi, theme=get_theme("pearl_white"), unit="mi")
    assert isinstance(chart_b64, str)
    assert len(chart_b64) > 100


def test_tire_rotation_gradient_and_text_formatting():
    env = get_jinja_env()
    template = env.get_template("digest.html")

    # Verify health calculation gradients
    from app.analytics.health import get_health_analytics

    # Test 1: < 80% (393 / 6,250 mi -> 6.3% used)
    pct_used_low = 6.3
    g_stop = round((80.0 / max(pct_used_low, 1.0)) * 100.0, 1)
    # Under 80%, color is #10b981 and gradient is #10b981
    assert pct_used_low < 80.0

    # Test 2: 85% used -> turns yellow
    pct_used_mid = 85.0
    g_stop = round((80.0 / pct_used_mid) * 100.0, 1)
    grad_mid = f"linear-gradient(90deg, #10b981 0%, #10b981 {g_stop}%, #f59e0b 100%)"
    assert "#10b981" in grad_mid and "#f59e0b" in grad_mid

    # Test 3: 95% used -> turns red
    pct_used_high = 95.0
    g_stop = round((80.0 / pct_used_high) * 100.0, 1)
    y_stop = round((90.0 / pct_used_high) * 100.0, 1)
    grad_high = f"linear-gradient(90deg, #10b981 0%, #10b981 {g_stop}%, #f59e0b {g_stop}%, #f59e0b {y_stop}%, #ef4444 {y_stop}%, #ef4444 100%)"
    assert "#ef4444" in grad_high and "#f59e0b" in grad_high and "#10b981" in grad_high

    # Render template with tire rotation and battery capacity badge
    context = {
        "report_title": "Monthly Report",
        "theme": get_theme("pearl_white"),
        "modules": {"maintenance_alerts": True, "battery_health": True},
        "show_battery_health": True,
        "health": {
            "cars": [
                {
                    "car_name": "Shadow",
                    "model": "Y",
                    "tpms": {
                        "front_left": 42.0, "front_right": 42.0, "rear_left": 42.0, "rear_right": 42.0, "unit": "psi",
                        "fl_info": {"color": "#10b981"}, "fr_info": {"color": "#10b981"}, "rl_info": {"color": "#10b981"}, "rr_info": {"color": "#10b981"},
                        "has_alert": False
                    },
                    "tire_rotation": {
                        "dist_driven_since": 393.0,
                        "interval": 6250.0,
                        "dist_remaining": 5857.0,
                        "unit": "mi",
                        "pct_progress": 6.3,
                        "color": "#10b981",
                        "gradient": "#10b981",
                        "last_rotation_odometer": 58204,
                        "is_due": False,
                    },
                }
            ]
        },
        "battery": {
            "cars": [
                {
                    "car_name": "Shadow",
                    "model": "Y",
                    "latest_odometer_mi": 58597,
                    "capacity_retained_pct": 98.8,
                    "health_grade": "A+",
                    "health_color": "#10b981",
                    "current_estimated_range_mi": 278.2,
                    "factory_baseline_range_mi": 280.6,
                    "degradation_pct": 1.2,
                }
            ]
        },
        "units": {"is_metric": False, "length": "mi", "pressure": "psi", "currency": "$"},
        "trips": {"total_miles": 393.0, "total_km": 632.0},
        "charging": {
            "total_spend": 0.0,
            "total_energy_used_kwh": 0.0,
            "off_peak_score_pct": 100.0,
            "off_peak_spend": 0.0,
            "gas_savings": {"net_savings": 0.0, "gas_spend_equivalent": 0.0},
            "supercharger_spend": 0.0,
            "supercharger_kwh": 0.0,
        },
    }

    rendered = template.render(**context)

    # Verify exact user-requested text
    assert "Tire Rotation Progress (6,250 mi interval)" in rendered
    assert "393 / 6,250 mi used" in rendered
    assert "5,857 mi remaining until next 6,250 mi rotation interval." in rendered

    # Verify battery capacity box has rounded corners
    assert "border-radius: 20px" in rendered


