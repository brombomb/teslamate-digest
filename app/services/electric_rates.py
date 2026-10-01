import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
CACHE_FILE = DATA_DIR / "electric_rates_cache.json"
CACHE_TTL_SECONDS = 7 * 86400  # 7 days

# Curated regional tariff profiles for instant matching and robust fallbacks
COLORADO_RATE_PLANS: List[Dict[str, Any]] = [
    {
        "id": "xcel_colorado_tou",
        "utility_name": "Public Service Co of Colorado (Xcel Energy)",
        "utility_id": "15466",
        "plan_name": "Residential Energy Time-of-Use (Schedule RE-TOU)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.090, Shoulder: $0.130, On-Peak: $0.190 (9 PM–9 AM Off-Peak, Weekends Off-Peak)",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.09,
        "shoulder_kwh_cost": 0.13,
        "on_peak_kwh_cost": 0.19,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.11,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.17,
        "tier3_kwh_cost": 0.26,
        "average_kwh_cost": 0.13,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Schedule RE-TOU: Summer on-peak 1-7 PM weekdays; shoulder 9 AM-1 PM & 7-9 PM; off-peak 9 PM-9 AM; weekends 100% off-peak."
    },
    {
        "id": "xcel_colorado_tiered",
        "utility_name": "Public Service Co of Colorado (Xcel Energy)",
        "utility_id": "15466",
        "plan_name": "Residential Service Schedule R (Tiered Baseline)",
        "rate_mode": "tiered",
        "badge": "Tiered",
        "description": "Tier 1 (≤500 kWh): $0.115, Tier 2 (≤1000 kWh): $0.165, Tier 3 (>1000 kWh): $0.215",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.115,
        "shoulder_kwh_cost": 0.165,
        "on_peak_kwh_cost": 0.215,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.115,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.165,
        "tier3_kwh_cost": 0.215,
        "average_kwh_cost": 0.145,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Standard non-TOU tiered rate structure based on cumulative monthly kilowatt-hour consumption."
    },
    {
        "id": "xcel_colorado_ev_rd",
        "utility_name": "Public Service Co of Colorado (Xcel Energy)",
        "utility_id": "15466",
        "plan_name": "Residential Demand & EV Smart Charging (Schedule RD)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Super Off-Peak: $0.065, Shoulder: $0.115, On-Peak: $0.245 (9 PM–9 AM Super Off-Peak)",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.065,
        "shoulder_kwh_cost": 0.115,
        "on_peak_kwh_cost": 0.245,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 14,
        "peak_end_hour": 18,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.11,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.17,
        "tier3_kwh_cost": 0.26,
        "average_kwh_cost": 0.12,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Optimized EV home charging rate with deep overnight off-peak discounts and higher 2-6 PM summer peak demand."
    },
    {
        "id": "united_power_tou",
        "utility_name": "United Power",
        "utility_id": "19436",
        "plan_name": "Residential Time-of-Day (Schedule R-TOU)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.078, Shoulder: $0.125, Peak: $0.228 (10 PM–6 AM Off-Peak)",
        "source": "Colorado Electric Co-op Tariff",
        "off_peak_kwh_cost": 0.078,
        "shoulder_kwh_cost": 0.125,
        "on_peak_kwh_cost": 0.228,
        "off_peak_start_hour": 22,
        "off_peak_end_hour": 6,
        "peak_start_hour": 14,
        "peak_end_hour": 20,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.11,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.16,
        "tier3_kwh_cost": 0.24,
        "average_kwh_cost": 0.13,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Cooperative electric utility service north & east of Denver metro area."
    },
    {
        "id": "colorado_springs_flat",
        "utility_name": "Colorado Springs Utilities",
        "utility_id": "3989",
        "plan_name": "Residential Electric Service (Schedule E-1)",
        "rate_mode": "flat",
        "badge": "Flat",
        "description": "Uniform flat electricity rate: $0.128/kWh",
        "source": "Municipal Utility Tariff",
        "off_peak_kwh_cost": 0.128,
        "shoulder_kwh_cost": 0.128,
        "on_peak_kwh_cost": 0.128,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.128,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.128,
        "tier3_kwh_cost": 0.128,
        "average_kwh_cost": 0.128,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Standard municipal flat residential rate with uniform energy charge."
    }
]

