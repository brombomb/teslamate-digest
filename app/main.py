from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    load_config,
    save_config,
    load_maintenance_log,
    save_maintenance_log,
    AppConfig
)
from app.db import Database
from app.scheduler import (
    setup_scheduler,
    scheduler,
    get_scheduler_status,
    run_scheduled_digest
)
from app.report import build_digest_report, build_wrapped_report
from app.mailer import Mailer
from app.services.gas_prices import fetch_gas_price_details
from app.services.electric_rates import fetch_electric_rates

BASE_DIR = Path(__file__).resolve().parent
WEB_TEMPLATES_DIR = BASE_DIR / "templates" / "web"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(WEB_TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    cfg = load_config()
    db = Database(cfg)
    try:
        await db.connect()
        app.state.db = db
        print("[App] Connected to TeslaMate PostgreSQL.")
    except Exception as e:
        print(f"[App] Warning: Could not connect to DB at startup: {e}")

    setup_scheduler(cfg)
    scheduler.start()
    print("[App] Scheduler running.")
    yield
    # Shutdown
    scheduler.shutdown()
    if hasattr(app.state, "db") and app.state.db:
        await app.state.db.disconnect()
    print("[App] Shutdown complete.")


app = FastAPI(title="TeslaMate Digest", version="1.0.0", lifespan=lifespan)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "teslamate-digest"}


@app.post("/api/sync-gas-price")
async def sync_gas_price(request: Request):
    cfg = load_config()
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    zip_code = data.get("zip_code") or cfg.rates.zip_code or "80005"
    eia_key = data.get("eia_api_key") or cfg.rates.eia_api_key

    details = await fetch_gas_price_details(
        zip_code=zip_code,
        api_key=eia_key,
        fallback=cfg.rates.gas_price_per_gal,
        force_refresh=True
    )
    cfg.rates.gas_price_per_gal = float(details.get("price", cfg.rates.gas_price_per_gal))
    if "area_name" in details:
        cfg.rates.zip_code = zip_code
    save_config(cfg)

    return JSONResponse(content={
        "success": True,
        "price": details.get("price"),
        "period": details.get("period"),
        "area_name": details.get("area_name"),
        "source": details.get("source"),
        "is_live": details.get("is_live", True)
    })


@app.post("/api/sync-electric-rates")
async def sync_electric_rates(request: Request):
    cfg = load_config()
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    zip_code = data.get("zip_code") or cfg.rates.zip_code or "80005"
    openei_key = data.get("openei_api_key") or cfg.rates.openei_api_key
    eia_key = data.get("eia_api_key") or cfg.rates.eia_api_key

    rates = await fetch_electric_rates(
        zip_code=zip_code,
        openei_api_key=openei_key,
        eia_api_key=eia_key,
        force_refresh=True
    )

    cfg.rates.off_peak_kwh_cost = float(rates.get("off_peak_kwh_cost", cfg.rates.off_peak_kwh_cost))
    cfg.rates.shoulder_kwh_cost = float(rates.get("shoulder_kwh_cost", cfg.rates.shoulder_kwh_cost))
    cfg.rates.on_peak_kwh_cost = float(rates.get("on_peak_kwh_cost", cfg.rates.on_peak_kwh_cost))
    cfg.rates.off_peak_start_hour = int(rates.get("off_peak_start_hour", cfg.rates.off_peak_start_hour))
    cfg.rates.off_peak_end_hour = int(rates.get("off_peak_end_hour", cfg.rates.off_peak_end_hour))
    cfg.rates.peak_start_hour = int(rates.get("peak_start_hour", cfg.rates.peak_start_hour))
    cfg.rates.peak_end_hour = int(rates.get("peak_end_hour", cfg.rates.peak_end_hour))
    cfg.rates.weekends_are_off_peak = bool(rates.get("weekends_are_off_peak", True))
    cfg.rates.utility_name = rates.get("utility_name", cfg.rates.utility_name)
    save_config(cfg)

    return JSONResponse(content={
        "success": True,
        "rates": rates
    })


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cfg = load_config()
    db: Database = request.app.state.db
    cars = await db.get_cars()
    sched_status = get_scheduler_status()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "active_nav": "dashboard",
            "config": cfg,
            "cars": cars,
            "scheduler_status": sched_status
        }
    )


