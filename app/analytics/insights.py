from typing import Dict, Any, List, Optional
from datetime import datetime


def calculate_mom_deltas(
    current: Dict[str, Any],
    previous: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calculates month-over-month (or period-over-period) deltas for key summary metrics.
    Returns delta objects with diff, percentage change, and display formatting.
    """
    if not previous:
        return {}

    deltas = {}

    # 1. Total Miles / Distance
    cur_miles = current.get("trips", {}).get("total_miles", 0.0)
    prev_miles = previous.get("trips", {}).get("total_miles", 0.0)
    if prev_miles > 0:
        diff_miles = round(cur_miles - prev_miles, 1)
        pct_miles = round((diff_miles / prev_miles) * 100.0, 1)
        deltas["miles"] = {
            "diff": diff_miles,
            "pct": pct_miles,
            "direction": "up" if diff_miles > 0 else ("down" if diff_miles < 0 else "flat"),
            "label": f"{'+' if diff_miles > 0 else ''}{diff_miles:,.0f} mi ({'+' if pct_miles > 0 else ''}{pct_miles:.1f}%)",
            "arrow": "▲" if diff_miles > 0 else ("▼" if diff_miles < 0 else "—"),
        }

    # 2. Charging Spend
    cur_spend = current.get("charging", {}).get("total_spend", 0.0)
    prev_spend = previous.get("charging", {}).get("total_spend", 0.0)
    if prev_spend > 0:
        diff_spend = round(cur_spend - prev_spend, 2)
        pct_spend = round((diff_spend / prev_spend) * 100.0, 1)
        deltas["spend"] = {
            "diff": diff_spend,
            "pct": pct_spend,
            "direction": "up" if diff_spend > 0 else ("down" if diff_spend < 0 else "flat"),
            "label": f"{'+' if diff_spend > 0 else ''}${diff_spend:,.2f} ({'+' if pct_spend > 0 else ''}{pct_spend:.1f}%)",
            "arrow": "▲" if diff_spend > 0 else ("▼" if diff_spend < 0 else "—"),
        }

    # 3. Gas Savings
    cur_savings = current.get("charging", {}).get("gas_savings", {}).get("net_savings", 0.0)
    prev_savings = previous.get("charging", {}).get("gas_savings", {}).get("net_savings", 0.0)
    if prev_savings > 0:
        diff_savings = round(cur_savings - prev_savings, 2)
        pct_savings = round((diff_savings / prev_savings) * 100.0, 1)
        deltas["gas_savings"] = {
            "diff": diff_savings,
            "pct": pct_savings,
            "direction": "up" if diff_savings > 0 else ("down" if diff_savings < 0 else "flat"),
            "label": f"{'+' if diff_savings > 0 else ''}${diff_savings:,.2f}",
            "arrow": "▲" if diff_savings > 0 else ("▼" if diff_savings < 0 else "—"),
        }

    # 4. Driving Efficiency (Wh/mi)
    cur_wh = current.get("efficiency", {}).get("avg_wh_per_mile", 0.0)
    prev_wh = previous.get("efficiency", {}).get("avg_wh_per_mile", 0.0)
    if prev_wh > 0 and cur_wh > 0:
        diff_wh = round(cur_wh - prev_wh, 1)
        deltas["efficiency"] = {
            "diff": diff_wh,
            "direction": "up" if diff_wh > 0 else ("down" if diff_wh < 0 else "flat"),
            "label": f"{'+' if diff_wh > 0 else ''}{diff_wh:.0f} Wh/mi",
            "arrow": "▲" if diff_wh > 0 else ("▼" if diff_wh < 0 else "—"),
        }

    return deltas


def generate_digest_insights(
    telemetry: Dict[str, Any],
    config: Any,
    prev_telemetry: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates telemetry to synthesize a prioritized 'Worth a look' diagnostic block
    and a balancing 'Highlights & Wins' summary.
    """
    items: List[Dict[str, Any]] = []
    wins: List[str] = []

    health = telemetry.get("health", {})
    cars_health = health.get("cars", [])
    compliance = telemetry.get("compliance", {})
    vampire = telemetry.get("vampire", {})
    charging = telemetry.get("charging", {})
    solar = telemetry.get("solar", {})
    achievements = telemetry.get("achievements", {})
    battery = telemetry.get("battery", {})

    # 1. Check Tire Pressures
    for car in cars_health:
        cname = car.get("car_name", "Vehicle")
        tpms = car.get("tpms", {})
        alerts = car.get("tpms_alerts", [])
        if alerts:
            # High severity TPMS alert
            primary_alert = alerts[0]
            items.append({
                "type": "tpms",
                "severity": "warning",
                "badge": "TPMS Check",
                "title": f"{cname}: {primary_alert}",
                "detail": f"Target cold pressure is 42.0 PSI (2.9 bar). Check and adjust pressures before driving.",
                "icon": "⚠️",
                "color": "#f59e0b",
            })
            break
        else:
            # Check for values > 46.5 or < 38.0 PSI
            readings = [
                tpms.get("fl_psi"),
                tpms.get("fr_psi"),
                tpms.get("rl_psi"),
                tpms.get("rr_psi"),
            ]
            valid_psi = [r for r in readings if r is not None and r > 0]
            if valid_psi:
                max_psi = max(valid_psi)
                min_psi = min(valid_psi)
                if max_psi > 46.5:
                    items.append({
                        "type": "tpms",
                        "severity": "warning",
                        "badge": "High Pressure",
                        "title": f"{cname}: Cold tire pressure elevated at {max_psi:.1f} PSI",
                        "detail": f"Target is 42.0 PSI (2.9 bar). High pressure causes center tread wear and a stiffer ride.",
                        "icon": "⚠️",
                        "color": "#f59e0b",
                    })
                    break
                elif min_psi < 38.0:
                    items.append({
                        "type": "tpms",
                        "severity": "warning",
                        "badge": "Low Pressure",
                        "title": f"{cname}: Low tire pressure at {min_psi:.1f} PSI",
                        "detail": f"Target is 42.0 PSI cold. Low tire pressure degrades efficiency and increases edge wear.",
                        "icon": "⚠️",
                        "color": "#f59e0b",
                    })
                    break

    # 2. Check Tire Rotation Calibration & Status
    for car in cars_health:
        cname = car.get("car_name", "Vehicle")
        rot = car.get("tire_rotation", {})
        if rot.get("is_uncalibrated"):
            items.append({
                "type": "maintenance",
                "severity": "info",
                "badge": "Calibration",
                "title": f"{cname}: No tire rotation history recorded at {rot.get('current_odometer', 0):,.0f} mi",
                "detail": "Set your last rotation odometer in Settings to enable tire wear and rotation alerts.",
                "icon": "🔧",
                "color": "#38bdf8",
                "action_url": "#maintenance-settings",
                "action_text": "Set rotation history →",
            })
            break
        elif rot.get("is_overdue"):
            items.append({
                "type": "maintenance",
                "severity": "warning",
                "badge": "Rotation Due",
                "title": f"{cname}: Tire rotation recommended ({rot.get('dist_driven_since', 0):,.0f} / {rot.get('interval', 6250):,.0f} mi)",
                "detail": "Rotating tires every 6,250 miles ensures even tread wear and maximizes tire lifespan.",
                "icon": "🔧",
                "color": "#f59e0b",
            })
            break

    # 3. Check Vampire / Phantom Standby Drain
    idle_hrs = vampire.get("total_idle_hours", 0.0)
    loss_kwh = vampire.get("estimated_loss_kwh", 0.0)
    loss_cost = vampire.get("estimated_cost", 0.0)
    total_spend = charging.get("total_spend", 0.0)
    avg_standby_watts = (loss_kwh * 1000.0 / idle_hrs) if idle_hrs > 0 else 0.0

    if loss_kwh >= 15.0 and (avg_standby_watts >= 150.0 or (total_spend > 0 and (loss_cost / total_spend) >= 0.12)):
        spend_pct = (loss_cost / total_spend * 100.0) if total_spend > 0 else 0.0
        items.append({
            "type": "vampire",
            "severity": "info",
            "badge": "Standby Drain",
            "title": f"Standby loss: {loss_kwh:.1f} kWh over {idle_hrs:,.0f} hrs (~{avg_standby_watts:.0f} W avg, ${loss_cost:.2f})",
            "detail": f"Standby consumption accounted for {spend_pct:.0f}% of total charging spend. Check Sentry Mode or Cabin Overheat settings if parked safely.",
            "icon": "🔋",
            "color": "#a855f7",
        })

    # 4. Deep Battery Dwell (< 20% SoC)
    hrs_below_20 = compliance.get("hours_below_20", 0.0)
    pct_below_20 = compliance.get("pct_below_20", 0.0)
    if hrs_below_20 >= 15.0 or pct_below_20 >= 4.0:
        items.append({
            "type": "compliance",
            "severity": "warning",
            "badge": "Low SoC Dwell",
            "title": f"Pack stress: {hrs_below_20:,.0f} hours spent resting below 20% SoC ({pct_below_20:.1f}%)",
            "detail": "Extended storage at low state of charge increases internal resistance and accelerates cell aging.",
            "icon": "⚠️",
            "color": "#f59e0b",
        })

    # 5. Partial Solar Telemetry Note
    if solar.get("has_data") and solar.get("is_partial_period"):
        items.append({
            "type": "solar",
            "severity": "info",
            "badge": "Partial Data",
            "title": f"Solar data recorded for {solar.get('days_tracked')} of {solar.get('total_days')} days",
            "detail": f"Solar EV coverage ({solar.get('solar_ev_coverage_pct', 0):.0f}%) and self-use reflect only days where solar monitoring was active.",
            "icon": "☀️",
            "color": "#06b6d4",
        })

    # Limit to top 3 prioritized diagnostic items
    prioritized_items = items[:3]

    # --- BALANCING POSITIVE WINS & HIGHLIGHTS ---
    gas_saved = charging.get("gas_savings", {}).get("net_savings", 0.0)
    if gas_saved > 0:
        wins.append(f"${gas_saved:,.0f} saved vs gas")

    off_peak_score = charging.get("off_peak_score_pct", 0.0)
    if off_peak_score >= 85.0:
        wins.append(f"{off_peak_score:.0f}% off-peak charging")

    battery_cars = battery.get("cars", [])
    if battery_cars:
        top_retained = max([c.get("capacity_retained_pct", 0.0) for c in battery_cars])
        grade = battery_cars[0].get("health_grade", "A")
        if top_retained > 0:
            wins.append(f"Battery at {top_retained:.1f}% (Grade {grade})")

    earned_badges = achievements.get("earned_this_period", [])
    if earned_badges:
        count = len(earned_badges)
        wins.append(f"{count} new badge{'s' if count > 1 else ''}")

    clean_miles = solar.get("clean_miles_covered", 0.0)
    if clean_miles and clean_miles > 50:
        wins.append(f"{clean_miles:,.0f} clean solar mi")

    wins_summary = " · ".join(wins) if wins else ""

    return {
        "items": prioritized_items,
        "diagnostic_items": prioritized_items,
        "has_items": len(prioritized_items) > 0,
        "wins_summary": wins_summary,
        "deltas": calculate_mom_deltas(telemetry, prev_telemetry),
    }