CALIFORNIA_RATE_PLANS: List[Dict[str, Any]] = [
    {
        "id": "pge_ev2a_tou",
        "utility_name": "Pacific Gas & Electric (PG&E)",
        "utility_id": "14328",
        "plan_name": "EV & Home Charging Time-of-Use (Schedule EV2-A)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.280, Partial-Peak: $0.440, Peak: $0.580 (12 AM–3 PM Off-Peak)",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.28,
        "shoulder_kwh_cost": 0.44,
        "on_peak_kwh_cost": 0.58,
        "off_peak_start_hour": 0,
        "off_peak_end_hour": 15,
        "peak_start_hour": 16,
        "peak_end_hour": 21,
        "weekends_are_off_peak": False,
        "tier1_max_kwh": 350.0,
        "tier1_kwh_cost": 0.32,
        "tier2_max_kwh": 1400.0,
        "tier2_kwh_cost": 0.42,
        "tier3_kwh_cost": 0.52,
        "average_kwh_cost": 0.38,
        "effective_year": 2026,
        "is_live": False,
        "notes": "PG&E EV2-A whole-home charging rate with 4-9 PM daily peak and 12 AM - 3 PM off-peak window."
    },
    {
        "id": "pge_tiered_e1",
        "utility_name": "Pacific Gas & Electric (PG&E)",
        "utility_id": "14328",
        "plan_name": "Residential Tiered Rate Plan (Schedule E-1)",
        "rate_mode": "tiered",
        "badge": "Tiered",
        "description": "Tier 1 (≤350 kWh): $0.340, Tier 2 (≤1400 kWh): $0.430, Tier 3 (>1400 kWh): $0.520",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.34,
        "shoulder_kwh_cost": 0.43,
        "on_peak_kwh_cost": 0.52,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 350.0,
        "tier1_kwh_cost": 0.34,
        "tier2_max_kwh": 1400.0,
        "tier2_kwh_cost": 0.43,
        "tier3_kwh_cost": 0.52,
        "average_kwh_cost": 0.39,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Baseline allowance usage tiers with progressive steps for higher consumption."
    },
    {
        "id": "sce_tou_d_prime",
        "utility_name": "Southern California Edison (SCE)",
        "utility_id": "17609",
        "plan_name": "Clean Energy & EV Tariff (TOU-D-PRIME)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.240, Mid-Peak: $0.380, Peak: $0.560 (8 AM–4 PM Super Off-Peak)",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.24,
        "shoulder_kwh_cost": 0.38,
        "on_peak_kwh_cost": 0.56,
        "off_peak_start_hour": 8,
        "off_peak_end_hour": 16,
        "peak_start_hour": 16,
        "peak_end_hour": 21,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 400.0,
        "tier1_kwh_cost": 0.28,
        "tier2_max_kwh": 1200.0,
        "tier2_kwh_cost": 0.39,
        "tier3_kwh_cost": 0.50,
        "average_kwh_cost": 0.33,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Specifically crafted for EV, battery storage, and heat pump owners in Southern California."
    },
    {
        "id": "sdge_ev_tou5",
        "utility_name": "San Diego Gas & Electric (SDG&E)",
        "utility_id": "16609",
        "plan_name": "Electric Vehicle Time-of-Use (Schedule EV-TOU-5)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Super Off-Peak: $0.150, Off-Peak: $0.420, Peak: $0.720 (12 AM–6 AM Off-Peak)",
        "source": "OpenEI URDB (Utility Rate Database)",
        "off_peak_kwh_cost": 0.15,
        "shoulder_kwh_cost": 0.42,
        "on_peak_kwh_cost": 0.72,
        "off_peak_start_hour": 0,
        "off_peak_end_hour": 6,
        "peak_start_hour": 16,
        "peak_end_hour": 21,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 350.0,
        "tier1_kwh_cost": 0.35,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.45,
        "tier3_kwh_cost": 0.60,
        "average_kwh_cost": 0.42,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Low super off-peak rate for midnight-6 AM EV charging with higher peak charges."
    },
    {
        "id": "smud_tod",
        "utility_name": "Sacramento Municipal Utility District (SMUD)",
        "utility_id": "16572",
        "plan_name": "Residential Time-of-Day (5-8 PM Peak)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.138, Mid-Peak: $0.188, Peak: $0.328 (Weekends 100% Off-Peak)",
        "source": "Municipal Utility Tariff",
        "off_peak_kwh_cost": 0.138,
        "shoulder_kwh_cost": 0.188,
        "on_peak_kwh_cost": 0.328,
        "off_peak_start_hour": 20,
        "off_peak_end_hour": 12,
        "peak_start_hour": 17,
        "peak_end_hour": 20,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.14,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.19,
        "tier3_kwh_cost": 0.30,
        "average_kwh_cost": 0.18,
        "effective_year": 2026,
        "is_live": False,
        "notes": "SMUD public power rate with compact 3-hour evening peak and all weekends completely off-peak."
    }
]

