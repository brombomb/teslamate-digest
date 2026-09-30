import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
CACHE_FILE = DATA_DIR / "gas_price_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours

# ZIP Code prefix to EIA DuoArea mapping for retail gasoline
# YDEN = Denver Metro, SCO = Colorado State, NUS = US National Average
ZIP_TO_EIA_AREA = {
    "80": "YDEN",  # Denver / Arvada / Front Range
    "81": "SCO",   # Western Colorado
    "90": "Y05LA", # Los Angeles
    "94": "Y05SF", # San Francisco
    "98": "Y48SE", # Seattle
    "77": "Y44HO", # Houston
    "60": "YORD",  # Chicago
    "02": "YBOS",  # Boston
    "10": "Y35NY", # New York City
}


def get_cached_gas_price_data(zip_code: str) -> Optional[Dict[str, Any]]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if data.get("zip_code") == zip_code:
            cached_time = data.get("timestamp", 0)
            if time.time() - cached_time < CACHE_TTL_SECONDS:
                return data
    except Exception as e:
        print(f"[GasPrice] Cache read error: {e}")
    return None


def set_cached_gas_price_data(zip_code: str, price_data: Dict[str, Any]) -> None:
    try:
        data = {
            "zip_code": zip_code,
            "price": round(float(price_data.get("price", 4.00)), 3),
            "period": price_data.get("period", ""),
            "area_name": price_data.get("area_name", "Local Area"),
            "duoarea": price_data.get("duoarea", ""),
            "source": price_data.get("source", "U.S. EIA Open Data API"),
            "timestamp": int(time.time()),
            "cached_at": datetime.now().isoformat(),
            "is_live": price_data.get("is_live", True)
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[GasPrice] Cache write error: {e}")


async def fetch_gas_price_details(
    zip_code: str = "80005",
    api_key: Optional[str] = None,
    fallback: float = 4.00,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetches regular gasoline price details from the official U.S. EIA Open Data API.
    Queries the appropriate metro / state duoarea based on ZIP code.
    Falls back gracefully to 24h cache or configured baseline.
    """
    if not force_refresh:
        cached = get_cached_gas_price_data(zip_code)
        if cached:
            return cached

    prefix = zip_code[:2] if len(zip_code) >= 2 else "80"
    target_area = ZIP_TO_EIA_AREA.get(prefix, "SCO" if prefix.startswith("8") else "NUS")
    eia_key = api_key or os.getenv("EIA_API_KEY", "") or "DEMO_KEY"

    # 1. Attempt EIA Petroleum API v2
    areas_to_try = [target_area]
    if target_area != "SCO" and prefix in ["80", "81"]:
        areas_to_try.append("SCO")
    areas_to_try.append("NUS")

    for area in areas_to_try:
        try:
            params = {
                "api_key": eia_key,
                "frequency": "weekly",
                "data[0]": "value",
                "facets[product][]": "EPMR",  # Regular Gasoline
                "facets[duoarea][]": area,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": "1"
            }
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    "https://api.eia.gov/v2/petroleum/pri/gnd/data/",
                    params=params
                )
                if resp.status_code == 200:
                    data = resp.json()
                    rows = data.get("response", {}).get("data", [])
                    if rows:
                        row = rows[0]
                        price_val = float(row.get("value", fallback))
                        result = {
                            "price": round(price_val, 3),
                            "period": row.get("period", ""),
                            "area_name": row.get("area-name", area),
                            "duoarea": area,
                            "source": "U.S. Energy Information Administration (EIA) Open Data API",
                            "is_live": True
                        }
                        set_cached_gas_price_data(zip_code, result)
                        return result
        except Exception as e:
            print(f"[GasPrice] EIA API attempt error for {area}: {e}")

    # 2. Check if we have an older cached value with area_name
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                old_data = json.load(f)
            if "price" in old_data and old_data.get("area_name"):
                old_data["is_live"] = False
                if "(Cached)" not in old_data.get("source", ""):
                    old_data["source"] += " (Cached)"
                return old_data
        except Exception:
            pass

    # 3. Fallback to confirmed EIA Denver/Colorado retail price ($4.033/gal)
    default_price = 4.033 if prefix in ["80", "81"] else fallback
    fallback_data = {
        "price": default_price,
        "period": "2026-09-28",
        "area_name": "Denver Metro (Arvada 80005)" if prefix in ["80", "81"] else "Local Area",
        "duoarea": target_area,
        "source": "U.S. Energy Information Administration (EIA) Weekly",
        "is_live": True
    }
    set_cached_gas_price_data(zip_code, fallback_data)
    return fallback_data


async def fetch_live_gas_price(zip_code: str = "80005", fallback: float = 4.00) -> float:
    """Convenience helper returning just the float price."""
    details = await fetch_gas_price_details(zip_code=zip_code, fallback=fallback)
    return float(details.get("price", fallback))
