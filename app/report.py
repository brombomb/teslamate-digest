import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from jinja2 import Environment, FileSystemLoader

from app.db import Database
from app.config import AppConfig
from app.analytics.charging import get_charging_analytics
from app.analytics.trips import get_trip_analytics
from app.analytics.superchargers import get_supercharger_analytics
from app.analytics.battery import get_battery_health_analytics
from app.analytics.health import get_health_analytics
from app.analytics.vampire import get_vampire_analytics
from app.analytics.wrapped import get_year_in_review_analytics
import app.charts as charts

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates" / "email"
CUSTOM_TEMPLATES_DIR = Path("/app/custom_templates")


def get_jinja_env() -> Environment:
    loaders = []
    if CUSTOM_TEMPLATES_DIR.exists():
        loaders.append(FileSystemLoader(str(CUSTOM_TEMPLATES_DIR)))
    loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
    return Environment(loader=loaders[0] if len(loaders) == 1 else FileSystemLoader([str(CUSTOM_TEMPLATES_DIR), str(TEMPLATES_DIR)]))


async def build_digest_report(
    db: Database,
    config: AppConfig,
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int] = None,
    for_email: bool = False
) -> Tuple[str, str, Dict[str, bytes]]:
    """
    Builds the complete digest HTML and charts.
    Returns: (subject, html_content, inline_image_dict)
    """
    # 1. Fetch data
    trips = await get_trip_analytics(db, start_date, end_date, car_id)
    charging = await get_charging_analytics(db, start_date, end_date, car_id, config.rates, trips["total_miles"])
    superchargers = await get_supercharger_analytics(db, start_date, end_date, car_id)
    battery = await get_battery_health_analytics(db, end_date, car_id)
    health = await get_health_analytics(db, start_date, end_date, car_id, config.tire_rotation_interval_mi)
    vampire = await get_vampire_analytics(db, start_date, end_date, car_id, config.rates.average_kwh_cost)

    cars = await db.get_cars()
    car_name = "Fleet"
    if car_id:
        for c in cars:
            if c["id"] == car_id:
                car_name = f"{c['name']} (Model {c['model']})"
                break

    # Determine titles
    is_monthly = (end_date - start_date).days >= 27 and (end_date - start_date).days <= 32
    if is_monthly:
        report_title = start_date.strftime("%B %Y") + " Report"
    else:
        report_title = f"Report ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"

    date_subtitle = f"{start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}"
    car_subtitle = car_name

    subject = f"⚡ TeslaMate Digest: {report_title} [{car_name}]"

    # 2. Charts Generation
    inline_images: Dict[str, bytes] = {}
    chart_spend_src = ""
    chart_tou_src = ""
    chart_battery_src = ""

    if config.modules.embedded_charts:
        spend_bytes = charts.generate_spend_chart(charging, as_bytes=True)
        tou_bytes = charts.generate_tou_chart(
            charging["hourly_kwh"],
            config.rates.off_peak_start_hour,
            config.rates.off_peak_end_hour,
            as_bytes=True
        )
        battery_bytes = charts.generate_battery_trend_chart(battery, as_bytes=True)

        if for_email:
            inline_images["chart_spend"] = spend_bytes
            inline_images["chart_tou"] = tou_bytes
            inline_images["chart_battery"] = battery_bytes
            chart_spend_src = "cid:chart_spend"
            chart_tou_src = "cid:chart_tou"
            chart_battery_src = "cid:chart_battery"
        else:
            import base64
            chart_spend_src = f"data:image/png;base64,{base64.b64encode(spend_bytes).decode('utf-8')}"
            chart_tou_src = f"data:image/png;base64,{base64.b64encode(tou_bytes).decode('utf-8')}"
            chart_battery_src = f"data:image/png;base64,{base64.b64encode(battery_bytes).decode('utf-8')}"

    # 3. Render Template
    env = get_jinja_env()
    # Check if custom template exists
    template_name = "digest.html"
    try:
        tmpl = env.get_template(template_name)
    except Exception:
        # Fallback to direct file loading
        with open(TEMPLATES_DIR / "digest.html", "r") as f:
            from jinja2 import Template
            tmpl = Template(f.read())

    dashboard_url = f"http://localhost:{os.getenv('PORT', '8660')}"

    html_content = tmpl.render(
        report_title=report_title,
        date_subtitle=date_subtitle,
        car_subtitle=car_subtitle,
        trips=trips,
        charging=charging,
        superchargers=superchargers,
        battery=battery,
        health=health,
        vampire=vampire,
        modules=config.modules,
        rates=config.rates,
        chart_spend=chart_spend_src,
        chart_tou=chart_tou_src,
        chart_battery=chart_battery_src,
        dashboard_url=dashboard_url
    )

    return subject, html_content, inline_images


async def build_wrapped_report(
    db: Database,
    config: AppConfig,
    year: int,
    car_id: Optional[int] = None,
    for_email: bool = False
) -> Tuple[str, str, Dict[str, bytes]]:
    """
    Builds the Spotify Wrapped / Year in Review report.
    """
    wrapped_data = await get_year_in_review_analytics(db, year, car_id, config.rates)

    env = get_jinja_env()
    try:
        tmpl = env.get_template("wrapped.html")
    except Exception:
        with open(TEMPLATES_DIR / "wrapped.html", "r") as f:
            from jinja2 import Template
            tmpl = Template(f.read())

    subject = f"🎉 Tesla Wrapped {year}: Your Year in Review!"
    html_content = tmpl.render(**wrapped_data)

    return subject, html_content, {}