TEXAS_RATE_PLANS: List[Dict[str, Any]] = [
    {
        "id": "ercot_free_nights",
        "utility_name": "Oncor / ERCOT Retail Competitive",
        "utility_id": "14006",
        "plan_name": "EV Free Nights & Solar Weekends (9 PM–6 AM)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Night Off-Peak: $0.000, Daytime: $0.140, On-Peak: $0.220 (100% Free Night Charging)",
        "source": "ERCOT Retail Market",
        "off_peak_kwh_cost": 0.00,
        "shoulder_kwh_cost": 0.14,
        "on_peak_kwh_cost": 0.22,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 6,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 1000.0,
        "tier1_kwh_cost": 0.12,
        "tier2_max_kwh": 2000.0,
        "tier2_kwh_cost": 0.16,
        "tier3_kwh_cost": 0.22,
        "average_kwh_cost": 0.13,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Popular Texas retail electric plan offering zero-cost energy for overnight EV charging."
    },
    {
        "id": "centerpoint_houston_flat",
        "utility_name": "CenterPoint Energy Houston",
        "utility_id": "8901",
        "plan_name": "Standard Residential Fixed Flat Rate",
        "rate_mode": "flat",
        "badge": "Flat",
        "description": "Uniform flat electricity rate: $0.135/kWh",
        "source": "ERCOT Delivery Tariff",
        "off_peak_kwh_cost": 0.135,
        "shoulder_kwh_cost": 0.135,
        "on_peak_kwh_cost": 0.135,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 1000.0,
        "tier1_kwh_cost": 0.135,
        "tier2_max_kwh": 2000.0,
        "tier2_kwh_cost": 0.135,
        "tier3_kwh_cost": 0.135,
        "average_kwh_cost": 0.135,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Fixed price residential contract without variable time or usage tier premiums."
    },
    {
        "id": "austin_energy_tiered",
        "utility_name": "Austin Energy",
        "utility_id": "1004",
        "plan_name": "Residential 3-Tier Conservation Rate Structure",
        "rate_mode": "tiered",
        "badge": "Tiered",
        "description": "Tier 1 (≤500 kWh): $0.078, Tier 2 (≤1000 kWh): $0.125, Tier 3 (>1000 kWh): $0.182",
        "source": "Municipal Utility Tariff",
        "off_peak_kwh_cost": 0.078,
        "shoulder_kwh_cost": 0.125,
        "on_peak_kwh_cost": 0.182,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.078,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.125,
        "tier3_kwh_cost": 0.182,
        "average_kwh_cost": 0.12,
        "effective_year": 2026,
        "is_live": False,
        "notes": "City of Austin stepped tier conservation structure encouraging efficient electric use."
    },
    {
        "id": "cps_energy_tou",
        "utility_name": "CPS Energy (San Antonio)",
        "utility_id": "3634",
        "plan_name": "Peak Capacity Time-of-Use Rate",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.082, Shoulder: $0.122, Peak: $0.198 (Weekends Off-Peak)",
        "source": "Municipal Utility Tariff",
        "off_peak_kwh_cost": 0.082,
        "shoulder_kwh_cost": 0.122,
        "on_peak_kwh_cost": 0.198,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 14,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 600.0,
        "tier1_kwh_cost": 0.09,
        "tier2_max_kwh": 1200.0,
        "tier2_kwh_cost": 0.14,
        "tier3_kwh_cost": 0.20,
        "average_kwh_cost": 0.125,
        "effective_year": 2026,
        "is_live": False,
        "notes": "CPS Energy San Antonio residential TOU rate for summer grid optimization."
    },
    {
        "id": "texas_tiered_credit",
        "utility_name": "Texas Retail Electric Provider",
        "utility_id": "0",
        "plan_name": "2-Tier Baseline Usage Credit Plan",
        "rate_mode": "tiered",
        "badge": "Tiered",
        "description": "Tier 1 (≤1000 kWh): $0.119, Tier 2 (≤2000 kWh): $0.158, Tier 3 (>2000 kWh): $0.198",
        "source": "Texas Power to Choose",
        "off_peak_kwh_cost": 0.119,
        "shoulder_kwh_cost": 0.158,
        "on_peak_kwh_cost": 0.198,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 1000.0,
        "tier1_kwh_cost": 0.119,
        "tier2_max_kwh": 2000.0,
        "tier2_kwh_cost": 0.158,
        "tier3_kwh_cost": 0.198,
        "average_kwh_cost": 0.138,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Typical tiered credit structure tailored for high-consumption single-family homes."
    }
]

