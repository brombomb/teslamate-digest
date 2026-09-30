from datetime import datetime, timedelta
import calendar
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import AppConfig, load_config
from app.db import Database
from app.mailer import Mailer
from app.report import build_digest_report

scheduler = AsyncIOScheduler()
last_run_info = {
    "timestamp": None,
    "status": "Idle",
    "details": "Scheduler initialized."
}


async def run_scheduled_digest(frequency: Optional[str] = None):
    global last_run_info
    config = load_config()
    db = Database(config)
    freq = frequency or config.schedule.frequency

    now = datetime.now()
    print(f"[Scheduler] Triggered {freq} digest run at {now.isoformat()}")
    last_run_info["timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S")
    last_run_info["status"] = "Running"

    try:
        await db.connect()

        # Calculate time window
        if freq == "monthly":
            # Previous month
            first_of_this_month = datetime(now.year, now.month, 1)
            last_day_of_prev_month = first_of_this_month - timedelta(days=1)
            start_date = datetime(last_day_of_prev_month.year, last_day_of_prev_month.month, 1, 0, 0, 0)
            end_date = datetime(first_of_this_month.year, first_of_this_month.month, 1, 0, 0, 0)
        elif freq == "weekly":
            # Last 7 days
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=7)
        else:
            # Daily (yesterday)
            end_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_date = end_date - timedelta(days=1)

        # Build report
        subject, html, inline_images = await build_digest_report(
            db=db,
            config=config,
            start_date=start_date,
            end_date=end_date,
            car_id=None,  # Fleet
            for_email=True
        )

        mailer = Mailer(config.smtp)
        success = mailer.send_email(
            subject=subject,
            html_content=html,
            inline_images=inline_images
        )

        if success:
            last_run_info["status"] = "Success"
            last_run_info["details"] = f"Delivered {freq} digest to {config.smtp.recipient_email}"
        else:
            last_run_info["status"] = "Skipped"
            last_run_info["details"] = "Delivery skipped (SMTP disabled or password missing)."

    except Exception as e:
        last_run_info["status"] = "Failed"
        last_run_info["details"] = f"Error during dispatch: {e}"
        print(f"[Scheduler] Error: {e}")
    finally:
        await db.disconnect()


def setup_scheduler(config: AppConfig):
    scheduler.remove_all_jobs()
    if not config.schedule.enabled:
        print("[Scheduler] Automated schedule is currently disabled.")
        return

    freq = config.schedule.frequency
    hour = config.schedule.send_hour
    minute = config.schedule.send_minute

    if freq == "monthly":
        trigger = CronTrigger(day=config.schedule.send_day_of_month, hour=hour, minute=minute)
    elif freq == "weekly":
        trigger = CronTrigger(day_of_week=config.schedule.send_day_of_week, hour=hour, minute=minute)
    else:  # Daily
        trigger = CronTrigger(hour=hour, minute=minute)

    scheduler.add_job(
        run_scheduled_digest,
        trigger=trigger,
        id="scheduled_digest",
        replace_existing=True
    )
    print(f"[Scheduler] Configured {freq} digest job for {hour:02d}:{minute:02d}")


def get_scheduler_status():
    job = scheduler.get_job("scheduled_digest")
    next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job and job.next_run_time else "Not scheduled"
    return {
        "is_running": scheduler.running,
        "next_run": next_run,
        "last_run": last_run_info
    }