@app.get("/preview", response_class=HTMLResponse)
async def preview(
    request: Request,
    period: str = Query("last_month"),
    car_id: Optional[str] = Query(None),
    sent: Optional[str] = Query(None)
):
    cfg = load_config()
    db: Database = request.app.state.db
    cars = await db.get_cars()
    now = datetime.now()

    cid = int(car_id) if car_id and car_id.isdigit() else None

    rendered_html = ""
    subject = ""

    if period == "wrapped":
        year = now.year
        subject, rendered_html, _ = await build_wrapped_report(
            db=db,
            config=cfg,
            year=year,
            car_id=cid,
            for_email=False
        )
    else:
        if period == "this_month":
            start_date = datetime(now.year, now.month, 1, 0, 0, 0)
            end_date = now
        elif period == "last_week":
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=7)
        elif period == "yesterday":
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=1)
        else:  # last_month (default)
            first_of_this_month = datetime(now.year, now.month, 1)
            last_day_of_prev = first_of_this_month - timedelta(days=1)
            start_date = datetime(last_day_of_prev.year, last_day_of_prev.month, 1, 0, 0, 0)
            end_date = first_of_this_month

        subject, rendered_html, _ = await build_digest_report(
            db=db,
            config=cfg,
            start_date=start_date,
            end_date=end_date,
            car_id=cid,
            for_email=False  # Base64 embedded charts for browser iframe
        )

    send_status = None
    if sent == "success":
        send_status = {"success": True, "message": f"Test digest dispatched to {cfg.smtp.recipient_email}!"}
    elif sent == "failed":
        err_text = request.query_params.get("err", "Check SMTP settings and app password.")
        send_status = {"success": False, "message": f"Failed to send email: {err_text}"}

    return templates.TemplateResponse(
        "preview.html",
        {
            "request": request,
            "active_nav": "preview",
            "config": cfg,
            "cars": cars,
            "period": period,
            "car_id": car_id,
            "subject": subject,
            "rendered_html": rendered_html,
            "send_status": send_status
        }
    )


@app.post("/api/send-test")
async def send_test(
    request: Request,
    period: str = Form("last_month"),
    car_id: Optional[str] = Form(None)
):
    cfg = load_config()
    db: Database = request.app.state.db
    now = datetime.now()
    cid = int(car_id) if car_id and car_id.isdigit() else None

    try:
        if period == "wrapped":
            subject, html, inline_imgs = await build_wrapped_report(
                db=db, config=cfg, year=now.year, car_id=cid, for_email=True
            )
        else:
            if period == "this_month":
                start_date = datetime(now.year, now.month, 1, 0, 0, 0)
                end_date = now
            elif period == "last_week":
                end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
                start_date = end_date - timedelta(days=7)
            elif period == "yesterday":
                end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
                start_date = end_date - timedelta(days=1)
            else:
                first_of_this_month = datetime(now.year, now.month, 1)
                last_day_of_prev = first_of_this_month - timedelta(days=1)
                start_date = datetime(last_day_of_prev.year, last_day_of_prev.month, 1, 0, 0, 0)
                end_date = first_of_this_month

            subject, html, inline_imgs = await build_digest_report(
                db=db, config=cfg, start_date=start_date, end_date=end_date, car_id=cid, for_email=True
            )

        mailer = Mailer(cfg.smtp)
        mailer.send_email(subject=subject, html_content=html, inline_images=inline_imgs)
        return RedirectResponse(url=f"/preview?period={period}&car_id={car_id or ''}&sent=success", status_code=303)
    except Exception as e:
        import urllib.parse
        err_msg = urllib.parse.quote(str(e))
        print(f"[API] Error sending test: {e}")
        return RedirectResponse(url=f"/preview?period={period}&car_id={car_id or ''}&sent=failed&err={err_msg}", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    cfg = load_config()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_nav": "settings",
            "config": cfg,
            "message": None
        }
    )

