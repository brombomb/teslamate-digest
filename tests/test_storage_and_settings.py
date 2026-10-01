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
