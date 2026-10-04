import json
import pytest
from app.config import (
    AppConfig, 
    RatesSettings, 
    load_config, 
    save_config, 
    load_maintenance_log, 
    save_maintenance_log, 
    reset_maintenance_log_rotation
)
from app.storage import (
    init_storage,
    load_config_data,
    save_config_data,
    load_maintenance_data,
    save_maintenance_data,
    reset_maintenance_rotation
)
from app.themes import EMAIL_THEMES, THEME_ALIASES, get_theme


def test_sqlite_storage_roundtrip():
    init_storage()
    cfg = load_config()
    orig_gas = cfg.rates.gas_price_per_gal
    
    # Test setting a 3-decimal gas price
    cfg.rates.gas_price_per_gal = 3.459
    cfg.rates.zip_code = "80003"
    save_config(cfg)

    # Reload from SQLite
    reloaded = load_config()
    assert reloaded.rates.gas_price_per_gal == 3.459
    assert reloaded.rates.zip_code == "80003"

    # Restore
    cfg.rates.gas_price_per_gal = orig_gas
    save_config(cfg)


def test_maintenance_storage_and_reset():
    init_storage()
    log = load_maintenance_log()
    test_car_id = "999"
    
    log[test_car_id] = {
        "last_tire_rotation_odometer": 12500.5,
        "last_tire_rotation_date": "2026-05-15",
        "active_tire_set": "all_season",
        "last_tire_swap_date": "2026-04-01",
        "notes": "Test service"
    }
    save_maintenance_log(log)

    # Verify saved
    reloaded = load_maintenance_log()
    assert test_car_id in reloaded
    assert reloaded[test_car_id]["last_tire_rotation_odometer"] == 12500.5
    assert reloaded[test_car_id]["last_tire_rotation_date"] == "2026-05-15"

    # Now test reset / clear rotation
    reset_maintenance_log_rotation(test_car_id)
    cleared = load_maintenance_log()
    assert cleared[test_car_id]["last_tire_rotation_odometer"] == 0.0
    assert cleared[test_car_id]["last_tire_rotation_date"] == ""
    # Other fields should be preserved
    assert cleared[test_car_id]["notes"] == "Test service"
    assert cleared[test_car_id]["active_tire_set"] == "all_season"


def test_theme_names_and_fonts():
    # Pearl White check
    assert "pearl_white" in EMAIL_THEMES
    assert EMAIL_THEMES["pearl_white"]["name"] == "Pearl White"

    # Solid Black should NOT be in EMAIL_THEMES, but in THEME_ALIASES pointing to obsidian_black
    assert "solid_black" not in EMAIL_THEMES
    assert THEME_ALIASES.get("solid_black") == "obsidian_black"
    assert get_theme("solid_black")["id"] == "obsidian_black"

    # Cybertruck and Cybercab name parentheses check
    assert EMAIL_THEMES["cybertruck"]["name"] == "Cybertruck"
    assert "(" not in EMAIL_THEMES["cybertruck"]["name"]
    assert EMAIL_THEMES["cybercab"]["name"] == "Cybercab"
    assert "(" not in EMAIL_THEMES["cybercab"]["name"]

    # Cybertruck header graffiti font check
    cybertruck = EMAIL_THEMES["cybertruck"]
    assert "header_font" in cybertruck
    assert "Permanent Marker" in cybertruck["header_font"]


def test_work_routes_vehicle_isolation():
    from app.config import WorkRouteItem
    r1 = WorkRouteItem(
        label="Home to Office",
        point_a="Home",
        point_b="Office",
        bidirectional=True,
        target_car_id=1
    )
    r2 = WorkRouteItem(
        label="Airport Shuttle",
        point_a="Home",
        point_b="Airport",
        bidirectional=False,
        target_car_id=None
    )
    assert r1.target_car_id == 1
    assert r2.target_car_id is None


