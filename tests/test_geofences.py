import pytest
from app.config import GeofenceItem, AppConfig, load_config, save_config
from app.services.geofences import haversine_distance_m, matches_location_point


def test_haversine_distance():
    # Identical points
    assert haversine_distance_m(39.8535, -105.1493, 39.8535, -105.1493) == pytest.approx(0.0, abs=1e-3)
    
    # Missing coordinates
    assert haversine_distance_m(None, -105.1493, 39.8535, -105.1493) == float("inf")
    assert haversine_distance_m(39.8535, None, 39.8535, -105.1493) == float("inf")
    
    # Approx 100 meters north
    dist = haversine_distance_m(39.85350, -105.1493, 39.85440, -105.1493)
    assert 90.0 < dist < 110.0


def test_geofence_item_alias_parsing():
    # Comma-separated string
    g1 = GeofenceItem(
        name="Home",
        latitude=39.8536,
        longitude=-105.1497,
        radius_meters=350,
        address_aliases="Main Street, Elm Street, Oak Avenue"
    )
    assert g1.address_aliases == ["Main Street", "Elm Street", "Oak Avenue"]

    # List of strings
    g2 = GeofenceItem(
        name="Work",
        latitude=39.7564,
        longitude=-105.2214,
        radius_meters=400,
        address_aliases=["Jackson St", " 11th St "]
    )
    assert g2.address_aliases == ["Jackson St", "11th St"]


def test_matches_location_point_by_geofence_radius():
    home_geo = GeofenceItem(
        name="Home",
        latitude=39.8536,
        longitude=-105.1497,
        radius_meters=350,
        address_aliases=["87th Terrace"]
    )
    geofences = [home_geo]

    # Inside geofence radius (approx 100m away)
    matched = matches_location_point(
        target="Home",
        drive_lat=39.8540,
        drive_lon=-105.1495,
        drive_name="Random Street",
        drive_city="City",
        geofences=geofences
    )
    assert matched is True

    # Far away (e.g. 10km away)
    unmatched = matches_location_point(
        target="Home",
        drive_lat=39.7564,
        drive_lon=-105.2214,
        drive_name="Random Street",
        drive_city="City",
        geofences=geofences
    )
    assert unmatched is False


def test_matches_location_point_by_geofence_alias():
    work_geo = GeofenceItem(
        name="Office",
        latitude=39.7564,
        longitude=-105.2214,
        radius_meters=400,
        address_aliases=["11th Street", "Jackson Street", "Prospector's Alley"]
    )
    geofences = [work_geo]

    # Target is "Office", drive ended at "Jackson Street" even without GPS
    matched = matches_location_point(
        target="Office",
        drive_lat=None,
        drive_lon=None,
        drive_name="Jackson Street",
        drive_city="Town",
        geofences=geofences
    )
    assert matched is True

    # Target is "11th Street", drive has GPS inside Office geofence
    matched2 = matches_location_point(
        target="11th Street",
        drive_lat=39.7562,
        drive_lon=-105.2207,
        drive_name="Prospector's Alley",
        drive_city="Town",
        geofences=geofences
    )
    assert matched2 is True


def test_matches_location_point_by_address_cache():
    addr_cache = {
        "elm street": (39.8000, -105.1000),
        "elm street city": (39.8000, -105.1000)
    }

    # Drive parked 50m from Elm Street
    matched = matches_location_point(
        target="Elm Street",
        drive_lat=39.8003,
        drive_lon=-105.1002,
        drive_name="Oak Court",
        drive_city="City",
        geofences=[],
        addr_cache=addr_cache
    )
    assert matched is True

    # Drive parked 2km from Elm Street
    unmatched = matches_location_point(
        target="Elm Street",
        drive_lat=39.8200,
        drive_lon=-105.1000,
        drive_name="Oak Court",
        drive_city="City",
        geofences=[],
        addr_cache=addr_cache
    )
    assert unmatched is False


