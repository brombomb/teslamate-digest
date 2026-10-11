import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.testclient import TestClient

from app.cache import (
    TTLCache,
    report_cache,
    make_telemetry_cache_key,
    make_report_cache_key,
    clear_report_cache
)
from app.config import AppConfig, load_config
from app.main import app, resolve_period_dates


def test_ttl_cache_crud_and_expiry():
    cache = TTLCache(default_ttl=10)
    assert cache.stats()["size"] == 0

    # Basic get/set
    cache.set("key1", "val1")
    assert cache.get("key1") == "val1"
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 0

    # Non-existent key
    assert cache.get("nonexistent") is None
    assert cache.stats()["misses"] == 1

    # Overwrite
    cache.set("key1", "val2")
    assert cache.get("key1") == "val2"

    # Delete
    assert cache.delete("key1") is True
    assert cache.delete("key1") is False
    assert cache.get("key1") is None

    # Expiry
    cache.set("short_lived", "data", ttl=0.05)
    assert cache.get("short_lived") == "data"
    time.sleep(0.06)
    assert cache.get("short_lived") is None

    # Cleanup expired
    cache.set("k1", "v1", ttl=0.01)
    cache.set("k2", "v2", ttl=100)
    time.sleep(0.02)
    cleaned = cache.cleanup()
    assert cleaned == 1
    assert cache.get("k2") == "v2"

    # Clear
    cache.clear()
    assert cache.stats()["size"] == 0


def test_telemetry_and_report_cache_keys():
    cfg1 = AppConfig()
    cfg2 = AppConfig()

    d1 = datetime(2026, 1, 1, 0, 0, 0)
    d2 = datetime(2026, 2, 1, 0, 0, 0)

    # Identical config produces identical telemetry key
    key1 = make_telemetry_cache_key(d1, d2, 1, cfg1)
    key2 = make_telemetry_cache_key(d1, d2, 1, cfg2)
    assert key1 == key2

    # Different car produces different key
    key_diff_car = make_telemetry_cache_key(d1, d2, 2, cfg1)
    assert key1 != key_diff_car

    # Different rate setting produces different key
    cfg2.rates.off_peak_kwh_cost = 0.05
    key_diff_rate = make_telemetry_cache_key(d1, d2, 1, cfg2)
    assert key1 != key_diff_rate

    # Report cache key varies by theme and email mode
    rep_preview_dark = make_report_cache_key(d1, d2, 1, "dark_modern", False, cfg1)
    rep_preview_light = make_report_cache_key(d1, d2, 1, "pearl_white", False, cfg1)
    rep_email_dark = make_report_cache_key(d1, d2, 1, "dark_modern", True, cfg1)

    assert rep_preview_dark != rep_preview_light
    assert rep_preview_dark != rep_email_dark


def test_clear_report_cache():
    report_cache.set("test_key", {"data": 123})
    assert report_cache.get("test_key") == {"data": 123}
    clear_report_cache()
    assert report_cache.get("test_key") is None


def test_resolve_period_dates():
    now = datetime(2026, 5, 15, 14, 30, 0)

    # Yesterday
    s_yest, e_yest = resolve_period_dates("yesterday", now)
    assert e_yest == datetime(2026, 5, 15, 0, 0, 0)
    assert s_yest == datetime(2026, 5, 14, 0, 0, 0)

    # Last Week
    s_week, e_week = resolve_period_dates("last_week", now)
    assert e_week == datetime(2026, 5, 15, 0, 0, 0)
    assert s_week == datetime(2026, 5, 8, 0, 0, 0)

    # This Month
    s_month, e_month = resolve_period_dates("this_month", now)
    assert s_month == datetime(2026, 5, 1, 0, 0, 0)
    assert e_month == now

    # Last Month
    s_lastm, e_lastm = resolve_period_dates("last_month", now)
    assert s_lastm == datetime(2026, 4, 1, 0, 0, 0)
    assert e_lastm == datetime(2026, 5, 1, 0, 0, 0)