def test_settings_pages_routing_and_isolation():
    from starlette.testclient import TestClient
    from app.main import app
    from app.config import WorkRouteItem, ScheduleItem

    client = TestClient(app)

    # 1. Verify GET /settings renders Delivery
    r_deliv = client.get("/settings")
    assert r_deliv.status_code == 200
    assert "Email Delivery Configuration" in r_deliv.text
    assert "Automated Dispatch Schedules" in r_deliv.text
    assert "Work &amp; Commute Mileage Routes" in r_deliv.text
    assert "Excluded Locations from Top Destinations" in r_deliv.text
    assert "Default Email Paint Theme" not in r_deliv.text
    assert "Electricity Rates &amp; Plan Structure" not in r_deliv.text

    # 2. Verify GET /settings/integrations and /integrations render Rates & Integrations
    r_integ = client.get("/settings/integrations")
    assert r_integ.status_code == 200
    assert "Electricity Rates &amp; Plan Structure" in r_integ.text
    assert "Home Assistant &amp; Solar Integration" in r_integ.text
    assert "Work &amp; Commute Mileage Routes" not in r_integ.text
    assert "Excluded Locations from Top Destinations" not in r_integ.text
    assert "Email Delivery Configuration" not in r_integ.text

    r_alias = client.get("/integrations")
    assert r_alias.status_code == 200
    assert "Electricity Rates &amp; Plan Structure" in r_alias.text

    # 3. Seed baseline config
    cfg = load_config()
    cfg.smtp.sender_name = "Delivery Baseline"
    cfg.smtp.recipient_email = "tester@domain.com"
    cfg.rates.gas_price_per_gal = 3.987
    cfg.rates.zip_code = "80005"
    cfg.homeassistant.enabled = True
    cfg.homeassistant.url = "http://192.168.1.50:8123"
    cfg.homeassistant.token = "preserved_secret_token_abc"
    cfg.work_routes = [
        WorkRouteItem(label="HQ Commute", point_a="Home", point_b="Office", bidirectional=True, target_car_id=1)
    ]
    cfg.schedules = [
        ScheduleItem(id="s1", name="Monthly Retrospective", enabled=True, frequency="monthly", send_hour=8, send_minute=0, theme="pearl_white")
    ]
    save_config(cfg)

    # 4. POST /settings (Delivery update ONLY) - must NOT reset rates, commute, or HA!
    post_deliv = client.post("/settings", data={
        "smtp_enabled": "on",
        "smtp_host": "smtp.mailgun.org",
        "smtp_port": "587",
        "smtp_user": "postmaster@domain.com",
        "smtp_password": "supersecretpassword",
        "sender_email": "digest@domain.com",
        "recipient_email": "updated_recipient@domain.com",
        "sender_name": "Delivery Updated",
        "use_tls": "on",
        "email_theme": "cybercab",
        "schedules_json": json.dumps([
            {"id": "s1", "name": "Weekly Quick Digest", "enabled": True, "frequency": "weekly", "day_of_week": 0, "day_of_month": 1, "send_hour": 7, "send_minute": 30, "target_car_id": None, "recipient_email": "", "theme": "cybercab"}
        ])
    })
    assert post_deliv.status_code == 200

    cfg_after_deliv = load_config()
    # Check that delivery fields changed:
    assert cfg_after_deliv.smtp.sender_name == "Delivery Updated"
    assert cfg_after_deliv.smtp.recipient_email == "updated_recipient@domain.com"
    assert cfg_after_deliv.schedules[0].name == "Weekly Quick Digest"
    assert cfg_after_deliv.email_theme == "cybercab"
    # Check that rates, routes, and HA were completely preserved and NOT reset!
    assert cfg_after_deliv.rates.gas_price_per_gal == 3.987
    assert cfg_after_deliv.rates.zip_code == "80005"
    assert cfg_after_deliv.homeassistant.token == "preserved_secret_token_abc"
    assert cfg_after_deliv.homeassistant.url == "http://192.168.1.50:8123"
    assert len(cfg_after_deliv.work_routes) == 1
    assert cfg_after_deliv.work_routes[0].label == "HQ Commute"

    # 5. POST /settings/integrations (Rates/Integrations update) - must NOT reset SMTP or schedules!
    # Also verify empty ha_token does NOT blank out existing secret token
    post_integ = client.post("/settings/integrations", data={
        "rate_mode": "tou",
        "gas_price_per_gal": "4.129",
        "zip_code": "80007",
        "utility_name": "Xcel Energy",
        "ha_enabled": "on",
        "ha_url": "http://192.168.1.99:8123",
        "ha_token": "",  # Empty submitted: must preserve existing token!
        "work_routes_json": json.dumps([
            {"label": "Gym Trip", "point_a": "Home", "point_b": "Gym", "bidirectional": True, "target_car_id": None}
        ]),
        "tire_rotation_interval_mi": "7000"
    })
    assert post_integ.status_code == 200

    cfg_after_integ = load_config()
    # Check that integrations updated:
    assert cfg_after_integ.rates.gas_price_per_gal == 4.129
    assert cfg_after_integ.rates.zip_code == "80007"
    assert cfg_after_integ.homeassistant.url == "http://192.168.1.99:8123"
    assert cfg_after_integ.homeassistant.token == "preserved_secret_token_abc"  # Preserved!
    assert len(cfg_after_integ.work_routes) == 1
    assert cfg_after_integ.work_routes[0].label == "Gym Trip"
    assert cfg_after_integ.tire_rotation_interval_mi == 7000
    # Check that delivery settings and schedules were NOT clobbered!
    assert cfg_after_integ.smtp.sender_name == "Delivery Updated"
    assert cfg_after_integ.smtp.recipient_email == "updated_recipient@domain.com"
    assert cfg_after_integ.schedules[0].name == "Weekly Quick Digest"
    assert cfg_after_integ.email_theme == "cybercab"

    # 6. POST /settings with work routes, irs rate, and excluded locations
    post_deliv_routes = client.post("/settings", data={
        "smtp_enabled": "on",
        "work_routes_json": json.dumps([
            {"label": "Direct Work Commute", "point_a": "Home", "point_b": "Tech Center", "bidirectional": True, "target_car_id": None}
        ]),
        "irs_mileage_rate": "0.70",
        "excluded_locations": "Home, Secret Base"
    })
    assert post_deliv_routes.status_code == 200
    cfg_deliv_routes = load_config()
    assert len(cfg_deliv_routes.work_routes) == 1
    assert cfg_deliv_routes.work_routes[0].label == "Direct Work Commute"
    assert cfg_deliv_routes.irs_mileage_rate == 0.70
    assert cfg_deliv_routes.excluded_locations == ["Home", "Secret Base"]


