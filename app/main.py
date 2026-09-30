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
        send_status = {"success": False, "message": "Failed to send email. Check SMTP settings and app password."}

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
        print(f"[API] Error sending test: {e}")
        return RedirectResponse(url=f"/preview?period={period}&car_id={car_id or ''}&sent=failed", status_code=303)


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
    average_kwh_cost: float = Form(0.11),
    off_peak_kwh_cost: float = Form(0.09),
    on_peak_kwh_cost: float = Form(0.16),
    off_peak_start_hour: int = Form(21),
    off_peak_end_hour: int = Form(9),
    supercharger_fallback_cost: float = Form(0.36),
    gas_price_per_gal: float = Form(3.50),
    baseline_ice_mpg: float = Form(26.0),
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

    cfg.rates.average_kwh_cost = average_kwh_cost
    cfg.rates.off_peak_kwh_cost = off_peak_kwh_cost
    cfg.rates.on_peak_kwh_cost = on_peak_kwh_cost
    cfg.rates.off_peak_start_hour = off_peak_start_hour
    cfg.rates.off_peak_end_hour = off_peak_end_hour
    cfg.rates.supercharger_fallback_cost = supercharger_fallback_cost
    cfg.rates.gas_price_per_gal = gas_price_per_gal
    cfg.rates.baseline_ice_mpg = baseline_ice_mpg
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
async def maintenance_view(request: Request):
    db: Database = request.app.state.db
    cars = await db.get_cars()
    log = load_maintenance_log()

    return templates.TemplateResponse(
        "maintenance.html",
        {
            "request": request,
            "active_nav": "maintenance",
            "cars": cars,
            "log": log,
            "message": None
        }
    )


@app.post("/maintenance", response_class=HTMLResponse)
async def maintenance_save(
    request: Request,
    car_id: str = Form(...),
    last_tire_rotation_odometer: float = Form(0),
    last_tire_rotation_date: str = Form(""),
    notes: str = Form("")
):
    db: Database = request.app.state.db
    cars = await db.get_cars()
    log = load_maintenance_log()

    log[str(car_id)] = {
        "last_tire_rotation_odometer": last_tire_rotation_odometer,
        "last_tire_rotation_date": last_tire_rotation_date,
        "notes": notes
    }
    save_maintenance_log(log)

    return templates.TemplateResponse(
        "maintenance.html",
        {
            "request": request,
            "active_nav": "maintenance",
            "cars": cars,
            "log": log,
            "message": "Maintenance log updated successfully!"
        }
    )