@pytest.mark.anyio
async def test_preview_render_api_endpoint(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_cars = AsyncMock(return_value=[{"id": 1, "name": "Model 3", "model": "3"}])
    app.state.db = mock_db

    clear_report_cache()

    # Mock build_digest_report to observe caching
    call_count = 0

    async def fake_build_digest(db, config, start_date, end_date, car_id=None, for_email=False, theme_override=None, force_refresh=False, modules_override=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return (f"Digest Report {call_count}", f"<h1>Preview HTML {call_count}</h1>", {})

    with patch("app.main.build_digest_report", side_effect=fake_build_digest):
        with TestClient(app) as client:
            # 1. First fetch
            res = client.get("/api/preview/render?period=last_month&car_id=1&theme=dark_modern")
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert "Digest Report 1" in data["subject"]
            assert "<h1>Preview HTML 1</h1>" in data["html"]
            assert call_count == 1

            # 2. Force refresh via nocache=1
            res_nocache = client.get("/api/preview/render?period=last_month&car_id=1&theme=dark_modern&nocache=1")
            assert res_nocache.status_code == 200
            assert call_count == 2
            data_nocache = res_nocache.json()
            assert "Digest Report 2" in data_nocache["subject"]


def test_settings_and_maintenance_evict_cache():
    mock_db = MagicMock()
    mock_db.get_cars = AsyncMock(return_value=[])
    mock_db.fetchrow = AsyncMock(return_value={"odometer_mi": 5000.0})
    app.state.db = mock_db

    with TestClient(app) as client:
        # Pre-seed cache
        report_cache.set("tel:dummy", {"some": "data"})
        assert report_cache.stats()["size"] > 0

        # POST /settings should clear cache
        client.post("/settings", data={
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "u",
            "smtp_password": "p",
            "recipient_email": "r@example.com",
            "frequency": "monthly",
            "send_hour": "8",
            "send_minute": "0",
            "modules_submitted": "1"
        })
        assert report_cache.stats()["size"] == 0

        # Pre-seed cache again
        report_cache.set("tel:dummy", {"some": "data"})
        assert report_cache.stats()["size"] > 0

        # POST /settings/integrations should clear cache
        client.post("/settings/integrations", data={
            "rate_mode": "tou",
            "average_kwh_cost": "0.15"
        })
        assert report_cache.stats()["size"] == 0

        # Pre-seed cache again
        report_cache.set("tel:dummy", {"some": "data"})
        assert report_cache.stats()["size"] > 0

        # POST /maintenance/quick-rotate should clear cache
        client.post("/maintenance/quick-rotate", data={"car_id": "1"})
        assert report_cache.stats()["size"] == 0


def test_ttl_cache_max_size_bounding():
    small_cache = TTLCache(default_ttl=300, max_size=20)
    for i in range(50):
        small_cache.set(f"key_{i}", f"val_{i}")
    assert small_cache.stats()["size"] <= 20
    # Oldest key should have been evicted
    assert small_cache.get("key_0") is None
    # Most recent key should exist
    assert small_cache.get("key_49") == "val_49"


def test_security_headers_middleware():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_jinja_report_autoescape():
    from app.report import get_jinja_env
    env = get_jinja_env()
    assert env.autoescape is not False
    # Render untrusted HTML string to verify autoescape
    template = env.from_string("Hello {{ name }}")
    rendered = template.render(name="<script>alert(1)</script>")
    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_mailer_crlf_stripping():
    from app.config import SMTPSettings
    from app.mailer import Mailer
    from unittest.mock import MagicMock

    smtp_cfg = SMTPSettings(
        enabled=True,
        host="smtp.example.com",
        port=587,
        user="test@example.com",
        password="secretpassword",
        sender_email="safe@example.com\r\nBcc: evil@attacker.com",
        sender_name="Sender\r\nName",
        recipient_email="victim@example.com\r\nBcc: evil@attacker.com"
    )
    mailer = Mailer(smtp_cfg)

    # Mock smtplib to inspect message headers
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        mailer.send_email(
            subject="Test\r\nSubject\nInjection",
            html_content="<p>Test</p>"
        )

        sent_call = mock_server.sendmail.call_args
        from_arg = sent_call[0][0]
        to_arg = sent_call[0][1]

        # Verify no carriage returns or line feeds in sender or recipient
        assert "\r" not in from_arg and "\n" not in from_arg
        assert "\r" not in to_arg[0] and "\n" not in to_arg[0]


def test_builder_view_and_theme_starter():
    client = TestClient(app)

    # 1. Builder UI renders properly with all module blocks & tabs
    res = client.get("/builder")
    assert res.status_code == 200
    html = res.text
    assert "Custom Template Builder" in html
    assert "Quick Insert Module Cards" in html
    assert "tab-btn-body" in html
    assert "tab-btn-style" in html
    assert "tab-btn-full" in html
    assert "Battery Health" in html
    assert "TPMS" in html
    assert "Solar Production" in html
    assert "Vampire Loss" in html

    # 2. Starter generation produces valid CSS without truncated style block
    res_starter = client.get("/builder/starter?theme=pearl_white")
    assert res_starter.status_code == 200
    starter_html = res_starter.text
    assert "<style>" in starter_html
    assert "body {" in starter_html
    assert ".main-table {" in starter_html
    assert "{{ theme.body_bg }}" not in starter_html
    assert "{{ theme.card_bg }}" not in starter_html
    assert "{{ theme.font_family" not in starter_html

    # 3. Cybertruck theme starter produces 0px border radius
    res_cyber = client.get("/builder/starter?theme=cybertruck")
    assert res_cyber.status_code == 200
    cyber_html = res_cyber.text
    assert "0px" in cyber_html

    # 4. Theme palette endpoint returns comprehensive tokens
    res_pal = client.get("/api/theme-palette?theme=obsidian_black")
    assert res_pal.status_code == 200
    pal_data = res_pal.json()
    assert pal_data["id"] == "obsidian_black"
    assert "card_inner_border" in pal_data
    assert "accent_green" in pal_data
    assert "badge_bg" in pal_data


def test_preview_page_view():
    mock_db = MagicMock()
    mock_db.get_cars = AsyncMock(return_value=[{"id": 1, "name": "Model 3", "model": "3"}])
    app.state.db = mock_db

    async def fake_build_digest(*args, **kwargs):
        return ("Digest Report", "<html><body>Digest Body</body></html>", {})

    with patch("app.main.build_digest_report", side_effect=fake_build_digest):
        with TestClient(app) as client:
            res = client.get("/preview")
            assert res.status_code == 200
            assert "Live Preview" in res.text


@pytest.mark.anyio
async def test_fetch_digest_telemetry_gas_price_refresh():
    from app.report import fetch_digest_telemetry
    mock_db = MagicMock()
    def mock_fetchrow(query, *args):
        if "ORDER BY d.distance DESC" in query:
            return None
        return {
            "drives_count": 0,
            "total_km": 0,
            "total_duration_min": 0,
            "top_speed_kmh": 0,
            "total_ascent_m": 0,
            "total_descent_m": 0
        }

    mock_db.fetchrow = AsyncMock(side_effect=mock_fetchrow)
    mock_db.fetch = AsyncMock(return_value=[])
    mock_db.get_units = AsyncMock(return_value={"unit_of_length": "mi", "unit_of_temperature": "F"})
    mock_db.get_trips = AsyncMock(return_value=[])
    mock_db.get_charging_sessions = AsyncMock(return_value=[])
    mock_db.get_battery_health = AsyncMock(return_value=[])
    mock_db.get_cars = AsyncMock(return_value=[{"id": 1, "name": "Test Car", "model": "Y"}])
    mock_db.get_addresses = AsyncMock(return_value=[])
    mock_db.get_charges_with_cost = AsyncMock(return_value=[])
    cfg = load_config()
    cfg.rates.auto_gas_price = True

    with patch("app.services.gas_prices.fetch_live_gas_price", new_callable=AsyncMock) as mock_gas:
        mock_gas.return_value = 3.89
        tel = await fetch_digest_telemetry(
            db=mock_db,
            config=cfg,
            start_date=datetime(2026, 8, 1),
            end_date=datetime(2026, 8, 31),
            car_id=1,
            force_refresh=True
        )
        assert mock_gas.called
        assert mock_gas.call_args[1]["force_refresh"] is True