def test_dispatch_history_persistence():
    from app.storage import record_dispatch_history, get_last_dispatch, get_recent_dispatches
    from app.scheduler import get_scheduler_status, last_run_info

    # Record a dispatch
    record_dispatch_history(
        status="Success",
        details="Delivered Monthly Test Digest to test@example.com",
        timestamp="2026-10-01 08:00:00",
        schedule_id="test-sched-1",
        schedule_name="Monthly Test Digest",
        frequency="monthly",
        target_car_id=1,
        target_car_name="Model Y",
        recipient="test@example.com",
        theme="frost_blue"
    )

    last = get_last_dispatch()
    assert last is not None
    assert last["status"] == "Success"
    assert last["timestamp"] == "2026-10-01 08:00:00"
    assert last["schedule_name"] == "Monthly Test Digest"
    assert "Delivered Monthly Test Digest" in last["details"]

    recent = get_recent_dispatches(limit=5)
    assert len(recent) >= 1
    assert recent[0]["schedule_name"] == "Monthly Test Digest"
    assert recent[0]["status"] == "Success"

    # Verify get_scheduler_status falls back to persistent dispatch when in-memory timestamp is None
    last_run_info["timestamp"] = None
    status = get_scheduler_status()
    assert status["last_run"]["status"] == "Success"
    assert status["last_run"]["timestamp"] == "2026-10-01 08:00:00"


def test_top_tab_bars_removed_from_settings_templates():
    from pathlib import Path
    settings_html = (Path(__file__).parent.parent / "app" / "templates" / "web" / "settings.html").read_text()
    integrations_html = (Path(__file__).parent.parent / "app" / "templates" / "web" / "settings_integrations.html").read_text()

    # Redundant tab navigation button bar must be dropped from both
    assert "TOP TAB NAVIGATION" not in settings_html
    assert "TOP TAB NAVIGATION" not in integrations_html
    assert '<a href="/settings/integrations" class="px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition bg-slate-100' not in settings_html
    assert '<a href="/settings" class="px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition bg-slate-100' not in integrations_html


