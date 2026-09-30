import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
CACHE_FILE = DATA_DIR / "gas_price_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours


def get_cached_gas_price(zip_code: str) -> Optional[float]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if data.get("zip_code") == zip_code:
            cached_time = data.get("timestamp", 0)
            if time.time() - cached_time < CACHE_TTL_SECONDS:
                return float(data.get("price", 4.00))
    except Exception as e:
        print(f"[GasPrice] Cache read error: {e}")
    return None


def set_cached_gas_price(zip_code: str, price: float, source: str = "auto") -> None:
    try:
        data = {
            "zip_code": zip_code,
            "price": round(price, 2),
            "timestamp": int(time.time()),
            "source": source
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[GasPrice] Cache write error: {e}")


async def fetch_live_gas_price(zip_code: str = "80005", fallback: float = 4.00) -> float:
    """
    Fetches regular gasoline price for the given zip code / area.
    Checks 24h cache first; queries public endpoints with fallback to configured price.
    """
    cached = get_cached_gas_price(zip_code)
    if cached is not None:
        return cached

    # Attempt to query public gas price data
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Check public Colorado / Rocky Mountain energy data or fallback
            url = f"https://raw.githubusercontent.com/gas-prices/data/main/us/{zip_code[:2]}.json"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if "regular" in data:
                    price = float(data["regular"])
                    set_cached_gas_price(zip_code, price, source="public_api")
                    return price
    except Exception as e:
        print(f"[GasPrice] Live fetch lookup note: {e}")

    # Fallback to configured price ($4.00 default)
    set_cached_gas_price(zip_code, fallback, source="fallback")
    return fallback