@app.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    smtp_enabled: Optional[str] = Form(None),
    smtp_host: str = Form("smtp.gmail.com"),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    recipient_email: str = Form(""),
    sender_name: str = Form("TeslaMate Digest"),
    tariff_preset: str = Form("xcel_colorado_tou"),
    average_kwh_cost: float = Form(0.11),
    off_peak_kwh_cost: float = Form(0.09),
    shoulder_kwh_cost: float = Form(0.13),
    on_peak_kwh_cost: float = Form(0.19),
    off_peak_start_hour: int = Form(21),
    off_peak_end_hour: int = Form(9),
    peak_start_hour: int = Form(13),
    peak_end_hour: int = Form(19),
    weekends_are_off_peak: Optional[str] = Form(None),
    supercharger_fallback_cost: float = Form(0.36),
    zip_code: str = Form("80005"),
    gas_price_per_gal: float = Form(4.00),
    baseline_ice_mpg: float = Form(26.0),
    eia_api_key: str = Form(""),
    openei_api_key: str = Form(""),
    utility_name: str = Form("Public Service Co of Colorado (Xcel Energy)"),
    dashboard_url: str = Form("http://localhost:8660"),
    excluded_locations: str = Form("West 87th Terrace, Home"),
    tire_rotation_interval_mi: int = Form(6250),
    schedule_enabled: Optional[str] = Form(None),
    frequency: str = Form("monthly"),
    send_hour: int = Form(8),
    send_minute: int = Form(0),
    mod_spend_breakdown: Optional[str] = Form(None),
    mod_gas_savings: Optional[str] = Form(None),
    mod_battery_health: Optional[str] = Form(None),
    mod_supercharger_explorer: Optional[str] = Form(None),
    mod_top_locations: Optional[str] = Form(None),
    mod_driving_milestones: Optional[str] = Form(None),
    mod_colorado_mountain_regen: Optional[str] = Form(None),
    mod_vampire_drain: Optional[str] = Form(None),
    mod_maintenance_alerts: Optional[str] = Form(None),
    mod_snow_tire_reminder: Optional[str] = Form(None),
    mod_embedded_charts: Optional[str] = Form(None),
):
    cfg = load_config()

    cfg.smtp.enabled = bool(smtp_enabled)
    cfg.smtp.host = smtp_host
    cfg.smtp.port = smtp_port
    cfg.smtp.user = smtp_user
    if smtp_password.strip():
        cfg.smtp.password = smtp_password.strip()
    cfg.smtp.sender_email = smtp_user
    cfg.smtp.recipient_email = recipient_email
    cfg.smtp.sender_name = sender_name

    cfg.dashboard_url = dashboard_url.strip() or "http://localhost:8660"
    cfg.excluded_locations = [x.strip() for x in excluded_locations.split(",") if x.strip()]

    cfg.rates.tariff_preset = tariff_preset
    cfg.rates.average_kwh_cost = average_kwh_cost
    cfg.rates.off_peak_kwh_cost = off_peak_kwh_cost
    cfg.rates.shoulder_kwh_cost = shoulder_kwh_cost
    cfg.rates.on_peak_kwh_cost = on_peak_kwh_cost
    cfg.rates.off_peak_start_hour = off_peak_start_hour
    cfg.rates.off_peak_end_hour = off_peak_end_hour
    cfg.rates.peak_start_hour = peak_start_hour
    cfg.rates.peak_end_hour = peak_end_hour
    cfg.rates.weekends_are_off_peak = bool(weekends_are_off_peak)
    cfg.rates.supercharger_fallback_cost = supercharger_fallback_cost
    cfg.rates.zip_code = zip_code
    cfg.rates.gas_price_per_gal = gas_price_per_gal
    cfg.rates.baseline_ice_mpg = baseline_ice_mpg
    cfg.rates.eia_api_key = eia_api_key.strip()
    cfg.rates.openei_api_key = openei_api_key.strip()
    cfg.rates.utility_name = utility_name.strip()
    cfg.tire_rotation_interval_mi = tire_rotation_interval_mi

    cfg.schedule.enabled = bool(schedule_enabled)
    cfg.schedule.frequency = frequency
    cfg.schedule.send_hour = send_hour
    cfg.schedule.send_minute = send_minute

    cfg.modules.spend_breakdown = bool(mod_spend_breakdown)
    cfg.modules.gas_savings = bool(mod_gas_savings)
    cfg.modules.battery_health = bool(mod_battery_health)
    cfg.modules.supercharger_explorer = bool(mod_supercharger_explorer)
    cfg.modules.top_locations = bool(mod_top_locations)
    cfg.modules.driving_milestones = bool(mod_driving_milestones)
    cfg.modules.colorado_mountain_regen = bool(mod_colorado_mountain_regen)
    cfg.modules.vampire_drain = bool(mod_vampire_drain)
    cfg.modules.maintenance_alerts = bool(mod_maintenance_alerts)
    cfg.modules.snow_tire_reminder = bool(mod_snow_tire_reminder)
    cfg.modules.embedded_charts = bool(mod_embedded_charts)

    save_config(cfg)
    setup_scheduler(cfg)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_nav": "settings",
            "config": cfg,
            "message": "Settings updated and saved successfully!"
        }
    )


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_view(request: Request, msg: Optional[str] = Query(None)):
    db: Database = request.app.state.db
    cars = await db.get_cars()
    log = load_maintenance_log()
    cfg = load_config()

    car_statuses = []
    for c in cars:
        cid = c["id"]
        latest_pos = await db.fetchrow(
            "SELECT coalesce(odometer, 0) * 0.621371 as odometer_mi FROM positions WHERE car_id = $1 ORDER BY date DESC LIMIT 1;",
            cid
        )
        curr_odo = round(float(latest_pos["odometer_mi"]), 1) if latest_pos else 0.0
        m = log.get(str(cid), {})
        last_rot_odo = float(m.get("last_tire_rotation_odometer", 0))
        last_rot_date = m.get("last_tire_rotation_date", "")
        active_set = m.get("active_tire_set", "all_season")
        last_swap_date = m.get("last_tire_swap_date", "")
        notes = m.get("notes", "")

        miles_since = round(max(0.0, curr_odo - last_rot_odo), 1) if last_rot_odo > 0 else 0.0
        interval = cfg.tire_rotation_interval_mi
        miles_remaining = max(0.0, interval - miles_since)
        life_remaining_pct = max(0.0, min(100.0, round(((interval - miles_since) / interval) * 100.0, 1))) if interval > 0 else 100.0
        is_overdue = miles_since >= interval

        car_statuses.append({
            "id": cid,
            "name": c["name"],
            "model": c["model"],
            "current_odometer": curr_odo,
            "last_tire_rotation_odometer": last_rot_odo,
            "last_tire_rotation_date": last_rot_date,
            "miles_since": miles_since,
            "miles_remaining": miles_remaining,
            "life_remaining_pct": life_remaining_pct,
            "is_overdue": is_overdue,
            "active_tire_set": active_set,
            "last_tire_swap_date": last_swap_date,
            "notes": notes,
        })

    flash_message = None
    if msg == "rotated":
        flash_message = "✅ Tires marked as rotated today! Tread life reset to 100%."
    elif msg == "swapped":
        flash_message = "✅ Seasonal tire set updated successfully!"

    return templates.TemplateResponse(
        "maintenance.html",
        {
            "request": request,
            "active_nav": "maintenance",
            "cars": car_statuses,
            "log": log,
            "message": flash_message
        }
    )