NATIONAL_FALLBACK_PLANS: List[Dict[str, Any]] = [
    {
        "id": "standard_tou",
        "utility_name": "Standard Electric Utility",
        "utility_id": "0",
        "plan_name": "Residential Time-of-Use (Schedule TOU-3)",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Off-Peak: $0.100, Shoulder: $0.140, On-Peak: $0.200 (9 PM–9 AM Off-Peak, Weekends Off-Peak)",
        "source": "Standard TOU Profile",
        "off_peak_kwh_cost": 0.10,
        "shoulder_kwh_cost": 0.14,
        "on_peak_kwh_cost": 0.20,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.11,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.17,
        "tier3_kwh_cost": 0.26,
        "average_kwh_cost": 0.13,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Classic 3-period TOU tariff structure balanced for residential EV overnight charging."
    },
    {
        "id": "standard_tiered",
        "utility_name": "Standard Electric Utility",
        "utility_id": "0",
        "plan_name": "Standard 2-Tier Baseline Conservation Plan",
        "rate_mode": "tiered",
        "badge": "Tiered",
        "description": "Tier 1 (≤500 kWh): $0.110, Tier 2 (≤1000 kWh): $0.170, Tier 3 (>1000 kWh): $0.260",
        "source": "Standard Tiered Profile",
        "off_peak_kwh_cost": 0.11,
        "shoulder_kwh_cost": 0.17,
        "on_peak_kwh_cost": 0.26,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.11,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.17,
        "tier3_kwh_cost": 0.26,
        "average_kwh_cost": 0.14,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Baseline energy threshold rate with step increases as monthly consumption grows."
    },
    {
        "id": "national_average_flat",
        "utility_name": "U.S. National Average",
        "utility_id": "0",
        "plan_name": "U.S. National Baseline Flat Electricity Rate",
        "rate_mode": "flat",
        "badge": "Flat",
        "description": "Uniform flat electricity rate based on EIA Monthly: $0.145/kWh",
        "source": "U.S. EIA Electric Power Monthly",
        "off_peak_kwh_cost": 0.145,
        "shoulder_kwh_cost": 0.145,
        "on_peak_kwh_cost": 0.145,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.145,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.145,
        "tier3_kwh_cost": 0.145,
        "average_kwh_cost": 0.145,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Uniform average residential electricity rate across the United States."
    },
    {
        "id": "ev_overnight_tou",
        "utility_name": "Clean Energy Utility",
        "utility_id": "0",
        "plan_name": "Overnight EV Smart Charging Incentive Plan",
        "rate_mode": "tou",
        "badge": "TOU",
        "description": "Super Off-Peak: $0.075, Shoulder: $0.135, On-Peak: $0.235 (11 PM–7 AM Super Off-Peak)",
        "source": "Clean Grid EV Program",
        "off_peak_kwh_cost": 0.075,
        "shoulder_kwh_cost": 0.135,
        "on_peak_kwh_cost": 0.235,
        "off_peak_start_hour": 23,
        "off_peak_end_hour": 7,
        "peak_start_hour": 14,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.10,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.15,
        "tier3_kwh_cost": 0.22,
        "average_kwh_cost": 0.12,
        "effective_year": 2026,
        "is_live": False,
        "notes": "High-incentive overnight charging schedule designed to prevent daytime grid congestion."
    },
    {
        "id": "coop_public_flat",
        "utility_name": "Public Power & Electric Cooperative",
        "utility_id": "0",
        "plan_name": "Cooperative Rural / Municipal Standard Rate",
        "rate_mode": "flat",
        "badge": "Flat",
        "description": "Co-op / Municipal public power flat rate: $0.122/kWh",
        "source": "Cooperative Power Tariff",
        "off_peak_kwh_cost": 0.122,
        "shoulder_kwh_cost": 0.122,
        "on_peak_kwh_cost": 0.122,
        "off_peak_start_hour": 21,
        "off_peak_end_hour": 9,
        "peak_start_hour": 13,
        "peak_end_hour": 19,
        "weekends_are_off_peak": True,
        "tier1_max_kwh": 500.0,
        "tier1_kwh_cost": 0.122,
        "tier2_max_kwh": 1000.0,
        "tier2_kwh_cost": 0.122,
        "tier3_kwh_cost": 0.122,
        "average_kwh_cost": 0.122,
        "effective_year": 2026,
        "is_live": False,
        "notes": "Affordable fixed cost electric service provided by non-profit public utilities."
    }
]