def test_geofences_config_roundtrip():
    cfg = load_config()
    orig_geofences = cfg.geofences

    test_geo = GeofenceItem(
        name="Test Area",
        latitude=40.0,
        longitude=-105.0,
        radius_meters=500,
        address_aliases=["Street A", "Street B"]
    )
    cfg.geofences = [test_geo]
    save_config(cfg)

    reloaded = load_config()
    assert len(reloaded.geofences) == 1
    assert reloaded.geofences[0].name == "Test Area"
    assert reloaded.geofences[0].latitude == 40.0
    assert reloaded.geofences[0].longitude == -105.0
    assert reloaded.geofences[0].radius_meters == 500
    assert reloaded.geofences[0].address_aliases == ["Street A", "Street B"]

    # Restore
    cfg.geofences = orig_geofences
    save_config(cfg)


def test_get_grafana_dashboard_urls():
    from app.services.geofences import get_grafana_dashboard_urls

    # Without car_id
    urls = get_grafana_dashboard_urls("http://192.168.1.15:3000")
    assert urls["grafana_charging_url"] == "http://192.168.1.15:3000/d/-pkIkhmRz/charging-stats"
    assert urls["grafana_efficiency_url"] == "http://192.168.1.15:3000/d/fu4SiQgWz/efficiency"
    assert urls["grafana_battery_url"] == "http://192.168.1.15:3000/d/jchmRiqUfXgTM/battery-health"
    assert urls["grafana_drives_url"] == "http://192.168.1.15:3000/d/Y8upc6ZRk/drives"
    assert urls["grafana_charges_url"] == "http://192.168.1.15:3000/d/TSmNYvRRk/charges"
    assert urls["grafana_vampire_url"] == "http://192.168.1.15:3000/d/zhHx2Fggk/vampire-drain"

    # With car_id
    urls_car = get_grafana_dashboard_urls("http://192.168.1.15:3000/", car_id=2)
    assert urls_car["grafana_charging_url"] == "http://192.168.1.15:3000/d/-pkIkhmRz/charging-stats?var-car_id=2"
    assert urls_car["grafana_battery_url"] == "http://192.168.1.15:3000/d/jchmRiqUfXgTM/battery-health?var-car_id=2"


@pytest.mark.anyio
async def test_get_effective_service_urls():
    from app.services.geofences import get_effective_service_urls
    from unittest.mock import AsyncMock

    mock_db = AsyncMock()
    mock_db.fetchrow.return_value = {
        "base_url": "http://192.168.1.50:4000",
        "grafana_url": "http://192.168.1.50:3000"
    }

    # Unconfigured AppConfig should auto-detect from settings table
    cfg = AppConfig()
    cfg.teslamate_url = ""
    cfg.grafana_url = ""
    tm_url, graf_url = await get_effective_service_urls(mock_db, cfg)
    assert tm_url == "http://192.168.1.50:4000"
    assert graf_url == "http://192.168.1.50:3000"

    # Explicitly configured should take precedence
    cfg.teslamate_url = "https://custom-tm.local"
    cfg.grafana_url = "https://custom-graf.local"
    tm_url2, graf_url2 = await get_effective_service_urls(mock_db, cfg)
    assert tm_url2 == "https://custom-tm.local"
    assert graf_url2 == "https://custom-graf.local"


@pytest.mark.anyio
async def test_sync_geofences_with_teslamate():
    from app.services.geofences import sync_geofences_with_teslamate
    from unittest.mock import AsyncMock

    mock_db = AsyncMock()
    # Mock existing rows in PostgreSQL
    mock_db.fetch.return_value = [
        {"id": 1, "name": "Work", "latitude": 39.7564, "longitude": -105.2214, "radius": 400.0},
        {"id": 2, "name": "Supercharger", "latitude": 39.8000, "longitude": -105.1000, "radius": 150.0}
    ]
    mock_db.fetchrow.return_value = None
    mock_db.fetchval.return_value = 3

    cfg = AppConfig()
    cfg.geofences = [
        GeofenceItem(name="Work", latitude=0, longitude=0, radius_meters=450),
        GeofenceItem(name="Home", latitude=39.8536, longitude=-105.1497, radius_meters=350)
    ]

    geos, stats = await sync_geofences_with_teslamate(mock_db, cfg)
    assert stats["imported_from_teslamate"] == 1  # "Supercharger" imported
    assert stats["exported_to_teslamate"] == 1    # "Home" exported
    assert stats["updated"] == 1                  # "Work" coordinates updated from TeslaMate

    names = [g.name for g in geos]
    assert "Home" in names
    assert "Work" in names
    assert "Supercharger" in names
    for g in geos:
        assert g.in_teslamate is True


