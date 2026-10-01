import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx


async def verify_ha_connection(url: str, token: str) -> Dict[str, Any]:
    """
    Tests connectivity to Home Assistant REST API.
    """
    base_url = (url or "http://192.168.1.15:8123").strip().rstrip("/")
    tok = (token or "").strip()
    if not tok:
        return {"success": False, "error": "Home Assistant Long-Lived Access Token is required."}

    candidate_urls = [base_url]
    if "192.168.1.15" not in base_url:
        candidate_urls.append("http://192.168.1.15:8123")
    if "172.17.0.1" not in base_url:
        candidate_urls.append("http://172.17.0.1:8123")

    error_msg = ""
    async with httpx.AsyncClient(timeout=4.0) as client:
        for host in candidate_urls:
            endpoint = f"{host}/api/"
            try:
                resp = await client.get(endpoint, headers={"Authorization": f"Bearer {tok}"})
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("message", "API running.")
                    return {"success": True, "message": f"Successfully connected to Home Assistant at {host}! ({msg})", "url": host}
                elif resp.status_code in (401, 403):
                    return {"success": False, "error": "Invalid or expired Long-Lived Access Token (401/403)."}
                else:
                    error_msg = f"HTTP {resp.status_code} returned from {host}"
            except Exception as e:
                if not error_msg:
                    error_msg = str(e)

    return {"success": False, "error": error_msg or "Could not connect to Home Assistant"}


async def discover_ha_solar_entities(url: str, token: str) -> Dict[str, Any]:
    """
    Queries /api/states to discover solar and energy monitoring entities.
    """
    base_url = (url or "http://192.168.1.15:8123").strip().rstrip("/")
    tok = (token or "").strip()
    if not tok:
        return {"success": False, "error": "Token required to discover entities", "entities": []}

    candidate_urls = [base_url]
    if "192.168.1.15" not in base_url:
        candidate_urls.append("http://192.168.1.15:8123")
    if "172.17.0.1" not in base_url:
        candidate_urls.append("http://172.17.0.1:8123")

    states = []
    error_msg = ""
    async with httpx.AsyncClient(timeout=6.0) as client:
        for host in candidate_urls:
            endpoint = f"{host}/api/states"
            try:
                resp = await client.get(endpoint, headers={"Authorization": f"Bearer {tok}"})
                if resp.status_code == 200:
                    states = resp.json()
                    break
                elif resp.status_code in (401, 403):
                    return {"success": False, "error": "Unauthorized: Check Home Assistant token", "entities": []}
            except Exception as e:
                if not error_msg:
                    error_msg = str(e)

    if not states:
        return {"success": False, "error": error_msg or "Failed to retrieve states from Home Assistant", "entities": []}

    solar_energy_candidates = []
    solar_power_candidates = []
    grid_import_candidates = []
    grid_export_candidates = []
    load_candidates = []

    for s in states:
        eid = s.get("entity_id", "")
        if not eid.startswith("sensor."):
            continue
        attrs = s.get("attributes", {})
        fn = attrs.get("friendly_name", eid)
        dc = attrs.get("device_class", "")
        unit = attrs.get("unit_of_measurement", "")
        eid_low = eid.lower()
        fn_low = fn.lower()

        # Solar energy (kWh)
        if any(k in eid_low or k in fn_low for k in ["solar_production", "solar_energy", "solar_generation", "pv_energy", "tesla_solar"]) and unit in ["kWh", "Wh", "MWh"]:
            solar_energy_candidates.append({"entity_id": eid, "name": fn, "state": s.get("state"), "unit": unit})
        # Solar power (W / kW)
        elif any(k in eid_low or k in fn_low for k in ["solar_power", "solar_active_power", "pv_power", "current_solar"]) or (dc == "power" and "solar" in fn_low):
            solar_power_candidates.append({"entity_id": eid, "name": fn, "state": s.get("state"), "unit": unit})
        # Grid import
        elif any(k in eid_low or k in fn_low for k in ["grid_import", "grid_consumption", "grid_in"]) and unit in ["kWh", "Wh"]:
            grid_import_candidates.append({"entity_id": eid, "name": fn, "state": s.get("state"), "unit": unit})
        # Grid export / feed-in
        elif any(k in eid_low or k in fn_low for k in ["grid_export", "grid_feed", "grid_out"]) and unit in ["kWh", "Wh"]:
            grid_export_candidates.append({"entity_id": eid, "name": fn, "state": s.get("state"), "unit": unit})
        # Total load / home consumption
        elif any(k in eid_low or k in fn_low for k in ["total_load_energy", "home_consumption", "house_energy"]) and unit in ["kWh", "Wh"]:
            load_candidates.append({"entity_id": eid, "name": fn, "state": s.get("state"), "unit": unit})

    def _pick_best(candidates: List[Dict[str, Any]], fallback: str) -> str:
        if not candidates:
            return fallback
        for c in candidates:
            st = str(c.get("state", "")).lower()
            if st not in ("unavailable", "unknown", "none", ""):
                try:
                    float(st)
                    return c["entity_id"]
                except ValueError:
                    pass
        return candidates[0]["entity_id"]

    suggested = {
        "solar_energy_entity": _pick_best(solar_energy_candidates, "sensor.tesla_solar_production"),
        "solar_power_entity": _pick_best(solar_power_candidates, "sensor.1au_solar_power"),
        "grid_import_entity": _pick_best(grid_import_candidates, "sensor.current_grid_consumption"),
        "grid_export_entity": _pick_best(grid_export_candidates, "sensor.current_grid_feed"),
        "home_load_entity": _pick_best(load_candidates, "sensor.total_load_energy")
    }

    return {
        "success": True,
        "suggested": suggested,
        "solar_energy_candidates": solar_energy_candidates,
        "solar_power_candidates": solar_power_candidates,
        "grid_import_candidates": grid_import_candidates,
        "grid_export_candidates": grid_export_candidates,
        "load_candidates": load_candidates,
    }


