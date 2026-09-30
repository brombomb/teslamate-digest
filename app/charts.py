import io
import base64
from typing import Dict, Any, List, Optional
import matplotlib
matplotlib.use("Agg")  # Headless backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=140, facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_b64


def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=140, facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    data = buf.read()
    plt.close(fig)
    return data


def _get_chart_colors(theme: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    ct = theme.get("chart_theme", {}) if theme else {}
    return {
        "bg": ct.get("chart_bg", "#0f172a"),
        "plot_bg": ct.get("chart_plot_bg", ct.get("chart_bg", "#0f172a")),
        "text": ct.get("chart_text", "#f8fafc"),
        "muted": ct.get("chart_muted", "#94a3b8"),
        "grid": ct.get("chart_grid", "#1e293b"),
        "primary": ct.get("chart_primary", "#e82127"),
        "secondary": ct.get("chart_secondary", "#38bdf8"),
        "tertiary": ct.get("chart_tertiary", "#10b981"),
        "off_peak": ct.get("chart_off_peak", "#10b981"),
        "shoulder": ct.get("chart_shoulder", "#38bdf8"),
        "on_peak": ct.get("chart_on_peak", "#f59e0b"),
        "supercharger": ct.get("chart_supercharger", "#e82127")
    }


def generate_spend_chart(charging: Dict[str, Any], theme: Optional[Dict[str, Any]] = None, as_bytes: bool = False):
    """
    Horizontal breakdown chart of Charging Spend & Energy:
    Home Off-Peak, Home Shoulder, Home On-Peak, Supercharger.
    Fully styled to match the active theme.
    """
    c = _get_chart_colors(theme)
    categories = []
    costs = []
    kwhs = []
    colors = []

    rate_mode = charging.get("rate_mode", "tou")
    if rate_mode == "tiered":
        if charging.get("tier1_kwh", 0) > 0:
            categories.append("Home Tier 1 (Base)")
            costs.append(charging.get("tier1_spend", 0))
            kwhs.append(charging.get("tier1_kwh", 0))
            colors.append(c["off_peak"])

        if charging.get("tier2_kwh", 0) > 0:
            categories.append("Home Tier 2")
            costs.append(charging.get("tier2_spend", 0))
            kwhs.append(charging.get("tier2_kwh", 0))
            colors.append(c["shoulder"])

        if charging.get("tier3_kwh", 0) > 0:
            categories.append("Home Tier 3")
            costs.append(charging.get("tier3_spend", 0))
            kwhs.append(charging.get("tier3_kwh", 0))
            colors.append(c["on_peak"])
    elif rate_mode == "flat":
        if charging.get("home_kwh", 0) > 0:
            categories.append("Home AC Charging")
            costs.append(charging.get("home_spend", 0))
            kwhs.append(charging.get("home_kwh", 0))
            colors.append(c["primary"])
    else:  # tou
        if charging.get("off_peak_kwh", 0) > 0:
            categories.append("Home Off-Peak")
            costs.append(charging.get("off_peak_spend", charging.get("off_peak_kwh", 0) * 0.10))
            kwhs.append(charging.get("off_peak_kwh", 0))
            colors.append(c["off_peak"])

        if charging.get("shoulder_kwh", 0) > 0:
            categories.append("Home Shoulder")
            costs.append(charging.get("shoulder_spend", charging.get("shoulder_kwh", 0) * 0.14))
            kwhs.append(charging.get("shoulder_kwh", 0))
            colors.append(c["shoulder"])

        if charging.get("on_peak_kwh", 0) > 0:
            categories.append("Home On-Peak")
            costs.append(charging.get("on_peak_spend", charging.get("on_peak_kwh", 0) * 0.20))
            kwhs.append(charging.get("on_peak_kwh", 0))
            colors.append(c["on_peak"])

    if charging.get("supercharger_kwh", 0) > 0:
        categories.append("Supercharging")
        costs.append(charging.get("supercharger_spend", 0))
        kwhs.append(charging.get("supercharger_kwh", 0))
        colors.append(c["supercharger"])

    if not categories:
        categories = ["Home"]
        costs = [charging.get("total_spend", 0)]
        kwhs = [charging.get("total_energy_used_kwh", 0)]
        colors = [c["primary"]]

    fig, ax = plt.subplots(figsize=(6.5, 2.4), facecolor=c["bg"])
    ax.set_facecolor(c["plot_bg"])

    y_pos = np.arange(len(categories))
    bars = ax.barh(y_pos, costs, color=colors, height=0.45, edgecolor="none", zorder=3)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(categories, color=c["text"], fontsize=10, fontweight="bold")
    ax.invert_yaxis()

    ax.tick_params(axis="x", colors=c["muted"], labelsize=9)
    ax.tick_params(axis="y", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.grid(axis="x", color=c["grid"], linestyle="--", alpha=0.7, zorder=1)

    for bar, cost, kwh in zip(bars, costs, kwhs):
        width = bar.get_width()
        label_text = f" ${cost:.2f} ({kwh:.1f} kWh)"
        ax.text(width + (max(costs) * 0.02 if costs else 1), bar.get_y() + bar.get_height() / 2,
                label_text, va="center", ha="left", color=c["text"], fontsize=9, fontweight="bold")

    ax.set_xlim(0, max(costs) * 1.35 if costs and max(costs) > 0 else 10)
    ax.set_title("Charging Spend Breakdown ($)", color=c["text"], fontsize=11, fontweight="bold", pad=10, loc="left")

    return _fig_to_bytes(fig) if as_bytes else _fig_to_base64(fig)


def generate_tou_chart(
    hourly_kwh: List[float],
    off_peak_start: int = 21,
    off_peak_end: int = 9,
    peak_start: int = 13,
    peak_end: int = 19,
    theme: Optional[Dict[str, Any]] = None,
    as_bytes: bool = False
):
    """
    24-hour distribution bar chart showing off-peak, shoulder, and on-peak hours.
    Styled according to active theme.
    """
    c = _get_chart_colors(theme)
    fig, ax = plt.subplots(figsize=(7, 2.5), facecolor=c["bg"])
    ax.set_facecolor(c["plot_bg"])

    hours = list(range(24))
    bar_colors = []

    for h in hours:
        is_off_peak = (h >= off_peak_start or h < off_peak_end) if off_peak_start > off_peak_end else (off_peak_start <= h < off_peak_end)
        is_peak = (peak_start <= h < peak_end)
        if is_off_peak:
            bar_colors.append(c["off_peak"])
        elif is_peak:
            bar_colors.append(c["on_peak"])
        else:
            bar_colors.append(c["shoulder"])

    # Shaded off-peak background region
    ax.axvspan(-0.5, off_peak_end - 0.5, facecolor=c["off_peak"], alpha=0.15, label="Off-Peak")
    ax.axvspan(off_peak_start - 0.5, 23.5, facecolor=c["off_peak"], alpha=0.15)
    # Shaded on-peak background
    ax.axvspan(peak_start - 0.5, peak_end - 0.5, facecolor=c["on_peak"], alpha=0.15, label="On-Peak")

    ax.bar(hours, hourly_kwh, color=bar_colors, width=0.75, zorder=3)

    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21])
    ax.set_xticklabels(["12am", "3am", "6am", "9am", "12pm", "3pm", "6pm", "9pm"], color=c["muted"], fontsize=8.5)
    ax.tick_params(axis="y", colors=c["muted"], labelsize=8.5)
    ax.tick_params(axis="both", length=0)

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.grid(axis="y", color=c["grid"], linestyle="--", alpha=0.7, zorder=1)
    ax.set_ylabel("kWh Drawn", color=c["muted"], fontsize=8.5)
    ax.set_title("24-Hour TOU Charging Distribution", color=c["text"], fontsize=10.5, fontweight="bold", pad=10, loc="left")

    return _fig_to_bytes(fig) if as_bytes else _fig_to_base64(fig)