def test_email_template_grafana_and_teslamate_links():
    from pathlib import Path
    from jinja2 import Template
    from app.services.geofences import get_grafana_dashboard_urls
    from app.themes import get_theme
    from app.config import RatesSettings

    tmpl_path = Path(__file__).resolve().parent.parent / "app" / "templates" / "email" / "digest.html"
    if not tmpl_path.exists():
        tmpl_path = Path("/app/app/templates/email/digest.html")
    
    with open(tmpl_path, "r") as f:
        tmpl = Template(f.read())

    dashboards = get_grafana_dashboard_urls("http://192.168.1.15:3000", car_id=1)
    
    rendered = tmpl.render(
        report_title="Weekly Tesla Digest",
        date_subtitle="Jan 1 - Jan 7, 2026",
        car_subtitle="Model Y",
        car_id=1,
        dashboard_url="http://localhost:8660",
        teslamate_url="http://192.168.1.15:4000",
        grafana_url="http://192.168.1.15:3000",
        rates=RatesSettings(),
        theme=get_theme("pearl_white"),
        modules={
            "spend_breakdown": True,
            "driving_efficiency": True,
            "battery_health": True,
            "charge_limit_compliance": True,
            "work_mileage": False,
            "top_locations": True,
            "supercharger_explorer": True,
            "maintenance_alerts": True,
            "vampire_drain": True,
        },
        efficiency={"avg_wh_per_mile": 270, "avg_wh_per_km": 168, "efficiency_pct": 94, "grade": "A", "net_energy_kwh": 120, "total_drives": 15, "cars_breakdown": []},
        compliance={"hours_above_80": 1, "pct_above_80": 2, "hours_optimal": 90, "pct_optimal": 95, "hours_below_20": 2, "pct_below_20": 3, "compliance_score": 96, "compliance_rating": "Optimal", "stress_level": "Low"},
        battery={"cars": [{"car_name": "Model Y", "model": "Y", "latest_odometer_mi": 15000, "capacity_retained_pct": 98.2, "health_grade": "A+", "health_color": "#10b981", "current_estimated_range_mi": 300, "factory_baseline_range_mi": 310, "degradation_pct": 1.8}]},
        show_battery_health=True,
        trips={"total_miles": 250, "avg_wh_per_mile": 270, "drives_count": 15, "total_duration_hours": 12, "avg_trip_miles": 18, "top_speed_mph": 75, "elevation": {"ascent_ft": 2000, "regen_kwh_recaptured": 4.5}, "longest_drive": None, "top_places": []},
        charging={
            "total_spend": 13.0,
            "total_energy_used_kwh": 100,
            "off_peak_spend": 8.0,
            "off_peak_kwh": 70,
            "shoulder_spend": 2.0,
            "shoulder_kwh": 10,
            "on_peak_spend": 0.0,
            "on_peak_kwh": 0,
            "supercharger_spend": 3.0,
            "supercharger_kwh": 20,
            "home_kwh": 80,
            "home_spend": 10.0,
            "gas_savings": {"net_savings": 22.5, "est_ice_cost": 35.5, "gallons_avoided": 10.1, "savings_pct": 63},
            "cars_breakdown": []
        },
        superchargers={"lifetime_unique_stations": 8, "month_sessions_count": 2, "new_stations_this_month": [], "recent_visits": []},
        health={"cars": []},
        vampire={"total_idle_hours": 150, "estimated_loss_kwh": 12.5, "estimated_cost": 1.62},
        chart_spend="cid:chart_spend",
        chart_tou="cid:chart_tou",
        chart_battery="cid:chart_battery",
        spend={"total_charging_kwh": 100, "total_charging_cost": 13.0, "home_charging_kwh": 80, "home_charging_cost": 9.6, "supercharger_kwh": 20, "supercharger_cost": 3.4, "other_charging_kwh": 0, "other_charging_cost": 0},
        **dashboards
    )

    # Check header buttons
    assert 'href="http://192.168.1.15:4000"' in rendered
    assert '⚡ TeslaMate' in rendered
    assert 'href="http://192.168.1.15:3000"' in rendered
    assert '📊 Grafana' in rendered

    # Check live dashboard links
    assert 'href="http://192.168.1.15:3000/d/-pkIkhmRz/charging-stats?var-car_id=1"' in rendered
    assert 'href="http://192.168.1.15:3000/d/fu4SiQgWz/efficiency?var-car_id=1"' in rendered
    assert 'href="http://192.168.1.15:3000/d/jchmRiqUfXgTM/battery-health?var-car_id=1"' in rendered
    assert 'href="http://192.168.1.15:3000/d/Y8upc6ZRk/drives?var-car_id=1"' in rendered
    assert 'href="http://192.168.1.15:3000/d/zhHx2Fggk/vampire-drain?var-car_id=1"' in rendered

    # Check clickable charts
    assert '<a href="http://192.168.1.15:3000/d/-pkIkhmRz/charging-stats?var-car_id=1"' in rendered
    assert '<a href="http://192.168.1.15:3000/d/jchmRiqUfXgTM/battery-health?var-car_id=1"' in rendered
    assert '<img src="cid:chart_spend"' in rendered
    assert '<img src="cid:chart_battery"' in rendered


