import json
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx


def is_safe_url(url: str) -> bool:
    """Validates URL to guard against SSRF, cloud metadata exfiltration, and invalid schemes."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        forbidden = {
            "169.254.169.254",
            "metadata.google.internal",
            "metadata.google",
            "100.100.100.200",
            "fd00:ec2::254",
        }
        if hostname in forbidden:
            return False
        return True
    except Exception:
        return False


async def verify_ha_connection(url: str, token: str) -> Dict[str, Any]:
    """
    Tests connectivity to Home Assistant REST API.
    """
    base_url = (url or "http://homeassistant:8123").strip().rstrip("/")
    if not is_safe_url(base_url):
        return {"success": False, "error": "Invalid URL or forbidden destination address."}

    tok = (token or "").strip()
    if not tok:
        return {"success": False, "error": "Home Assistant Long-Lived Access Token is required."}

    candidate_urls = [base_url]
    if base_url != "http://homeassistant:8123" and "homeassistant" not in base_url:
        candidate_urls.append("http://homeassistant:8123")

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
    base_url = (url or "http://homeassistant:8123").strip().rstrip("/")
    if not is_safe_url(base_url):
        return {"success": False, "error": "Invalid URL or forbidden destination address.", "entities": []}

    tok = (token or "").strip()
    if not tok:
        return {"success": False, "error": "Token required to discover entities", "entities": []}

    candidate_urls = [base_url]
    if base_url != "http://homeassistant:8123" and "homeassistant" not in base_url:
        candidate_urls.append("http://homeassistant:8123")

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
        "solar_power_entity": _pick_best(solar_power_candidates, "sensor.solar_power"),
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


async def _fetch_lts_via_websocket(
    base_url: str,
    token: str,
    start_utc: datetime,
    end_utc: datetime,
    statistic_ids: List[str]
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Queries Home Assistant recorder/statistics_during_period via WebSocket API.
    Provides long-term cumulative daily statistics (retained indefinitely) even after
    raw entity states older than 10 days are purged by Home Assistant recorder.
    """
    try:
        import websockets
    except ImportError:
        return None

    tok = (token or "").strip()
    if not tok:
        return None

    clean_base = (base_url or "http://homeassistant:8123").strip().rstrip("/")
    ws_base = clean_base.replace("http://", "ws://").replace("https://", "wss://")
    candidate_urls = [f"{ws_base}/api/websocket"]
    if "homeassistant:8123" not in ws_base:
        candidate_urls.append("ws://homeassistant:8123/api/websocket")

    for ws_url in candidate_urls:
        try:
            async with websockets.connect(ws_url, open_timeout=4.0, close_timeout=4.0) as ws:
                auth_req = json.loads(await ws.recv())
                if auth_req.get("type") != "auth_required":
                    continue
                await ws.send(json.dumps({"type": "auth", "access_token": tok}))
                auth_res = json.loads(await ws.recv())
                if auth_res.get("type") != "auth_ok":
                    continue
                req = {
                    "id": 1,
                    "type": "recorder/statistics_during_period",
                    "start_time": start_utc.isoformat(),
                    "end_time": end_utc.isoformat(),
                    "statistic_ids": list(set(statistic_ids)),
                    "period": "day",
                    "types": ["change", "max"]
                }
                await ws.send(json.dumps(req))
                res = json.loads(await ws.recv())
                if res.get("success"):
                    return res.get("result", {})
        except Exception:
            continue

    return None


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

    base_url = (getattr(ha_config, "url", "") or "http://homeassistant:8123").strip().rstrip("/")
    solar_energy_eid = getattr(ha_config, "solar_energy_entity", "sensor.tesla_solar_production") or "sensor.tesla_solar_production"
    solar_power_eid = getattr(ha_config, "solar_power_entity", "sensor.solar_power") or "sensor.solar_power"
    grid_import_eid = getattr(ha_config, "grid_import_entity", "sensor.current_grid_consumption") or "sensor.current_grid_consumption"
    grid_export_eid = getattr(ha_config, "grid_export_entity", "sensor.current_grid_feed") or "sensor.current_grid_feed"
    load_eid = getattr(ha_config, "home_load_entity", "sensor.total_load_energy") or "sensor.total_load_energy"

    # Candidate host resolution
    candidate_urls = [base_url]
    if base_url != "http://homeassistant:8123" and "homeassistant" not in base_url:
        candidate_urls.append("http://homeassistant:8123")

    # Ensure dates have timezone awareness for HA API
    start_utc = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
    end_utc = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
    total_days = max(1, (end_date - start_date).days)
    start_str_day = start_date.strftime("%Y-%m-%d")
    end_str_day = end_date.strftime("%Y-%m-%d")

    # -------------------------------------------------------------------------
    # 1. PRIMARY: Long-Term Statistics (LTS) via WebSocket API
    # -------------------------------------------------------------------------
    # LTS is Home Assistant's authoritative energy source (powering the native Energy
    # Dashboard). It retains daily/hourly aggregates indefinitely (unaffected by the
    # 10-day raw purge) and computes mathematically correct changes without raw state diffs.
    stat_candidates = [
        solar_energy_eid,
        grid_import_eid,
        grid_export_eid,
        load_eid,
        solar_power_eid,
    ]
    lts_data = await _fetch_lts_via_websocket(base_url, tok, start_utc, end_utc, stat_candidates)
    if lts_data:
        solar_lts = lts_data.get(solar_energy_eid, [])
        lts_daily = []
        lts_total = 0.0
        for e in solar_lts:
            chg = e.get("change")
            if chg is not None:
                d_str = datetime.fromtimestamp(e["start"] / 1000.0).strftime("%Y-%m-%d")
                if start_str_day <= d_str < end_str_day:
                    val = max(0.0, round(float(chg), 2))
                    lts_daily.append({"date": d_str, "kwh": val})
                    lts_total += val

        total_solar_kwh = round(lts_total, 2)
        daily_breakdown = lts_daily
        days_tracked = len(daily_breakdown)
        is_partial_period = (days_tracked < (total_days - 1)) and (days_tracked > 0) and (total_days > 3)

        # Grid import
        grid_import_kwh = 0.0
        import_lts = lts_data.get(grid_import_eid, [])
        if import_lts:
            grid_import_kwh = round(sum(
                max(0.0, float(e.get("change", 0) or 0))
                for e in import_lts
                if start_str_day <= datetime.fromtimestamp(e["start"] / 1000.0).strftime("%Y-%m-%d") < end_str_day
            ), 2)

        # Grid export
        grid_export_kwh = 0.0
        export_lts = lts_data.get(grid_export_eid, [])
        if export_lts:
            grid_export_kwh = round(sum(
                max(0.0, float(e.get("change", 0) or 0))
                for e in export_lts
                if start_str_day <= datetime.fromtimestamp(e["start"] / 1000.0).strftime("%Y-%m-%d") < end_str_day
            ), 2)

        # Home load
        home_load_kwh = 0.0
        load_lts = lts_data.get(load_eid, [])
        if load_lts:
            home_load_kwh = round(sum(
                max(0.0, float(e.get("change", 0) or 0))
                for e in load_lts
                if start_str_day <= datetime.fromtimestamp(e["start"] / 1000.0).strftime("%Y-%m-%d") < end_str_day
            ), 2)

        # Peak power from LTS
        peak_solar_kw = 0.0
        power_lts = lts_data.get(solar_power_eid, [])
        if not power_lts or max((float(e.get("max", 0) or 0) for e in power_lts), default=0.0) <= 0:
            power_lts = lts_data.get("sensor.solar_power", [])
        if power_lts:
            max_p = max((float(e.get("max", 0) or 0) for e in power_lts), default=0.0)
            if max_p > 50:
                peak_solar_kw = round(max_p / 1000.0, 2)
            elif max_p > 0:
                peak_solar_kw = round(max_p, 2)

        if peak_solar_kw <= 0.0 and total_solar_kwh > 0.0 and days_tracked > 0:
            max_daily_kwh = max([d["kwh"] for d in daily_breakdown]) if daily_breakdown else 0.0
            peak_solar_kw = round(max_daily_kwh / 4.8, 1) if max_daily_kwh > 0 else 0.0

        has_data = total_solar_kwh > 0.0 or peak_solar_kw > 0.0
        if has_data or days_tracked > 0:
            solar_savings = round(total_solar_kwh * (kwh_cost or 0.13), 2)
            solar_ev_coverage_pct = 0.0
            if home_charging_kwh > 0:
                solar_ev_coverage_pct = min(100.0, round((total_solar_kwh / home_charging_kwh) * 100.0, 1))
            elif total_solar_kwh > 0:
                solar_ev_coverage_pct = 100.0

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
                "days_tracked": days_tracked,
                "total_days": total_days,
                "is_partial_period": is_partial_period,
            }

    # -------------------------------------------------------------------------
    # 2. FALLBACK: REST History API (/api/history/period/...)
    # -------------------------------------------------------------------------
    # Used when WebSocket is unreachable or if entities lack state_class/statistics.
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

    entity_map = {}
    if data and isinstance(data, list):
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

    # Partial period tracking
    days_tracked = len(daily_breakdown)
    is_partial_period = (days_tracked < (total_days - 1)) and (days_tracked > 0) and (total_days > 3)

    # Calculations
    has_data = total_solar_kwh > 0.0 or peak_solar_kw > 0.0
    solar_savings = round(total_solar_kwh * (kwh_cost or 0.13), 2)

    solar_ev_coverage_pct = 0.0
    if home_charging_kwh > 0:
        solar_ev_coverage_pct = min(100.0, round((total_solar_kwh / home_charging_kwh) * 100.0, 1))
    elif total_solar_kwh > 0:
        solar_ev_coverage_pct = 100.0

    clean_ev_kwh = min(total_solar_kwh, home_charging_kwh)
    clean_miles_covered = round(clean_ev_kwh * 3.7, 1)
    solar_surplus_kwh = max(0.0, round(total_solar_kwh - home_charging_kwh, 2))

    self_consumption_pct = 100.0
    if total_solar_kwh > 0 and grid_export_kwh <= total_solar_kwh:
        self_consumption_pct = round(((total_solar_kwh - grid_export_kwh) / total_solar_kwh) * 100.0, 1)

    # If peak power sensor returned 0.0 but energy was generated, estimate realistic peak from best day
    if peak_solar_kw <= 0.0 and total_solar_kwh > 0.0 and days_tracked > 0:
        max_daily_kwh = max([d["kwh"] for d in daily_breakdown]) if daily_breakdown else 0.0
        peak_solar_kw = round(max_daily_kwh / 4.8, 1) if max_daily_kwh > 0 else 0.0

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
        "days_tracked": days_tracked,
        "total_days": total_days,
        "is_partial_period": is_partial_period,
    }
