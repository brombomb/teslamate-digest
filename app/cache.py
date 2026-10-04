import time
import hashlib
import json
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from app.config import AppConfig


class TTLCache:
    """
    Thread-safe in-memory cache with Time-To-Live (TTL) expiration.
    """
    def __init__(self, default_ttl: int = 300):
        self._default_ttl = default_ttl
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            expiry, val = entry
            if time.time() > expiry:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        actual_ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + actual_ttl
        with self._lock:
            self._store[key] = (expiry, value)

    def delete(self, key: str) -> bool:
        with self._lock:
            return bool(self._store.pop(key, None))

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def cleanup(self) -> int:
        now = time.time()
        with self._lock:
            expired_keys = [k for k, (exp, _) in self._store.items() if now > exp]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses
            }


# Global in-memory cache instance
report_cache = TTLCache(default_ttl=300)


def _config_telemetry_signature(config: AppConfig) -> str:
    """
    Produces a deterministic hash string representing all settings that affect telemetry data.
    """
    data = {
        "rates": config.rates.model_dump() if hasattr(config.rates, "model_dump") else config.rates.dict(),
        "work_routes": [r.model_dump() if hasattr(r, "model_dump") else r for r in getattr(config, "work_routes", [])],
        "excluded_locations": getattr(config, "excluded_locations", []),
        "irs_mileage_rate": getattr(config, "irs_mileage_rate", 0.67),
        "commute_target_car_id": getattr(config, "commute_target_car_id", None),
        "tire_rotation_interval_mi": getattr(config, "tire_rotation_interval_mi", 6250),
        "units": config.units.model_dump() if hasattr(config.units, "model_dump") else getattr(config, "units", {}),
        "modules": config.modules.model_dump() if hasattr(config.modules, "model_dump") else config.modules.dict(),
        "ha_enabled": bool(getattr(config.homeassistant, "enabled", False)),
        "ha_url": getattr(config.homeassistant, "url", ""),
    }
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_telemetry_cache_key(
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int],
    config: AppConfig
) -> str:
    sig = _config_telemetry_signature(config)
    s_str = start_date.strftime("%Y%m%d%H%M%S")
    e_str = end_date.strftime("%Y%m%d%H%M%S")
    return f"tel:{s_str}:{e_str}:{car_id or 'all'}:{sig}"


def make_report_cache_key(
    start_date: datetime,
    end_date: datetime,
    car_id: Optional[int],
    theme: Optional[str],
    for_email: bool,
    config: AppConfig
) -> str:
    tel_key = make_telemetry_cache_key(start_date, end_date, car_id, config)
    urls = f"{config.dashboard_url}|{config.teslamate_url}|{config.grafana_url}"
    theme_str = theme or getattr(config, "email_theme", "pearl_white")
    mode_str = "email" if for_email else "preview"
    h = hashlib.sha256(f"{urls}:{theme_str}:{mode_str}".encode("utf-8")).hexdigest()[:12]
    return f"rep:{tel_key}:{theme_str}:{h}"


def clear_report_cache() -> None:
    report_cache.clear()