def test_get_grafana_dashboard_urls_custom_config():
    from app.services.geofences import get_grafana_dashboard_urls
    from app.config import GrafanaDashboardsConfig

    custom_cfg = GrafanaDashboardsConfig(
        charging="custom-uid/custom-charging",
        efficiency="d/my-efficiency-slug",
        battery_health="carlos/battery-degradation"
    )
    urls = get_grafana_dashboard_urls("http://grafana.lan:3000", car_id=2, dashboards_config=custom_cfg)
    assert urls["grafana_charging_url"] == "http://grafana.lan:3000/d/custom-uid/custom-charging?var-car_id=2"
    assert urls["grafana_efficiency_url"] == "http://grafana.lan:3000/d/my-efficiency-slug?var-car_id=2"
    assert urls["grafana_battery_url"] == "http://grafana.lan:3000/d/carlos/battery-degradation?var-car_id=2"
    # Unconfigured ones use default
    assert urls["grafana_vampire_url"] == "http://grafana.lan:3000/d/zhHx2Fggk/vampire-drain?var-car_id=2"


def test_discover_grafana_dashboards_mocked():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.geofences import discover_grafana_dashboards

    mock_search_data = [
        {"uid": "carlos-charge", "title": "Charging Stats and Cost", "url": "/d/carlos-charge/charging-stats-and-cost"},
        {"uid": "carlos-deg", "title": "Battery Degradation", "url": "/d/carlos-deg/battery-degradation"},
        {"uid": "carlos-eff", "title": "Consumption and Efficiency", "url": "/d/carlos-eff/consumption-and-efficiency"},
        {"uid": "carlos-trips", "title": "Tracking Drives and Trips", "url": "/d/carlos-trips/tracking-drives"},
        {"uid": "carlos-vamp", "title": "Phantom / Vampire Drain", "url": "/d/carlos-vamp/phantom-drain"},
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_search_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        res = asyncio.run(discover_grafana_dashboards("http://localhost:3000", "my_token"))
        assert res["success"] is True
        assert res["count"] == 5
        assert res["mapped"]["charging"] == "carlos-charge/charging-stats-and-cost"
        assert res["mapped"]["battery_health"] == "carlos-deg/battery-degradation"
        assert res["mapped"]["efficiency"] == "carlos-eff/consumption-and-efficiency"
        assert res["mapped"]["drives"] == "carlos-trips/tracking-drives"
        assert res["mapped"]["vampire_drain"] == "carlos-vamp/phantom-drain"



