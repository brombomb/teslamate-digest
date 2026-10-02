import json
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
MAINTENANCE_FILE = DATA_DIR / "maintenance.json"


class SMTPSettings(BaseModel):
    enabled: bool = True
    host: str = "smtp.gmail.com"
    port: int = 587
    user: str = ""
    password: str = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    sender_email: str = ""
    sender_name: str = "TeslaMate Digest"
    recipient_email: str = ""
    use_tls: bool = True
    use_ssl: bool = False


class ScheduleItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Digest Schedule"
    enabled: bool = True
    frequency: str = "monthly"  # monthly, semi-monthly, bi-weekly, weekly, daily
    target_car_id: Optional[int] = None  # None for All Cars (Fleet), or integer car_id
    day_of_week: int = 0  # 0=Monday, 6=Sunday
    day_of_month: int = 1  # 1 to 28
    send_hour: int = 8  # 0 to 23
    send_minute: int = 0  # 0 to 59
    recipient_email: str = ""  # override or empty for default SMTP recipient
    theme: str = "pearl_white"

    @field_validator("target_car_id", mode="before")
    @classmethod
    def parse_target_car_id(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or v == "null" or v == "None":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class ScheduleSettings(BaseModel):
    enabled: bool = True
    frequency: str = "monthly"  # monthly, semi-monthly, bi-weekly, weekly, daily
    send_day_of_month: int = 1   # 1st of month (or 1st & 15th for semi-monthly)
    send_day_of_week: int = 0    # Monday (0)
    send_hour: int = 8           # 8:00 AM
    send_minute: int = 0
    target_car_id: Optional[int] = None  # None for Fleet (All Cars), or car_id integer
    theme: str = "pearl_white"


class RatesSettings(BaseModel):
    rate_mode: str = "tou"  # tou or flat
    tariff_preset: str = "standard_tou"
    average_kwh_cost: float = 0.13
    off_peak_kwh_cost: float = 0.10
    shoulder_kwh_cost: float = 0.14
    on_peak_kwh_cost: float = 0.20
    off_peak_start_hour: int = 21  # 9 PM
    off_peak_end_hour: int = 9     # 9 AM
    peak_start_hour: int = 13      # 1 PM
    peak_end_hour: int = 19        # 7 PM
    weekends_are_off_peak: bool = True
    supercharger_fallback_cost: float = 0.36
    gas_price_per_gal: float = 3.50
    zip_code: str = "12345"
    auto_gas_price: bool = True
    baseline_ice_mpg: float = 26.0
    eia_api_key: str = ""
    openei_api_key: str = ""
    utility_name: str = ""
    # Tiered / Threshold Usage Rates
    tier1_max_kwh: float = 500.0
    tier1_kwh_cost: float = 0.11
    tier2_max_kwh: float = 1000.0
    tier2_kwh_cost: float = 0.17
    tier3_kwh_cost: float = 0.26

    gas_price_source: str = "eia"
    electric_rate_source: str = "openei"


class UnitSettings(BaseModel):
    length: str = "mi"       # mi or km
    temp: str = "F"          # F or C
    pressure: str = "psi"    # psi or bar
    currency: str = "$"


class GeofenceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    latitude: float
    longitude: float
    radius_meters: int = 350
    address_aliases: list[str] = Field(default_factory=list)
    in_teslamate: bool = False

    @field_validator("address_aliases", mode="before")
    @classmethod
    def parse_aliases(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class WorkRouteItem(BaseModel):
    label: str
    point_a: str
    point_b: str
    bidirectional: bool = True
    target_car_id: Optional[int] = None

    @field_validator("target_car_id", mode="before")
    @classmethod
    def parse_target_car_id(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or v == "null" or v == "None":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


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
    mountain_regen: bool = True
    colorado_mountain_regen: Optional[bool] = None
    vampire_drain: bool = True
    maintenance_alerts: bool = True
    snow_tire_reminder: bool = True
    embedded_charts: bool = True
    solar_production: bool = True
    achievements: bool = True

    def model_post_init(self, __context: Any) -> None:
        if self.colorado_mountain_regen is not None:
            self.mountain_regen = self.colorado_mountain_regen


class HomeAssistantConfig(BaseModel):
    enabled: bool = False
    url: str = "http://192.168.1.15:8123"
    token: str = ""
    solar_energy_entity: str = "sensor.tesla_solar_production"
    solar_power_entity: str = "sensor.1au_solar_power"
    grid_import_entity: str = "sensor.current_grid_consumption"
    grid_export_entity: str = "sensor.current_grid_feed"
    home_load_entity: str = "sensor.total_load_energy"


class GrafanaDashboardsConfig(BaseModel):
    charging: str = "-pkIkhmRz/charging-stats"
    charge_level: str = "WopVO_mgz/charge-level"
    charges: str = "TSmNYvRRk/charges"
    drives: str = "Y8upc6ZRk/drives"
    drive_stats: str = "_7WkNSyWk/drive-stats"
    efficiency: str = "fu4SiQgWz/efficiency"
    battery_health: str = "jchmRiqUfXgTM/battery-health"
    vampire_drain: str = "zhHx2Fggk/vampire-drain"
    overview: str = "kOuP_Fggz/overview"
    mileage: str = "NjtMTFggz/mileage"
    trip: str = "FkUpJpQZk/trip"
    locations: str = "ZzhF-aRWz/locations"
    visited: str = "RG_DxSmgk/visited"
    updates: str = "IiC07mgWz/updates"
    timeline: str = "SUBgwtigz/timeline"
    achievements: str = "c6020bdb-a2c7-4b1c-ab2c-fd34ab836c6e/achievements"


class AppConfig(BaseModel):
    database_host: str = Field(default_factory=lambda: os.getenv("DATABASE_HOST", "database"))
    database_port: int = Field(default_factory=lambda: int(os.getenv("DATABASE_PORT", "5432")))
    database_user: str = Field(default_factory=lambda: os.getenv("DATABASE_USER", "teslamate"))
    database_pass: str = Field(default_factory=lambda: os.getenv("DATABASE_PASS", "teslamate"))
    database_name: str = Field(default_factory=lambda: os.getenv("DATABASE_NAME", "teslamate"))
    timezone: str = Field(default_factory=lambda: os.getenv("TZ", "UTC"))
    grafana_url: str = Field(default_factory=lambda: os.getenv("GRAFANA_URL", ""))
    grafana_api_token: str = Field(default_factory=lambda: os.getenv("GRAFANA_API_TOKEN", ""))
    grafana_dashboards: GrafanaDashboardsConfig = Field(default_factory=GrafanaDashboardsConfig)
    homeassistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)

    smtp: SMTPSettings = Field(default_factory=SMTPSettings)
    schedules: list[ScheduleItem] = Field(default_factory=lambda: [
        ScheduleItem(
            id="default-monthly",
            name="Monthly Fleet Retrospective",
            enabled=True,
            frequency="monthly",
            target_car_id=None,
            day_of_week=0,
            day_of_month=1,
            send_hour=8,
            send_minute=0,
            recipient_email="",
            theme="pearl_white"
        )
    ])
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    rates: RatesSettings = Field(default_factory=RatesSettings)
    units: UnitSettings = Field(default_factory=UnitSettings)
    modules: ModuleToggles = Field(default_factory=ModuleToggles)
    tire_rotation_interval_mi: int = 6250
    dashboard_url: str = Field(default_factory=lambda: os.getenv("DASHBOARD_URL", "http://localhost:8660"))
    teslamate_url: str = Field(default_factory=lambda: os.getenv("TESLAMATE_URL", ""))
    excluded_locations: list[str] = Field(default_factory=lambda: ["Home"])
    email_theme: str = "pearl_white"
    geofences: list[GeofenceItem] = Field(default_factory=list)
    work_routes: list[WorkRouteItem] = Field(default_factory=list)
    irs_mileage_rate: float = 0.67
    commute_target_car_id: Optional[int] = None

    @field_validator("commute_target_car_id", mode="before")
    @classmethod
    def parse_commute_target_car_id(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or v == "null" or v == "None":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


def load_config() -> AppConfig:
    from app.storage import load_config_data, save_config_data
    data = load_config_data()
    if data:
        try:
            # Migration from legacy single schedule to multi-schedules list
            if "schedules" not in data and "schedule" in data:
                leg = data["schedule"]
                th = data.get("email_theme", "pearl_white")
                data["schedules"] = [
                    {
                        "id": "migrated-1",
                        "name": "Scheduled Digest",
                        "enabled": leg.get("enabled", True),
                        "frequency": leg.get("frequency", "monthly"),
                        "target_car_id": leg.get("target_car_id"),
                        "day_of_week": leg.get("send_day_of_week", 0),
                        "day_of_month": leg.get("send_day_of_month", 1),
                        "send_hour": leg.get("send_hour", 8),
                        "send_minute": leg.get("send_minute", 0),
                        "recipient_email": "",
                        "theme": th
                    }
                ]
            
            cfg = AppConfig(**data)
            if not cfg.smtp.password and os.getenv("SMTP_PASSWORD"):
                cfg.smtp.password = os.getenv("SMTP_PASSWORD")
            if os.getenv("DATABASE_PASS"):
                cfg.database_pass = os.getenv("DATABASE_PASS")
            if os.getenv("DATABASE_HOST"):
                cfg.database_host = os.getenv("DATABASE_HOST")
            if os.getenv("DATABASE_USER"):
                cfg.database_user = os.getenv("DATABASE_USER")
            if os.getenv("DATABASE_NAME"):
                cfg.database_name = os.getenv("DATABASE_NAME")
            if os.getenv("DATABASE_PORT"):
                try:
                    cfg.database_port = int(os.getenv("DATABASE_PORT"))
                except ValueError:
                    pass
            return cfg
        except Exception as e:
            print(f"[Config] Error parsing config from storage: {e}. Preserving raw storage and returning fallback in-memory config.")
            return AppConfig()

    cfg = AppConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    from app.storage import save_config_data
    try:
        save_config_data(cfg.model_dump())
    except Exception as e:
        print(f"[Config] Error saving config: {e}")


def load_maintenance_log() -> Dict[str, Any]:
    from app.storage import load_maintenance_data
    try:
        return load_maintenance_data()
    except Exception as e:
        print(f"[Maintenance] Error loading log: {e}")
        return {}


def save_maintenance_log(data: Dict[str, Any]) -> None:
    from app.storage import save_maintenance_data
    try:
        save_maintenance_data(data)
    except Exception as e:
        print(f"[Maintenance] Error saving log: {e}")


def reset_maintenance_log_rotation(car_id: str) -> None:
    from app.storage import reset_maintenance_rotation
    try:
        reset_maintenance_rotation(car_id)
    except Exception as e:
        print(f"[Maintenance] Error resetting rotation: {e}")