async def fetch_solar_summary(
    ha_config: Any,
    start_date: datetime,
    end_date: datetime,
    home_charging_kwh: float = 0.0,
    kwh_cost: float = 0.13
) -> Dict[str, Any]:
    """
    Fetches solar production and grid flow metrics for the specified digest period.
    """
    empty_result = {
        "has_data": False,
        "total_solar_kwh": 0.0,
        "home_charging_kwh": home_charging_kwh,
        "solar_ev_coverage_pct": 0.0,
        "clean_miles_covered": 0.0,
        "solar_surplus_kwh": 0.0,
        "solar_savings": 0.0,
        "grid_import_kwh": 0.0,
        "grid_export_kwh": 0.0,
        "home_load_kwh": 0.0,
        "peak_solar_kw": 0.0,
        "self_consumption_pct": 100.0,
        "daily_breakdown": [],
    }

    if not ha_config or not getattr(ha_config, "enabled", False):
        return empty_result

    tok = getattr(ha_config, "token", "").strip()
    if not tok:
        return empty_result

    base_url = (getattr(ha_config, "url", "") or "http://192.168.1.15:8123").strip().rstrip("/")
    solar_energy_eid = getattr(ha_config, "solar_energy_entity", "sensor.tesla_solar_production") or "sensor.tesla_solar_production"
    solar_power_eid = getattr(ha_config, "solar_power_entity", "sensor.1au_solar_power") or "sensor.1au_solar_power"
    grid_import_eid = getattr(ha_config, "grid_import_entity", "sensor.current_grid_consumption") or "sensor.current_grid_consumption"
    grid_export_eid = getattr(ha_config, "grid_export_entity", "sensor.current_grid_feed") or "sensor.current_grid_feed"
    load_eid = getattr(ha_config, "home_load_entity", "sensor.total_load_energy") or "sensor.total_load_energy"

    # Candidate host resolution
    candidate_urls = [base_url]
    if "192.168.1.15" not in base_url:
        candidate_urls.append("http://192.168.1.15:8123")
    if "172.17.0.1" not in base_url:
        candidate_urls.append("http://172.17.0.1:8123")

    # Ensure dates have timezone awareness for HA API
    start_utc = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
    end_utc = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)

    start_str = urllib.parse.quote(start_utc.isoformat())
    end_str = urllib.parse.quote(end_utc.isoformat())

    filter_entities = f"{solar_energy_eid},{grid_import_eid},{grid_export_eid},{load_eid},{solar_power_eid}"
    query_url = f"/api/history/period/{start_str}?filter_entity_id={filter_entities}&end_time={end_str}&minimal_response=1"

    data = None
    async with httpx.AsyncClient(timeout=12.0) as client:
        for host in candidate_urls:
            full_url = f"{host}{query_url}"
            try:
                resp = await client.get(full_url, headers={"Authorization": f"Bearer {tok}"})
                if resp.status_code == 200:
                    data = resp.json()
                    break
            except Exception as e:
                print(f"[HomeAssistant] Host {host} failed: {e}")

    if not data or not isinstance(data, list):
        return empty_result

    entity_map = {}
    for series in data:
        if series and isinstance(series, list):
            eid = series[0].get("entity_id")
            if eid:
                entity_map[eid] = series

    def _calc_delta(eid: str) -> float:
        s = entity_map.get(eid, [])
        if not s or len(s) < 2:
            return 0.0
        try:
            first_val = float(s[0].get("state", 0))
            last_val = float(s[-1].get("state", 0))
            diff = last_val - first_val
            return max(0.0, round(diff, 2))
        except (ValueError, TypeError):
            return 0.0

    total_solar_kwh = _calc_delta(solar_energy_eid)
    grid_import_kwh = _calc_delta(grid_import_eid)
    grid_export_kwh = _calc_delta(grid_export_eid)
    home_load_kwh = _calc_delta(load_eid)

    # Daily breakdown from solar_energy_eid
    daily_min = {}
    daily_max = {}
    solar_series = entity_map.get(solar_energy_eid, [])
    for p in solar_series:
        try:
            val = float(p.get("state", 0))
            dt_raw = p.get("last_updated") or p.get("last_changed") or ""
            day_key = dt_raw[:10]
            if not day_key:
                continue
            if day_key not in daily_min:
                daily_min[day_key] = val
            daily_max[day_key] = val
        except (ValueError, TypeError):
            continue

    daily_breakdown = []
    for day, mx in sorted(daily_max.items()):
        mn = daily_min.get(day, mx)
        gen = max(0.0, round(mx - mn, 2))
        daily_breakdown.append({"date": day, "kwh": gen})

    # Peak solar power in kW from solar_power_eid
    peak_solar_kw = 0.0
    power_series = entity_map.get(solar_power_eid, [])
    max_w = 0.0
    for p in power_series:
        try:
            val = float(p.get("state", 0))
            if val > max_w:
                max_w = val
        except (ValueError, TypeError):
            continue
    peak_solar_kw = round(max_w / 1000.0, 2)

    # Calculations
    has_data = total_solar_kwh > 0.0 or peak_solar_kw > 0.0
    solar_savings = round(total_solar_kwh * (kwh_cost or 0.13), 2)

    solar_ev_coverage_pct = 0.0
    if home_charging_kwh > 0:
        solar_ev_coverage_pct = min(100.0, round((total_solar_kwh / home_charging_kwh) * 100.0, 1))
    elif total_solar_kwh > 0:
        solar_ev_coverage_pct = 100.0

    # Approx 3.7 mi/kWh for typical Tesla Model Y/X efficiency (~270 Wh/mi)
    clean_ev_kwh = min(total_solar_kwh, home_charging_kwh)
    clean_miles_covered = round(clean_ev_kwh * 3.7, 1)
    solar_surplus_kwh = max(0.0, round(total_solar_kwh - home_charging_kwh, 2))

    self_consumption_pct = 100.0
    if total_solar_kwh > 0 and grid_export_kwh <= total_solar_kwh:
        self_consumption_pct = round(((total_solar_kwh - grid_export_kwh) / total_solar_kwh) * 100.0, 1)

    return {
        "has_data": has_data,
        "total_solar_kwh": total_solar_kwh,
        "home_charging_kwh": round(home_charging_kwh, 2),
        "solar_ev_coverage_pct": solar_ev_coverage_pct,
        "clean_miles_covered": clean_miles_covered,
        "solar_surplus_kwh": solar_surplus_kwh,
        "solar_savings": solar_savings,
        "grid_import_kwh": grid_import_kwh,
        "grid_export_kwh": grid_export_kwh,
        "home_load_kwh": home_load_kwh,
        "peak_solar_kw": peak_solar_kw,
        "self_consumption_pct": self_consumption_pct,
        "daily_breakdown": daily_breakdown,
    }