@app.post("/maintenance/quick-rotate")
async def quick_rotate(request: Request, car_id: str = Form(...)):
    db: Database = request.app.state.db
    latest_pos = await db.fetchrow(
        "SELECT coalesce(odometer, 0) * 0.621371 as odometer_mi FROM positions WHERE car_id = $1 ORDER BY date DESC LIMIT 1;",
        int(car_id)
    )
    curr_odo = round(float(latest_pos["odometer_mi"]), 1) if latest_pos else 0.0
    log = load_maintenance_log()
    cid_str = str(car_id)
    if cid_str not in log:
        log[cid_str] = {}
    log[cid_str]["last_tire_rotation_odometer"] = curr_odo
    log[cid_str]["last_tire_rotation_date"] = datetime.now().strftime("%Y-%m-%d")
    save_maintenance_log(log)
    return RedirectResponse(url="/maintenance?msg=rotated", status_code=303)


@app.post("/maintenance/swap-tires")
async def swap_tires(request: Request, car_id: str = Form(...), target_set: str = Form(...)):
    log = load_maintenance_log()
    cid_str = str(car_id)
    if cid_str not in log:
        log[cid_str] = {}
    log[cid_str]["active_tire_set"] = target_set
    log[cid_str]["last_tire_swap_date"] = datetime.now().strftime("%Y-%m-%d")
    save_maintenance_log(log)
    return RedirectResponse(url="/maintenance?msg=swapped", status_code=303)


@app.post("/maintenance", response_class=HTMLResponse)
async def maintenance_save(
    request: Request,
    car_id: str = Form(...),
    last_tire_rotation_odometer: float = Form(0),
    last_tire_rotation_date: str = Form(""),
    active_tire_set: str = Form("all_season"),
    last_tire_swap_date: str = Form(""),
    notes: str = Form("")
):
    db: Database = request.app.state.db
    log = load_maintenance_log()
    cid_str = str(car_id)
    if cid_str not in log:
        log[cid_str] = {}

    log[cid_str]["last_tire_rotation_odometer"] = last_tire_rotation_odometer
    log[cid_str]["last_tire_rotation_date"] = last_tire_rotation_date
    log[cid_str]["active_tire_set"] = active_tire_set
    log[cid_str]["last_tire_swap_date"] = last_tire_swap_date
    log[cid_str]["notes"] = notes
    save_maintenance_log(log)

    return RedirectResponse(url="/maintenance?msg=saved", status_code=303)

