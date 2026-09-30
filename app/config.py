import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
MAINTENANCE_FILE = DATA_DIR / "maintenance.json"


class SMTPSettings(BaseModel):
    enabled: bool = True
    host: str = "smtp.gmail.com"
    port: int = 587
    user: str = "brombomb@gmail.com"
    password: str = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    sender_email: str = "brombomb@gmail.com"
    sender_name: str = "TeslaMate Digest"
    recipient_email: str = "brombomb@gmail.com"
    use_tls: bool = True
    use_ssl: bool = False


class ScheduleSettings(BaseModel):
    enabled: bool = True
    frequency: str = "monthly"  # monthly, semi-monthly, bi-weekly, weekly, daily
    send_day_of_month: int = 1   # 1st of month (or 1st & 15th for semi-monthly)
    send_day_of_week: int = 0    # Monday (0)
    send_hour: int = 8           # 8:00 AM
    send_minute: int = 0
    target_car_id: Optional[int] = None  # None for Fleet (All Cars), or car_id integer


class RatesSettings(BaseModel):
    rate_mode: str = "tou"  # tou or flat
    tariff_preset: str = "xcel_colorado_tou"
    average_kwh_cost: float = 0.11
    off_peak_kwh_cost: float = 0.09
    shoulder_kwh_cost: float = 0.13
    on_peak_kwh_cost: float = 0.19
    off_peak_start_hour: int = 21  # 9 PM
    off_peak_end_hour: int = 9     # 9 AM
    peak_start_hour: int = 13      # 1 PM
    peak_end_hour: int = 19        # 7 PM
    weekends_are_off_peak: bool = True
    supercharger_fallback_cost: float = 0.36
    gas_price_per_gal: float = 4.00
    zip_code: str = "80005"
    auto_gas_price: bool = True
    baseline_ice_mpg: float = 26.0
    eia_api_key: str = ""
    openei_api_key: str = ""
    utility_name: str = "Public Service Co of Colorado (Xcel Energy)"
    gas_price_source: str = "eia"
    electric_rate_source: str = "openei"


class UnitSettings(BaseModel):
    length: str = "mi"       # mi or km
    temp: str = "F"          # F or C
    pressure: str = "psi"    # psi or bar
    currency: str = "$"


class WorkRouteItem(BaseModel):
    label: str
    point_a: str
    point_b: str
    bidirectional: bool = True


class ModuleToggles(BaseModel):
    spend_breakdown: bool = True
    gas_savings: bool = True
    battery_health: bool = True
    driving_efficiency: bool = True
    charge_limit_compliance: bool = True
    work_mileage: bool = True
    supercharger_explorer: bool = True
    top_locations: bool = True
    driving_milestones: bool = True
    colorado_mountain_regen: bool = True
    vampire_drain: bool = True
    maintenance_alerts: bool = True
    snow_tire_reminder: bool = True
    embedded_charts: bool = True


class AppConfig(BaseModel):
    database_host: str = Field(default_factory=lambda: os.getenv("DATABASE_HOST", "database"))
    database_port: int = Field(default_factory=lambda: int(os.getenv("DATABASE_PORT", "5432")))
    database_user: str = Field(default_factory=lambda: os.getenv("DATABASE_USER", "teslamate"))
    database_pass: str = Field(default_factory=lambda: os.getenv("DATABASE_PASS", "Curtly-Silty-7Strung-4Flesh-sinh2-ssss"))
    database_name: str = Field(default_factory=lambda: os.getenv("DATABASE_NAME", "teslamate"))
    timezone: str = Field(default_factory=lambda: os.getenv("TZ", "America/Denver"))
    grafana_url: str = Field(default_factory=lambda: os.getenv("GRAFANA_URL", "http://grafana:3000"))
    grafana_api_token: str = Field(default_factory=lambda: os.getenv("GRAFANA_API_TOKEN", ""))

    smtp: SMTPSettings = Field(default_factory=SMTPSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    rates: RatesSettings = Field(default_factory=RatesSettings)
    units: UnitSettings = Field(default_factory=UnitSettings)
    modules: ModuleToggles = Field(default_factory=ModuleToggles)
    tire_rotation_interval_mi: int = 6250
    dashboard_url: str = Field(default_factory=lambda: os.getenv("DASHBOARD_URL", "http://localhost:8660"))
    excluded_locations: list[str] = Field(default_factory=lambda: ["West 87th Terrace", "West 87th Drive", "Home"])
    email_theme: str = "dark_modern"  # dark_modern, clean_white, clean_black, eco_green, electric_blue, custom
    work_routes: list[WorkRouteItem] = Field(default_factory=list)
    irs_mileage_rate: float = 0.67


def load_config() -> AppConfig:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            cfg = AppConfig(**data)
            if not cfg.smtp.password and os.getenv("SMTP_PASSWORD"):
                cfg.smtp.password = os.getenv("SMTP_PASSWORD")
            return cfg
        except Exception as e:
            print(f"[Config] Error loading {CONFIG_FILE}: {e}. Using defaults.")
    
    cfg = AppConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg.model_dump(), f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving config: {e}")


def load_maintenance_log() -> Dict[str, Any]:
    if MAINTENANCE_FILE.exists():
        try:
            with open(MAINTENANCE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Maintenance] Error loading log: {e}")
    
    # Defaults per car
    default_log = {
        "1": {
            "car_name": "Forget Me Not",
            "last_tire_rotation_odometer": 178500,
            "last_tire_rotation_date": "2026-05-10",
            "active_tire_set": "all_season",
            "last_tire_swap_date": "2026-04-20",
            "notes": "Rotated at Tesla Service"
        },
        "2": {
            "car_name": "Shadow",
            "last_tire_rotation_odometer": 88000,
            "last_tire_rotation_date": "2026-04-15",
            "active_tire_set": "all_season",
            "last_tire_swap_date": "2026-04-15",
            "notes": "Rotated at Discount Tire"
        }
    }
    save_maintenance_log(default_log)
    return default_log


def save_maintenance_log(data: Dict[str, Any]) -> None:
    try:
        with open(MAINTENANCE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Maintenance] Error saving log: {e}")