def get_cached_plans(zip_code: str) -> Optional[List[Dict[str, Any]]]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if data.get("zip_code") == zip_code:
            cached_time = data.get("timestamp", 0)
            if time.time() - cached_time < CACHE_TTL_SECONDS:
                plans = data.get("plans")
                if isinstance(plans, list) and len(plans) > 0:
                    return plans
    except Exception as e:
        print(f"[ElectricRates] Cache read error: {e}")
    return None


def set_cached_plans(zip_code: str, plans: List[Dict[str, Any]]) -> None:
    try:
        data = {
            "zip_code": zip_code,
            "plans": plans,
            "rate_data": plans[0] if plans else {},
            "timestamp": int(time.time()),
            "cached_at": datetime.now().isoformat()
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[ElectricRates] Cache write error: {e}")


def parse_openei_tariff_item(item: Dict[str, Any], zip_code: str) -> Optional[Dict[str, Any]]:
    """
    Parses a live OpenEI URDB v7 JSON item into our normalized plan schema.
    """
    try:
        plan_name = item.get("name", "Residential Tariff")
        utility_name = item.get("utility", "Electric Utility")
        eia_id = str(item.get("eiaid", ""))
        rates_struct = item.get("energyratestructure", [])

        rates: List[float] = []
        is_tiered = False
        t1_max = 500.0
        t2_max = 1000.0
        t1_cost = 0.11
        t2_cost = 0.16
        t3_cost = 0.22

        if rates_struct and isinstance(rates_struct, list):
            for tier_group in rates_struct:
                if isinstance(tier_group, list):
                    for tier in tier_group:
                        r = tier.get("rate")
                        if r is not None:
                            rates.append(float(r))
                        if tier.get("max") is not None:
                            is_tiered = True
                            if t1_max == 500.0:
                                t1_max = float(tier.get("max", 500.0))

        if not rates:
            return None

        weekday_sched = item.get("energyweekdayschedule", [])
        weekend_sched = item.get("energyweekendschedule", [])

        weekends_off_peak = True
        if weekend_sched and weekday_sched and weekend_sched == weekday_sched:
            weekends_off_peak = False

        off_peak_start = 21
        off_peak_end = 9
        peak_start = 13
        peak_end = 19

        if weekday_sched and len(weekday_sched) >= 12:
            summer_day = weekday_sched[6]
            if len(summer_day) == 24:
                max_period = max(summer_day)
                min_period = min(summer_day)
                if max_period > min_period:
                    peak_hours = [h for h, p in enumerate(summer_day) if p == max_period]
                    if peak_hours:
                        peak_start = peak_hours[0]
                        peak_end = min(23, peak_hours[-1] + 1)
                    off_hours = [h for h, p in enumerate(summer_day) if p == min_period]
                    if off_hours:
                        off_peak_start = off_hours[0]
                        off_peak_end = min(23, off_hours[-1] + 1)

        sorted_rates = sorted(list(set(rates)))
        if is_tiered and len(sorted_rates) >= 2:
            rate_mode = "tiered"
            badge = "Tiered"
            t1_cost = sorted_rates[0]
            t2_cost = sorted_rates[1]
            t3_cost = sorted_rates[2] if len(sorted_rates) >= 3 else round(t2_cost * 1.3, 3)
            desc = f"Tier 1 (≤{int(t1_max)} kWh): ${t1_cost:.3f}, Tier 2 (≤{int(t2_max)} kWh): ${t2_cost:.3f}, Tier 3: ${t3_cost:.3f}"
            off_peak = t1_cost
            shoulder = t2_cost
            peak = t3_cost
        elif len(sorted_rates) >= 2:
            rate_mode = "tou"
            badge = "TOU"
            off_peak = sorted_rates[0]
            peak = sorted_rates[-1]
            shoulder = sorted_rates[1] if len(sorted_rates) >= 3 else round((off_peak + peak) / 2.0, 3)
            desc = f"Off-Peak: ${off_peak:.3f}, Shoulder: ${shoulder:.3f}, Peak: ${peak:.3f}"
        else:
            rate_mode = "flat"
            badge = "Flat"
            avg_cost = sorted_rates[0]
            desc = f"Flat: ${avg_cost:.3f}/kWh"
            off_peak = shoulder = peak = avg_cost

        plan_id = f"urdb_{item.get('label') or eia_id or str(hash(plan_name))[:8]}"

        return {
            "id": plan_id,
            "utility_name": utility_name,
            "utility_id": eia_id,
            "plan_name": plan_name,
            "rate_mode": rate_mode,
            "badge": badge,
            "description": desc,
            "source": "OpenEI URDB Live",
            "off_peak_kwh_cost": round(off_peak, 4),
            "shoulder_kwh_cost": round(shoulder, 4),
            "on_peak_kwh_cost": round(peak, 4),
            "off_peak_start_hour": off_peak_start,
            "off_peak_end_hour": off_peak_end,
            "peak_start_hour": peak_start,
            "peak_end_hour": peak_end,
            "weekends_are_off_peak": weekends_off_peak,
            "tier1_max_kwh": t1_max,
            "tier1_kwh_cost": round(t1_cost, 4),
            "tier2_max_kwh": t2_max,
            "tier2_kwh_cost": round(t2_cost, 4),
            "tier3_kwh_cost": round(t3_cost, 4),
            "average_kwh_cost": round(sorted_rates[0], 4),
            "effective_year": 2026,
            "is_live": True,
            "notes": item.get("description") or f"Imported via OpenEI URDB for ZIP {zip_code}."
        }
    except Exception as e:
        print(f"[ElectricRates] Error parsing OpenEI item: {e}")
        return None


def get_regional_curated_plans(zip_code: str) -> List[Dict[str, Any]]:
    """Returns top 5 curated tariff plans matching the state or region."""
    z = zip_code.strip()
    if z.startswith("80") or z.startswith("81"):
        return [dict(p) for p in COLORADO_RATE_PLANS]
    elif z.startswith(("90", "91", "92", "93", "94", "95", "96")):
        return [dict(p) for p in CALIFORNIA_RATE_PLANS]
    elif z.startswith(("75", "76", "77", "78", "79")):
        return [dict(p) for p in TEXAS_RATE_PLANS]
    return [dict(p) for p in NATIONAL_FALLBACK_PLANS]


async def search_electric_rate_plans(
    zip_code: str = "",
    openei_api_key: Optional[str] = None,
    eia_api_key: Optional[str] = None,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Returns exactly the top 5 matching electric rate plans for a given ZIP code.
    If OpenEI API key is provided, queries the live URDB database.
    Always supplements or falls back to curated regional tariff profiles so
    a complete top 5 list is guaranteed.
    """
    clean_zip = zip_code.strip() or "80005"
    if not force_refresh:
        cached = get_cached_plans(clean_zip)
        if cached and len(cached) >= 5:
            return cached[:5]

    matched_plans: List[Dict[str, Any]] = []
    seen_names = set()

    # 1. Attempt OpenEI URDB Live Query
    api_key_to_use = (openei_api_key or os.getenv("OPENEI_API_KEY", "")).strip()
    if api_key_to_use:
        try:
            url = "https://api.openei.org/utility_rates"
            params = {
                "version": "7",
                "format": "json",
                "api_key": api_key_to_use,
                "address": clean_zip,
                "sector": "Residential",
                "limit": "10"
            }
            async with httpx.AsyncClient(timeout=6.5) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for it in items:
                        parsed = parse_openei_tariff_item(it, clean_zip)
                        if parsed:
                            key = (parsed["utility_name"] + " " + parsed["plan_name"]).lower()
                            if key not in seen_names:
                                seen_names.add(key)
                                matched_plans.append(parsed)
                                if len(matched_plans) >= 5:
                                    break
        except Exception as e:
            print(f"[ElectricRates] OpenEI search query note: {e}")

    # 2. Fill remaining slots up to 5 with regional curated plans
    curated = get_regional_curated_plans(clean_zip)
    for p in curated:
        key = (p["utility_name"] + " " + p["plan_name"]).lower()
        if key not in seen_names:
            seen_names.add(key)
            matched_plans.append(p)
            if len(matched_plans) >= 5:
                break

    top5 = matched_plans[:5]
    set_cached_plans(clean_zip, top5)
    return top5


async def fetch_electric_rates(
    zip_code: str = "",
    openei_api_key: Optional[str] = None,
    eia_api_key: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Backwards-compatible helper returning the top primary matching electric rate profile.
    """
    plans = await search_electric_rate_plans(
        zip_code=zip_code,
        openei_api_key=openei_api_key,
        eia_api_key=eia_api_key,
        force_refresh=force_refresh
    )
    if plans:
        return plans[0]
    return dict(COLORADO_RATE_PLANS[0])
