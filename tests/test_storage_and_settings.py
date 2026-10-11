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


def test_storage_file_permissions_hardened():
    import stat
    from app.storage import (
        init_storage, 
        save_config_data, 
        save_maintenance_data,
        SQLITE_DB_PATH, 
        LEGACY_CONFIG_FILE, 
        LEGACY_MAINTENANCE_FILE
    )

    init_storage()
    save_config_data({"test_key": "test_val"})
    save_maintenance_data({"test_car": {"notes": "secure"}})

    if SQLITE_DB_PATH.exists():
        mode = stat.S_IMODE(SQLITE_DB_PATH.stat().st_mode)
        assert (mode & 0o007) == 0  # No world access
        assert (mode & 0o002) == 0  # Not world writable

    if LEGACY_CONFIG_FILE.exists():
        mode = stat.S_IMODE(LEGACY_CONFIG_FILE.stat().st_mode)
        assert (mode & 0o007) == 0  # No world access
        assert (mode & 0o004) == 0  # Not world readable

    if LEGACY_MAINTENANCE_FILE.exists():
        mode = stat.S_IMODE(LEGACY_MAINTENANCE_FILE.stat().st_mode)
        assert (mode & 0o007) == 0
        assert (mode & 0o004) == 0


def test_schedule_module_overrides():
    from starlette.testclient import TestClient
    from app.main import app
    from app.config import load_config, save_config, ScheduleItem, ModuleToggles

    client = TestClient(app)

    # 1. Post settings with two schedules:
    # Schedule A: Daily work commute with ONLY work_mileage enabled
    # Schedule B: Monthly retrospective using global modules (override_modules=False)
    schedules_payload = [
        {
            "id": "daily_commute",
            "name": "Daily Work Trips",
            "enabled": True,
            "frequency": "daily",
            "send_hour": 7,
            "send_minute": 15,
            "target_car_id": None,
            "theme": "dark_modern",
            "override_modules": True,
            "modules": {
                "work_mileage": True,
                "spend_breakdown": False,
                "gas_savings": False,
                "battery_health": False,
                "driving_efficiency": False,
                "charge_limit_compliance": False,
                "supercharger_explorer": False,
                "top_locations": False,
                "driving_milestones": False,
                "mountain_regen": False,
                "vampire_drain": False,
                "maintenance_alerts": False,
                "snow_tire_reminder": False,
                "embedded_charts": False,
                "solar_production": False,
                "achievements": False
            }
        },
        {
            "id": "monthly_fleet",
            "name": "Monthly Complete Fleet",
            "enabled": True,
            "frequency": "monthly",
            "send_hour": 8,
            "send_minute": 0,
            "target_car_id": None,
            "theme": "pearl_white",
            "override_modules": False,
            "modules": None
        }
    ]

    res = client.post("/settings", data={
        "smtp_enabled": "on",
        "schedules_json": json.dumps(schedules_payload)
    })
    assert res.status_code == 200

    cfg = load_config()
    assert len(cfg.schedules) == 2

    daily = cfg.schedules[0]
    assert daily.id == "daily_commute"
    assert daily.override_modules is True
    assert daily.modules is not None
    assert daily.modules.work_mileage is True
    assert daily.modules.spend_breakdown is False
    assert daily.modules.achievements is False

    # Effective modules on daily schedule must return the override
    daily_eff = daily.get_effective_modules(cfg.modules)
    assert daily_eff.work_mileage is True
    assert daily_eff.spend_breakdown is False

    monthly = cfg.schedules[1]
    assert monthly.id == "monthly_fleet"
    assert monthly.override_modules is False
    # Effective modules on monthly schedule must fall back to global config
    monthly_eff = monthly.get_effective_modules(cfg.modules)
    assert monthly_eff.spend_breakdown == cfg.modules.spend_breakdown
    assert monthly_eff.gas_savings == cfg.modules.gas_savings


def test_ssrf_is_safe_url_guard():
    from app.services.homeassistant import is_safe_url

    # Allowed valid URLs
    assert is_safe_url("http://homeassistant:8123") is True
    assert is_safe_url("https://ha.mydomain.com:8123") is True
    assert is_safe_url("http://192.168.1.100:8123") is True
    assert is_safe_url("http://grafana:3000") is True

    # Blocked invalid schemes and metadata exfiltration targets
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://server/file") is False
    assert is_safe_url("gopher://server/1") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_url("http://metadata.google.internal/computeMetadata/v1/") is False
    assert is_safe_url("http://100.100.100.200/") is False
    assert is_safe_url("") is False


def test_basic_auth_middleware():
    from starlette.testclient import TestClient
    from app.main import app
    import app.main as main_mod

    client = TestClient(app)

    # 1. Without credentials configured, open access is allowed
    main_mod.WEB_AUTH_USER = ""
    main_mod.WEB_AUTH_PASS = ""
    res = client.get("/favicon.ico")
    assert res.status_code in (200, 404)

    # 2. When credentials configured, unauthorized requests are rejected with 401
    main_mod.WEB_AUTH_USER = "admin"
    main_mod.WEB_AUTH_PASS = "supersecret"
    try:
        res_unauth = client.get("/api/theme-palette?theme=pearl_white")
        assert res_unauth.status_code == 401
        assert "Basic" in res_unauth.headers.get("WWW-Authenticate", "")

        # 3. Bad credentials rejected
        res_bad = client.get("/api/theme-palette?theme=pearl_white", auth=("admin", "wrongpassword"))
        assert res_bad.status_code == 401

        # 4. Valid credentials accepted
        res_good = client.get("/api/theme-palette?theme=pearl_white", auth=("admin", "supersecret"))
        assert res_good.status_code == 200

        # 5. Docker health check bypasses auth and returns version
        res_health = client.get("/api/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"
        assert res_health.json()["version"] == "1.0.0"
    finally:
        main_mod.WEB_AUTH_USER = ""
        main_mod.WEB_AUTH_PASS = ""


def test_health_and_version_information():
    from starlette.testclient import TestClient
    from app import __version__
    from app.main import app, templates

    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "teslamate-digest"
    assert data["version"] == __version__
    assert templates.env.globals["app_version"] == __version__




