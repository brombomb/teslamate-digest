import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from jinja2 import Template

from app.services.homeassistant import verify_ha_connection, discover_ha_solar_entities, fetch_solar_summary
from app.charts import generate_solar_chart
from app.themes import get_theme


def test_verify_ha_connection_mocked():
    # Empty token returns error
    res_empty = asyncio.run(verify_ha_connection("http://localhost:8123", ""))
    assert res_empty["success"] is False
    assert "required" in res_empty["error"].lower()

    # Success case
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"message": "API running."}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = asyncio.run(verify_ha_connection("http://localhost:8123", "test_token"))
        assert res["success"] is True
        assert "Successfully connected" in res["message"]

    # 401 Unauthorized case
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp_401
        res_401 = asyncio.run(verify_ha_connection("http://localhost:8123", "bad_token"))
        assert res_401["success"] is False
        assert "Invalid" in res_401["error"]


def test_discover_ha_solar_entities_mocked():
    mock_states = [
        {"entity_id": "sensor.tesla_solar_production", "state": "17000", "attributes": {"friendly_name": "1AU Tesla Solar Production", "device_class": "energy", "unit_of_measurement": "kWh"}},
        {"entity_id": "sensor.1au_solar_power", "state": "1500", "attributes": {"friendly_name": "1AU Solar power", "device_class": "power", "unit_of_measurement": "W"}},
        {"entity_id": "sensor.current_grid_consumption", "state": "26000", "attributes": {"friendly_name": "Current Grid Consumption", "device_class": "energy", "unit_of_measurement": "kWh"}},
        {"entity_id": "sensor.current_grid_feed", "state": "7000", "attributes": {"friendly_name": "Current Grid Feed", "device_class": "energy", "unit_of_measurement": "kWh"}},
        {"entity_id": "sensor.total_load_energy", "state": "1500", "attributes": {"friendly_name": "Total Load Energy", "device_class": "energy", "unit_of_measurement": "kWh"}},
        {"entity_id": "light.living_room", "state": "on", "attributes": {}}
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_states

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        disc = asyncio.run(discover_ha_solar_entities("http://localhost:8123", "test_token"))
        assert disc["success"] is True
        assert disc["suggested"]["solar_energy_entity"] == "sensor.tesla_solar_production"
        assert disc["suggested"]["solar_power_entity"] == "sensor.1au_solar_power"
        assert disc["suggested"]["grid_import_entity"] == "sensor.current_grid_consumption"
        assert disc["suggested"]["grid_export_entity"] == "sensor.current_grid_feed"
        assert disc["suggested"]["home_load_entity"] == "sensor.total_load_energy"


def test_fetch_solar_summary_mocked():
    class MockConfig:
        enabled = True
        url = "http://localhost:8123"
        token = "test_token"
        solar_energy_entity = "sensor.tesla_solar_production"
        solar_power_entity = "sensor.1au_solar_power"
        grid_import_entity = "sensor.current_grid_consumption"
        grid_export_entity = "sensor.current_grid_feed"
        home_load_entity = "sensor.total_load_energy"

    # Minimal response series
    mock_history_payload = [
        [
            {"entity_id": "sensor.tesla_solar_production", "state": "16900.0", "last_updated": "2026-09-24T12:00:00+00:00"},
            {"entity_id": "sensor.tesla_solar_production", "state": "16950.0", "last_updated": "2026-09-24T18:00:00+00:00"},
            {"entity_id": "sensor.tesla_solar_production", "state": "17000.0", "last_updated": "2026-09-25T18:00:00+00:00"},
        ],
        [
            {"entity_id": "sensor.current_grid_consumption", "state": "25000.0"},
            {"entity_id": "sensor.current_grid_consumption", "state": "25150.0"},
        ],
        [
            {"entity_id": "sensor.current_grid_feed", "state": "7000.0"},
            {"entity_id": "sensor.current_grid_feed", "state": "7030.0"},
        ],
        [
            {"entity_id": "sensor.total_load_energy", "state": "1000.0"},
            {"entity_id": "sensor.total_load_energy", "state": "1220.0"},
        ],
        [
            {"entity_id": "sensor.1au_solar_power", "state": "2500.0"},
            {"entity_id": "sensor.1au_solar_power", "state": "5200.0"},
        ]
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_history_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        now = datetime.now(timezone.utc)
        summary = asyncio.run(fetch_solar_summary(
            MockConfig(),
            now - timedelta(days=7),
            now,
            home_charging_kwh=80.0,
            kwh_cost=0.13
        ))

        assert summary["has_data"] is True
        assert summary["total_solar_kwh"] == 100.0
        assert summary["grid_import_kwh"] == 150.0
        assert summary["grid_export_kwh"] == 30.0
        assert summary["home_load_kwh"] == 220.0
        assert summary["peak_solar_kw"] == 5.2
        assert summary["solar_ev_coverage_pct"] == 100.0
        assert summary["solar_surplus_kwh"] == 20.0
        assert summary["solar_savings"] == 13.0
        assert len(summary["daily_breakdown"]) == 2


def test_generate_solar_chart_output():
    solar_sample = {
        "has_data": True,
        "total_solar_kwh": 153.0,
        "peak_solar_kw": 5.4,
        "daily_breakdown": [
            {"date": "2026-09-24", "kwh": 20.4},
            {"date": "2026-09-25", "kwh": 20.1},
            {"date": "2026-09-26", "kwh": 33.6},
            {"date": "2026-09-27", "kwh": 33.2},
            {"date": "2026-09-28", "kwh": 14.4},
            {"date": "2026-09-29", "kwh": 21.5},
            {"date": "2026-09-30", "kwh": 9.1},
        ]
    }
    b = generate_solar_chart(solar_sample, theme=get_theme("pearl_white"), as_bytes=True)
    assert isinstance(b, bytes)
    assert len(b) > 500  # valid PNG bytes


def test_email_template_renders_solar_module():
    tmpl_path = Path(__file__).resolve().parent.parent / "app" / "templates" / "email" / "digest.html"
    if not tmpl_path.exists():
        tmpl_path = Path("/app/app/templates/email/digest.html")

    from app.config import RatesSettings

    with open(tmpl_path, "r") as f:
        tmpl = Template(f.read())

    rendered = tmpl.render(
        report_title="Weekly Tesla Digest",
        date_subtitle="Jan 1 - Jan 7, 2026",
        car_subtitle="Model Y",
        car_id=1,
        dashboard_url="http://localhost:8660",
        teslamate_url="http://192.168.1.15:4000",
        grafana_url="http://192.168.1.15:3000",
        homeassistant_url="http://192.168.1.15:8123",
        theme=get_theme("pearl_white"),
        rates=RatesSettings(),
        trips={"total_miles": 250, "avg_wh_per_mile": 270, "drives_count": 15, "total_duration_hours": 12, "avg_trip_miles": 18, "top_speed_mph": 75, "elevation": {"ascent_ft": 2000, "regen_kwh_recaptured": 4.5}, "longest_drive": None, "top_places": []},
        efficiency={"avg_wh_per_mile": 270, "avg_wh_per_km": 168, "efficiency_pct": 94, "grade": "A", "net_energy_kwh": 120, "total_drives": 15, "cars_breakdown": []},
        compliance={"hours_above_80": 1, "pct_above_80": 2, "hours_optimal": 90, "pct_optimal": 95, "hours_below_20": 2, "pct_below_20": 3, "compliance_score": 96, "compliance_rating": "Optimal", "stress_level": "Low"},
        battery={"cars": []},
        health={"cars": []},
        vampire={"total_idle_hours": 150, "estimated_loss_kwh": 12.5, "estimated_cost": 1.62},
        superchargers={"lifetime_unique_stations": 8, "month_sessions_count": 2, "new_stations_this_month": [], "recent_visits": []},
        modules={
            "spend_breakdown": True,
            "solar_production": True,
            "driving_efficiency": False,
            "battery_health": False,
            "charge_limit_compliance": False,
            "work_mileage": False,
            "top_locations": False,
            "supercharger_explorer": False,
            "maintenance_alerts": False,
            "vampire_drain": False,
            "gas_savings": False
        },
        charging={
            "total_spend": 10.0,
            "total_energy_used_kwh": 80,
            "home_kwh": 80,
            "home_spend": 10.0,
            "off_peak_spend": 10.0,
            "off_peak_kwh": 80,
            "shoulder_spend": 0.0,
            "shoulder_kwh": 0,
            "on_peak_spend": 0.0,
            "on_peak_kwh": 0,
            "supercharger_spend": 0.0,
            "supercharger_kwh": 0,
            "gas_savings": {"net_savings": 20.0, "gas_spend_equivalent": 30.0},
            "cars_breakdown": []
        },
        solar={
            "has_data": True,
            "total_solar_kwh": 153.0,
            "home_charging_kwh": 80.0,
            "solar_ev_coverage_pct": 100.0,
            "clean_miles_covered": 296.0,
            "solar_surplus_kwh": 73.0,
            "solar_savings": 19.89,
            "grid_import_kwh": 345.0,
            "grid_export_kwh": 75.0,
            "peak_solar_kw": 5.4,
            "self_consumption_pct": 51.0
        },
        chart_solar="cid:chart_solar"
    )

    assert "Solar Production &amp; Clean Charging" in rendered
    assert "153.0" in rendered
    assert "100%" in rendered
    assert "296.0 clean mi" in rendered
    assert "$19.89 value" in rendered
    assert "cid:chart_solar" in rendered
    assert "http://192.168.1.15:8123/energy" in rendered
