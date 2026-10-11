import os
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.db import Database
from app.config import AppConfig
from app.cache import report_cache, make_telemetry_cache_key, make_report_cache_key
from app.analytics.charging import get_charging_analytics
from app.analytics.trips import get_trip_analytics
from app.analytics.superchargers import get_supercharger_analytics
from app.analytics.battery import get_battery_health_analytics
from app.analytics.health import get_health_analytics
from app.analytics.vampire import get_vampire_analytics
from app.analytics.efficiency import get_driving_efficiency_analytics
from app.analytics.compliance import get_charge_compliance_analytics
from app.analytics.work_mileage import get_work_mileage_analytics
from app.analytics.wrapped import get_year_in_review_analytics
from app.analytics.achievements import get_achievements_analytics
from app.analytics.insights import generate_digest_insights
from app.themes import get_theme
from app.services.geofences import get_effective_service_urls, get_grafana_dashboard_urls
from app.services.homeassistant import fetch_solar_summary
from app.services.units import get_effective_units
import app.charts as charts

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates" / "email"
CUSTOM_TEMPLATES_DIR = Path(os.getenv("CUSTOM_TEMPLATES_DIR", "/app/custom_templates"))
if not CUSTOM_TEMPLATES_DIR.exists():
    fallback_custom = BASE_DIR.parent / "custom_templates"
    if fallback_custom.exists():
        CUSTOM_TEMPLATES_DIR = fallback_custom


def get_jinja_env() -> Environment:
    loaders = []
    if CUSTOM_TEMPLATES_DIR.exists():
        loaders.append(FileSystemLoader(str(CUSTOM_TEMPLATES_DIR)))
    loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
    loader = loaders[0] if len(loaders) == 1 else FileSystemLoader([str(CUSTOM_TEMPLATES_DIR), str(TEMPLATES_DIR)])
    return Environment(
        loader=loader,
        autoescape=select_autoescape(["html", "xml"])
    )


def to_utc(dt: datetime, tz_name: str) -> datetime:
    """Converts a local datetime to naive UTC datetime for querying PostgreSQL."""
    if dt.tzinfo is None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        dt_local = dt.replace(tzinfo=tz)
    else:
        dt_local = dt
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


