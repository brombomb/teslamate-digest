from datetime import datetime, timedelta
import calendar
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import AppConfig, load_config, ScheduleItem
from app.db import Database
from app.mailer import Mailer
from app.report import build_digest_report

scheduler = AsyncIOScheduler()
last_run_info = {
    "timestamp": None,
    "status": "Idle",
    "details": "Scheduler initialized."
}


async def run_scheduled_digest(schedule_id: Optional[str] = None, frequency: Optional[str] = None):
    global last_run_info
    config = load_config()
    db = Database(config)

    # Resolve schedule configuration
    sched_item: Optional[ScheduleItem] = None
    if schedule_id:
        sched_item = next((s for s in config.schedules if s.id == schedule_id), None)
    
    if not sched_item:
        if config.schedules:
            sched_item = config.schedules[0]
        else:
            sched_item = ScheduleItem(
                id="default",
                name="Scheduled Digest",
                frequency=frequency or getattr(config.schedule, "frequency", "monthly"),
                target_car_id=getattr(config.schedule, "target_car_id", None),
                theme=getattr(config, "email_theme", "pearl_white")
            )

    freq = frequency or sched_item.frequency
    theme = sched_item.theme or getattr(config, "email_theme", "pearl_white")
    car_id = sched_item.target_car_id
    recipient = sched_item.recipient_email.strip() or config.smtp.recipient_email

    now = datetime.now()
    sched_label = f"[{sched_item.name}] ({freq})"
    print(f"[Scheduler] Triggered {sched_label} at {now.isoformat()} (Theme: {theme}, Target: {car_id or 'Fleet'})")
    last_run_info["timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S")
    last_run_info["status"] = "Running"

    try:
        await db.connect()

        # Calculate time window
        if freq == "monthly":
            first_of_this_month = datetime(now.year, now.month, 1)
            last_day_of_prev_month = first_of_this_month - timedelta(days=1)
            start_date = datetime(last_day_of_prev_month.year, last_day_of_prev_month.month, 1, 0, 0, 0)
            end_date = datetime(first_of_this_month.year, first_of_this_month.month, 1, 0, 0, 0)
        elif freq == "semi-monthly":
            if now.day <= 15:
                start_date = datetime(now.year, now.month, 1, 0, 0, 0)
                end_date = datetime(now.year, now.month, 15, 23, 59, 59)
            else:
                first_of_this_month = datetime(now.year, now.month, 1)
                last_day_of_prev_month = first_of_this_month - timedelta(days=1)
                start_date = datetime(last_day_of_prev_month.year, last_day_of_prev_month.month, 16, 0, 0, 0)
                end_date = datetime(first_of_this_month.year, first_of_this_month.month, 1, 0, 0, 0)
        elif freq == "bi-weekly":
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=14)
        elif freq == "weekly":
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=7)
        else:  # daily
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=1)

        # Build report with schedule-specific theme and car_id
        subject, html, inline_images = await build_digest_report(
            db=db,
            config=config,
            start_date=start_date,
            end_date=end_date,
            car_id=car_id,
            theme_override=theme,
            for_email=True
        )

        mailer = Mailer(config.smtp)
        success = mailer.send_email(
            subject=subject,
            html_content=html,
            inline_images=inline_images,
            recipient=recipient
        )

        if success:
            last_run_info["status"] = "Success"
            target_desc = f"Car #{car_id}" if car_id else "All Cars (Fleet)"
            last_run_info["details"] = f"Delivered {sched_item.name} ({freq}, {target_desc}, Theme: {theme}) to {recipient}"
        else:
            last_run_info["status"] = "Skipped"
            last_run_info["details"] = "Delivery skipped (SMTP disabled or password missing)."

    except Exception as e:
        last_run_info["status"] = "Failed"
        last_run_info["details"] = f"Error during dispatch of {sched_item.name}: {e}"
        print(f"[Scheduler] Error: {e}")
    finally:
        await db.disconnect()


def setup_scheduler(config: AppConfig):
    scheduler.remove_all_jobs()
    
    if not config.schedules:
        print("[Scheduler] No schedules configured.")
        return

    active_count = 0
    for s in config.schedules:
        if not s.enabled:
            continue

        freq = s.frequency
        hour = s.send_hour
        minute = s.send_minute
        day_of_week = s.day_of_week
        day_of_month = s.day_of_month

        if freq == "monthly":
            trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute)
        elif freq == "semi-monthly":
            trigger = CronTrigger(day=f"{day_of_month},{min(28, day_of_month + 14)}", hour=hour, minute=minute)
        elif freq == "bi-weekly":
            # Runs on day_of_week (0=Mon .. 6=Sun)
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
        elif freq == "weekly":
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
        else:  # Daily
            trigger = CronTrigger(hour=hour, minute=minute)

        job_id = f"sched_{s.id}"
        scheduler.add_job(
            run_scheduled_digest,
            trigger=trigger,
            id=job_id,
            args=[s.id],
            replace_existing=True
        )
        active_count += 1
        print(f"[Scheduler] Configured job '{s.name}' ({freq}) at {hour:02d}:{minute:02d} (Theme: {s.theme}, Target: {s.target_car_id or 'Fleet'})")

    print(f"[Scheduler] Configured {active_count} active automated email schedule(s).")


def get_scheduler_status():
    jobs = scheduler.get_jobs()
    job_statuses = []
    for j in jobs:
        next_run = j.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if j.next_run_time else "Not scheduled"
        job_statuses.append({
            "id": j.id,
            "next_run": next_run
        })

    next_run_summary = job_statuses[0]["next_run"] if job_statuses else "No active schedules"

    return {
        "is_running": scheduler.running,
        "next_run": next_run_summary,
        "active_jobs_count": len(jobs),
        "jobs": job_statuses,
        "last_run": last_run_info
    }