def generate_battery_trend_chart(battery_data: Dict[str, Any], theme: Optional[Dict[str, Any]] = None, as_bytes: bool = False):
    """
    Battery health trend chart showing estimated 100% rated range over time per car.
    Styled according to active theme.
    """
    c = _get_chart_colors(theme)
    fig, ax = plt.subplots(figsize=(6.5, 2.4), facecolor=c["bg"])
    ax.set_facecolor(c["plot_bg"])

    cars = battery_data.get("cars", [])
    car_palette = [c["primary"], c["secondary"], c["tertiary"]]

    has_data = False
    for idx, car in enumerate(cars):
        trend = car.get("trend_series", [])
        if len(trend) >= 2:
            has_data = True
            months = [t["month"].split("-")[1] + "/" + t["month"].split("-")[0][2:] for t in trend]
            ranges = [t["avg_range_mi"] for t in trend]
            color = car_palette[idx % len(car_palette)]
            ax.plot(months, ranges, marker="o", markersize=5, linewidth=2, color=color, label=f"{car['car_name']} ({car['model']})", zorder=3)
            ax.annotate(f"{ranges[-1]:.0f} mi", (months[-1], ranges[-1]), textcoords="offset points", xytext=(8, -2), color=color, fontweight="bold", fontsize=8.5)

    if not has_data:
        for idx, car in enumerate(cars):
            color = car_palette[idx % len(car_palette)]
            cur_r = car.get("current_estimated_range_mi", 280)
            ax.bar(car["car_name"], cur_r, color=color, width=0.4, label=f"{car['car_name']} ({cur_r:.0f} mi)")
        ax.set_ylabel("100% Rated Range (mi)", color=c["muted"], fontsize=8.5)

    ax.tick_params(axis="both", colors=c["muted"], labelsize=8.5, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.grid(axis="y", color=c["grid"], linestyle="--", alpha=0.7, zorder=1)
    ax.legend(facecolor=c["plot_bg"], edgecolor=c["grid"], labelcolor=c["text"], fontsize=8, loc="upper right")
    ax.set_title("100% Battery Rated Range Trend (mi)", color=c["text"], fontsize=10.5, fontweight="bold", pad=10, loc="left")

    return _fig_to_bytes(fig) if as_bytes else _fig_to_base64(fig)


def generate_tpms_diagram(tpms_dict: Dict[str, Any], theme: Optional[Dict[str, Any]] = None, as_bytes: bool = False):
    """
    Visual 4-corner tire pressure graphic with theme-responsive aesthetics.
    """
    c = _get_chart_colors(theme)
    fig, ax = plt.subplots(figsize=(4.5, 3.2), facecolor=c["bg"])
    ax.set_facecolor(c["plot_bg"])

    # Draw minimalist car body
    car_body = patches.FancyBboxPatch((1.2, 0.8), 2.1, 4.4, boxstyle="round,pad=0.3",
                                      facecolor=c["plot_bg"], edgecolor=c["grid"], linewidth=1.5, zorder=2)
    ax.add_patch(car_body)

    # Windshield curve
    windshield = patches.Arc((2.25, 3.8), 1.5, 0.8, angle=0, theta1=0, theta2=180, color=c["muted"], linewidth=1.5, zorder=3)
    ax.add_patch(windshield)

    # Tires: FL, FR, RL, RR
    tires = [
        {"name": "FL", "x": 0.6, "y": 4.0, "psi": tpms_dict.get("fl_psi", 42.0), "color": tpms_dict.get("fl_info", {}).get("color", c["primary"])},
        {"name": "FR", "x": 3.9, "y": 4.0, "psi": tpms_dict.get("fr_psi", 42.0), "color": tpms_dict.get("fr_info", {}).get("color", c["primary"])},
        {"name": "RL", "x": 0.6, "y": 1.4, "psi": tpms_dict.get("rl_psi", 42.0), "color": tpms_dict.get("rl_info", {}).get("color", c["primary"])},
        {"name": "RR", "x": 3.9, "y": 1.4, "psi": tpms_dict.get("rr_psi", 42.0), "color": tpms_dict.get("rr_info", {}).get("color", c["primary"])},
    ]

    for t in tires:
        tire_patch = patches.FancyBboxPatch((t["x"] - 0.25, t["y"] - 0.45), 0.5, 0.9,
                                            boxstyle="round,pad=0.1", facecolor=c["bg"],
                                            edgecolor=t["color"], linewidth=2, zorder=4)
        ax.add_patch(tire_patch)
        ax.text(t["x"], t["y"], f"{t['psi']:.1f}\nPSI", color=c["text"], fontsize=7.5,
                fontweight="bold", ha="center", va="center", zorder=5)

    ax.text(2.25, 4.8, "FRONT", color=c["muted"], fontsize=7.5, fontweight="bold", ha="center")
    ax.text(2.25, 0.4, "REAR", color=c["muted"], fontsize=7.5, fontweight="bold", ha="center")

    ax.set_xlim(-0.2, 4.7)
    ax.set_ylim(0.0, 5.2)
    ax.axis("off")

    return _fig_to_bytes(fig) if as_bytes else _fig_to_base64(fig)