async def fetch_digest_telemetry(
    db: Database,
    config: AppConfig,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetches all telemetry, analytics, and Home Assistant metrics.
    Caches the aggregated dictionary so theme changes and repeated previews load in milliseconds.
    Executes independent queries concurrently using asyncio.gather.
    """
    tel_key = make_telemetry_cache_key(start_date, end_date, car_id, config)
    if not force_refresh:
        cached = report_cache.get(tel_key)
        if cached is not None:
            return cached

    # Convert query boundaries from user's local timezone to UTC for database queries
    start_utc = to_utc(start_date, config.timezone)
    end_utc = to_utc(end_date, config.timezone)

    # 1. Effective units
    units = await get_effective_units(db, config)

    # 2. Live gas price helper
    async def _get_gas_price():
        if config.rates.auto_gas_price:
            from app.services.gas_prices import fetch_live_gas_price
            return await fetch_live_gas_price(
                config.rates.zip_code,
                config.rates.gas_price_per_gal,
                force_refresh=force_refresh
            )
        return config.rates.gas_price_per_gal

    # 3. Achievements helper
    async def _get_achievements():
        if getattr(config.modules, "achievements", True):
            try:
                return await get_achievements_analytics(
                    db, start_utc, end_utc, car_id, units=units, tz=config.timezone
                )
            except Exception as e:
                print(f"[Report] Error fetching achievements analytics: {e}")
        return {}

    routes_config = [r.model_dump() if hasattr(r, 'model_dump') else r for r in getattr(config, "work_routes", [])]

    # Concurrent parallel execution of independent queries
    (
        gas_price,
        trips,
        superchargers,
        battery,
        health,
        vampire,
        efficiency,
        compliance,
        work_mileage,
        achievements,
        cars,
    ) = await asyncio.gather(
        _get_gas_price(),
        get_trip_analytics(db, start_utc, end_utc, car_id, config.excluded_locations, config=config),
        get_supercharger_analytics(db, start_utc, end_utc, car_id),
        get_battery_health_analytics(db, end_utc, car_id, length_unit=units["length"]),
        get_health_analytics(
            db, start_utc, end_utc, car_id, config.tire_rotation_interval_mi,
            pressure_unit=units["pressure"],
            length_unit=units["length"]
        ),
        get_vampire_analytics(db, start_utc, end_utc, car_id, config.rates.average_kwh_cost),
        get_driving_efficiency_analytics(db, start_utc, end_utc, car_id),
        get_charge_compliance_analytics(db, start_utc, end_utc, car_id),
        get_work_mileage_analytics(
            db, start_utc, end_utc, routes_config, car_id,
            getattr(config, "irs_mileage_rate", 0.67),
            commute_target_car_id=getattr(config, "commute_target_car_id", None),
            config=config
        ),
        _get_achievements(),
        db.get_cars(),
    )

    if config.rates.auto_gas_price and gas_price:
        config.rates.gas_price_per_gal = gas_price

    # 4. Charging analytics (needs trips total_miles)
    charging = await get_charging_analytics(
        db, start_utc, end_utc, car_id, config.rates, trips["total_miles"], tz=config.timezone
    )

    # 5. Solar Energy & Home Assistant Telemetry
    solar = {
        "has_data": False,
        "total_solar_kwh": 0.0,
        "home_charging_kwh": charging.get("home_kwh", 0.0),
        "solar_ev_coverage_pct": 0.0,
        "clean_miles_covered": 0.0,
        "solar_surplus_kwh": 0.0,
        "solar_savings": 0.0,
        "grid_import_kwh": 0.0,
        "grid_export_kwh": 0.0,
        "home_load_kwh": 0.0,
        "peak_solar_kw": 0.0,
        "self_consumption_pct": 100.0,
        "daily_breakdown": [],
    }
    ha_cfg = getattr(config, "homeassistant", None)
    if ha_cfg and ha_cfg.enabled and getattr(config.modules, "solar_production", True):
        try:
            solar = await fetch_solar_summary(
                ha_cfg,
                start_date=start_date,
                end_date=end_date,
                home_charging_kwh=charging.get("home_kwh", 0.0),
                kwh_cost=config.rates.off_peak_kwh_cost or config.rates.average_kwh_cost or 0.13
            )
        except Exception as e:
            print(f"[Report] Error fetching solar telemetry from Home Assistant: {e}")

    telemetry = {
        "units": units,
        "trips": trips,
        "charging": charging,
        "superchargers": superchargers,
        "battery": battery,
        "health": health,
        "vampire": vampire,
        "efficiency": efficiency,
        "compliance": compliance,
        "work_mileage": work_mileage,
        "achievements": achievements,
        "solar": solar,
        "cars": cars,
    }

    # Cache telemetry: 5 minutes (300s) for recent, 1 hour (3600s) for closed past periods
    ttl = 3600 if (datetime.now() - end_date).total_seconds() > 86400 else 300
    report_cache.set(tel_key, telemetry, ttl=ttl)
    return telemetry


async def build_digest_report(
    db: Database,
    config: AppConfig,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    for_email: bool = False,
    theme_override: Optional[str] = None,
    force_refresh: bool = False,
    modules_override: Optional[Any] = None
) -> Tuple[str, str, Dict[str, bytes]]:
    """
    Builds the complete digest HTML and charts.
    Returns: (subject, html_content, inline_image_dict)
    """
    active_modules = modules_override if modules_override is not None else config.modules

    rep_key = make_report_cache_key(start_date, end_date, car_id, theme_override, for_email, config, modules_override=modules_override)
    if not force_refresh and not for_email:
        cached_rep = report_cache.get(rep_key)
        if cached_rep is not None:
            return cached_rep

    telemetry = await fetch_digest_telemetry(
        db=db,
        config=config,
        start_date=start_date,
        end_date=end_date,
        car_id=car_id,
        force_refresh=(force_refresh or for_email)
    )

    units = telemetry["units"]
    trips = telemetry["trips"]
    charging = telemetry["charging"]
    superchargers = telemetry["superchargers"]
    battery = telemetry["battery"]
    health = telemetry["health"]
    vampire = telemetry["vampire"]
    efficiency = telemetry["efficiency"]
    compliance = telemetry["compliance"]
    work_mileage = telemetry["work_mileage"]
    achievements = telemetry["achievements"]
    solar = telemetry["solar"]
    cars = telemetry["cars"]

    car_name = "Fleet"
    single_car_name = None
    car_badge = None
    if car_id:
        for c in cars:
            if c["id"] == car_id:
                single_car_name = c["name"]
                model_str = f"Model {c['model']}" if c.get("model") else ""
                trim_str = c.get("trim_badging") or ""
                if model_str and trim_str:
                    car_badge = f"{model_str} · {trim_str}"
                elif model_str:
                    car_badge = model_str
                elif trim_str:
                    car_badge = trim_str
                else:
                    car_badge = "Tesla"
                car_name = f"{c['name']} ({car_badge})"
                break
    elif len(cars) == 1:
        c = cars[0]
        single_car_name = c["name"]
        model_str = f"Model {c['model']}" if c.get("model") else ""
        trim_str = c.get("trim_badging") or ""
        if model_str and trim_str:
            car_badge = f"{model_str} · {trim_str}"
        elif model_str:
            car_badge = model_str
        elif trim_str:
            car_badge = trim_str
        else:
            car_badge = "Tesla"
        car_name = f"{c['name']} ({car_badge})"
    else:
        car_badge = f"{len(cars)} Vehicles" if len(cars) > 1 else "All Vehicles"

    car_display = single_car_name or "Your Fleet"

    # Inclusive end date calculation for user display (e.g. Sep 1–30 rather than Sep 01 to Oct 01)
    inclusive_end = end_date - timedelta(days=1) if end_date > start_date and (end_date.hour == 0 and end_date.minute == 0) else end_date
    if inclusive_end < start_date:
        inclusive_end = start_date

    is_monthly = (end_date - start_date).days >= 27
    is_single_day = (inclusive_end.date() == start_date.date())

    if is_monthly:
        period_label = "Monthly Review"
    elif is_single_day:
        period_label = "Daily Report"
    elif (end_date - start_date).days <= 8:
        period_label = "Weekly Report"
    else:
        period_label = "Fleet Review" if not single_car_name else "Vehicle Review"

    def format_day(d: datetime) -> str:
        return f"{d.strftime('%b')} {d.day}"

    if is_monthly:
        report_title = f"{car_display} · {start_date.strftime('%B %Y')}"
        if start_date.year == inclusive_end.year:
            date_subtitle = f"{format_day(start_date)}–{inclusive_end.day}, {start_date.year}"
        else:
            date_subtitle = f"{format_day(start_date)}, {start_date.year} – {format_day(inclusive_end)}, {inclusive_end.year}"
    elif is_single_day:
        report_title = f"{car_display} · {start_date.strftime('%a %b')} {start_date.day}"
        date_subtitle = f"{start_date.strftime('%A, %B')} {start_date.day}, {start_date.year}"
    else:
        if start_date.month == inclusive_end.month and start_date.year == inclusive_end.year:
            report_title = f"{car_display} · {format_day(start_date)}–{inclusive_end.day}"
            date_subtitle = f"{format_day(start_date)}–{inclusive_end.day}, {start_date.year}"
        else:
            report_title = f"{car_display} · {format_day(start_date)} – {format_day(inclusive_end)}"
            date_subtitle = f"{format_day(start_date)} – {format_day(inclusive_end)}, {inclusive_end.year}"

    car_subtitle = car_name

    # One-line summary and preheader
    miles_val = trips.get("total_miles", 0.0)
    spend_val = charging.get("total_spend", 0.0)
    off_peak_pct = charging.get("off_peak_score_pct", 100.0)

    summary_parts = [
        f"{miles_val:,.0f} {units.get('length', 'mi')}",
        f"${spend_val:,.2f}",
        f"{off_peak_pct:.0f}% off-peak",
    ]
    gas_saved_val = charging.get("gas_savings", {}).get("net_savings", 0.0)
    if gas_saved_val > 0:
        summary_parts.append(f"${gas_saved_val:,.0f} saved")

    one_line_summary = " · ".join(summary_parts)
    preheader_text = f"{report_title}: {one_line_summary}"
    subject = f"⚡ TeslaMate Digest: {report_title}"

    # Fetch previous period telemetry for MoM deltas
    prev_telemetry = None
    period_duration = end_date - start_date
    if period_duration.total_seconds() > 0:
        prev_start = start_date - period_duration
        prev_end = start_date
        try:
            prev_telemetry = await fetch_digest_telemetry(
                db=db,
                config=config,
                start_date=prev_start,
                end_date=prev_end,
                car_id=car_id,
                force_refresh=False
            )
        except Exception as e:
            print(f"[Report] Error fetching previous period telemetry: {e}")

    insights = generate_digest_insights(telemetry, config, prev_telemetry=prev_telemetry)

    try:
        tz = ZoneInfo(config.timezone)
        generation_timestamp = datetime.now(tz).strftime("%b %d, %Y at %I:%M %p %Z")
    except Exception:
        generation_timestamp = datetime.now(timezone.utc).strftime("%b %d, %Y at %I:%M %p UTC")

    # Battery health is strictly monthly only per user requirement
    show_battery_health = bool(active_modules.battery_health and is_monthly)

    # 2. Choose Theme & Prepare Chart Styling
    chosen_theme = theme_override or getattr(config, "email_theme", "dark_modern")
    theme = get_theme(chosen_theme)

    ha_cfg = getattr(config, "homeassistant", None)

    # 3. Charts Generation
    inline_images: Dict[str, bytes] = {}
    chart_spend_src = ""
    chart_tou_src = ""
    chart_battery_src = ""
    chart_solar_src = ""

    if active_modules.embedded_charts:
        if active_modules.spend_breakdown:
            spend_bytes = charts.generate_spend_chart(charging, theme=theme, as_bytes=True)
            tou_bytes = charts.generate_tou_chart(
                charging["hourly_kwh"],
                config.rates.off_peak_start_hour,
                config.rates.off_peak_end_hour,
                config.rates.peak_start_hour,
                config.rates.peak_end_hour,
                theme=theme,
                as_bytes=True
            )
        else:
            spend_bytes = b""
            tou_bytes = b""

        if show_battery_health:
            battery_bytes = charts.generate_battery_trend_chart(battery, theme=theme, as_bytes=True, unit=units["length"])
        else:
            battery_bytes = b""

        solar_bytes = b""
        if getattr(active_modules, "solar_production", True) and solar.get("has_data"):
            try:
                solar_bytes = charts.generate_solar_chart(solar, theme=theme, as_bytes=True)
            except Exception as e:
                print(f"[Report] Error generating solar chart: {e}")

        if for_email:
            if spend_bytes:
                inline_images["chart_spend"] = spend_bytes
                chart_spend_src = "cid:chart_spend"
            if tou_bytes:
                inline_images["chart_tou"] = tou_bytes
                chart_tou_src = "cid:chart_tou"
            if show_battery_health and battery_bytes:
                inline_images["chart_battery"] = battery_bytes
                chart_battery_src = "cid:chart_battery"
            if solar_bytes:
                inline_images["chart_solar"] = solar_bytes
                chart_solar_src = "cid:chart_solar"
        else:
            import base64
            if spend_bytes:
                chart_spend_src = f"data:image/png;base64,{base64.b64encode(spend_bytes).decode('utf-8')}"
            if tou_bytes:
                chart_tou_src = f"data:image/png;base64,{base64.b64encode(tou_bytes).decode('utf-8')}"
            if show_battery_health and battery_bytes:
                chart_battery_src = f"data:image/png;base64,{base64.b64encode(battery_bytes).decode('utf-8')}"
            if solar_bytes:
                chart_solar_src = f"data:image/png;base64,{base64.b64encode(solar_bytes).decode('utf-8')}"

    env = get_jinja_env()
    custom_template_path = CUSTOM_TEMPLATES_DIR / "custom_digest.html"

    if chosen_theme == "custom" and custom_template_path.exists():
        try:
            tmpl = env.get_template("custom_digest.html")
        except Exception:
            with open(custom_template_path, "r") as f:
                tmpl = env.from_string(f.read())
    else:
        template_name = "digest.html"
        try:
            tmpl = env.get_template(template_name)
        except Exception:
            with open(TEMPLATES_DIR / "digest.html", "r") as f:
                tmpl = env.from_string(f.read())

    dashboard_url = getattr(config, "dashboard_url", None) or f"http://localhost:{os.getenv('PORT', '8660')}"
    teslamate_url, grafana_url = await get_effective_service_urls(db, config)
    grafana_dashboards = get_grafana_dashboard_urls(grafana_url, car_id, getattr(config, "grafana_dashboards", None))
    ha_url = (ha_cfg.url if ha_cfg and ha_cfg.enabled else "").rstrip("/")

    html_content = tmpl.render(
        report_title=report_title,
        date_subtitle=date_subtitle,
        car_subtitle=car_subtitle,
        car_badge=car_badge,
        period_label=period_label,
        one_line_summary=one_line_summary,
        preheader_text=preheader_text,
        generation_timestamp=generation_timestamp,
        insights=insights,
        units=units,
        trips=trips,
        charging=charging,
        solar=solar,
        superchargers=superchargers,
        battery=battery,
        health=health,
        vampire=vampire,
        efficiency=efficiency,
        compliance=compliance,
        work_mileage=work_mileage,
        achievements=achievements,
        show_battery_health=show_battery_health,
        modules=active_modules,
        rates=config.rates,
        chart_spend=chart_spend_src,
        chart_tou=chart_tou_src,
        chart_battery=chart_battery_src,
        chart_solar=chart_solar_src,
        dashboard_url=dashboard_url,
        teslamate_url=teslamate_url,
        grafana_url=grafana_url,
        homeassistant_url=ha_url,
        theme=theme,
        **grafana_dashboards
    )

    res = (subject, html_content, inline_images)
    if not for_email:
        ttl = 3600 if (datetime.now() - end_date).total_seconds() > 86400 else 300
        report_cache.set(rep_key, res, ttl=ttl)

    return res


async def build_wrapped_report(
    db: Database,
    config: AppConfig,
    year: int,
    car_id: Optional[int] = None,
    for_email: bool = False,
    force_refresh: bool = False
) -> Tuple[str, str, Dict[str, bytes]]:
    """
    Builds the Spotify Wrapped / Year in Review report.
    """
    wrap_key = f"rep:wrapped:{year}:{car_id or 'all'}:{'email' if for_email else 'preview'}"
    if not force_refresh and not for_email:
        cached_wrap = report_cache.get(wrap_key)
        if cached_wrap is not None:
            return cached_wrap

    wrapped_data = await get_year_in_review_analytics(db, year, car_id, config.rates, config.excluded_locations)

    env = get_jinja_env()
    try:
        tmpl = env.get_template("wrapped.html")
    except Exception:
        with open(TEMPLATES_DIR / "wrapped.html", "r") as f:
            tmpl = env.from_string(f.read())

    subject = f"🎉 Tesla Wrapped {year}: Your Year in Review!"
    html_content = tmpl.render(**wrapped_data)
    res = (subject, html_content, {})
    if not for_email:
        report_cache.set(wrap_key, res, ttl=3600)

    return res

