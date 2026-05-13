"""
make_plots.py
=============
Generates publication-grade matplotlib charts for the README.

Outputs (all into ./docs):
  - validation_chart.png        : grouped-bar hover validation (4 aircraft)
  - power_curves.png            : 2x2 power-required curves (4 aircraft)
  - calculator_overview.png     : composite "screenshot" for the README hero
  - forward_flight_v1_v2.png    : Mavic 3 v1 vs v2 forward-flight comparison
"""

import os
from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np

from aircraft_db import (
    ALL_AIRCRAFT, PUBLISHED_HOVER_MIN, PUBLISHED_FORWARD_REFS,
    DJI_MAVIC_3,
)
from endurance import (
    hover_endurance_min, forward_endurance_and_range, power_curve,
    best_cruise_speed, hover_power_momentum_theory,
)


# --- Style ---------------------------------------------------------------
NAVY   = "#1f4d7a"
RUST   = "#c96a3a"
GREEN  = "#2e7d5b"
PURPLE = "#6b3e8a"   # 4th color for Joby
AMBER  = "#e8a93e"
INK    = "#1a1a1a"
INK_SOFT = "#555555"
LINE   = "#cccccc"
CREAM  = "#fbefd7"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": INK_SOFT,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "axes.grid": True,
    "grid.color": LINE,
    "grid.linewidth": 0.4,
    "grid.alpha": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
os.makedirs(DOCS, exist_ok=True)


# --- Helpers --------------------------------------------------------------

UNTUNED_FOM = 0.65
UNTUNED_ETA = 0.78


def short_name(name: str) -> str:
    if "Mavic 3" in name:    return "Mavic 3"
    if "X10" in name:        return "Skydio X10"
    if "Alta X" in name:     return "Alta X"
    if "Joby" in name:       return "Joby S4"
    if "Archer" in name:     return "Archer Midnight"
    if "Beta" in name:       return "Beta ALIA-250"
    if "VX4" in name:        return "Vertical VX4"
    return name


def predict_hover_untuned(ac):
    o = replace(ac, figure_of_merit=UNTUNED_FOM,
                drivetrain_efficiency=UNTUNED_ETA, profile_power_W=0.0)
    return hover_endurance_min(o)


def pct_err(predicted, published):
    return (predicted - published) / published * 100


# --- Chart 1: validation chart (LinkedIn hero) ----------------------------

def make_validation_chart() -> str:
    names    = [short_name(ac.name) for ac in ALL_AIRCRAFT]
    pub      = [PUBLISHED_HOVER_MIN[ac.name] for ac in ALL_AIRCRAFT]
    untuned  = [predict_hover_untuned(ac) for ac in ALL_AIRCRAFT]
    tuned    = [hover_endurance_min(ac)   for ac in ALL_AIRCRAFT]
    err_unt  = [pct_err(u, p) for u, p in zip(untuned, pub)]
    err_tun  = [pct_err(t, p) for t, p in zip(tuned,   pub)]

    fig, ax = plt.subplots(figsize=(15, 7.2))
    fig.subplots_adjust(top=0.80, bottom=0.22, left=0.06, right=0.98)

    x = np.arange(len(names))
    w = 0.26
    bars_pub = ax.bar(x - w, pub,     w, color=NAVY,  label="Published / Derived")
    bars_unt = ax.bar(x,     untuned, w, color=RUST,  label="Untuned model")
    bars_tun = ax.bar(x + w, tuned,   w, color=GREEN, label="Tuned model")

    for bars, vals in zip([bars_pub, bars_unt, bars_tun],
                          [pub, untuned, tuned]):
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.8,
                    f"{v:.1f}", ha="center", va="bottom",
                    fontsize=8.5, color=INK, fontweight="bold")

    for xi, eu, et in zip(x, err_unt, err_tun):
        ax.text(xi, -5.5,
                f"untuned  {eu:+.1f}%\ntuned     {et:+.2f}%",
                ha="center", va="top",
                fontsize=8, color=INK_SOFT, family="monospace")

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=10.5, fontweight="bold")
    ax.set_ylabel("Hover endurance  (minutes)")
    ax.set_ylim(-13, max(max(untuned), max(tuned), max(pub)) * 1.18)
    ax.axhline(0, color=LINE, linewidth=0.8)
    ax.legend(loc="lower center", ncol=3,
              bbox_to_anchor=(0.5, -0.20), frameon=False)

    fig.text(0.06, 0.945,
             "Multirotor & eVTOL Battery Endurance Calculator   ·   Hover Validation (v4)",
             ha="left", fontsize=14, color=INK_SOFT)
    fig.text(0.06, 0.895,
             f"Per-aircraft tuning matches specs to "
             f"{max(abs(e) for e in err_tun):.2f} %  across a 3300× mass range "
             f"(0.9 kg → 2,948 kg) and four eVTOL architectures",
             ha="left", fontsize=11.5, color=INK, weight="bold")

    fig.text(0.06, 0.025,
             "Model: rotor momentum theory · Glauert forward flight · "
             "induced + profile-drag · wing-borne cruise across 4 eVTOL architectures (v4)",
             color=INK_SOFT, fontsize=9, style="italic")
    fig.text(0.98, 0.025,
             "D. Angelou  ·  UMich ME '27",
             ha="right", color=INK_SOFT, fontsize=9)

    out = os.path.join(DOCS, "validation_chart.png")
    fig.savefig(out)
    plt.close(fig)
    return out


# --- Chart 2: power-required curves (4 aircraft, 2x2 grid) ---------------

def make_power_curves_chart() -> str:
    speeds = np.linspace(0.1, 22.0, 60)
    speeds_joby = np.linspace(0.1, 100.0, 80)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Power-required vs airspeed   ·   rotor-borne (multirotors) + wing-borne (Joby)",
                 y=0.98, fontsize=14, fontweight="bold", color=INK)
    fig.subplots_adjust(top=0.91, bottom=0.08, left=0.08, right=0.96,
                        hspace=0.36, wspace=0.24)

    colors = [NAVY, RUST, GREEN, PURPLE]
    for ax, ac, color in zip(axes.flat, ALL_AIRCRAFT, colors):
        is_joby = "Joby" in ac.name
        vs = speeds_joby if is_joby else speeds

        P = power_curve(ac, vs.tolist())
        v_max_search = 100.0 if ac.has_wing else 22.0
        V_best, range_best, _ = best_cruise_speed(
            ac, v_min=1.0, v_max=v_max_search, n_pts=201
        )
        P_hover = hover_power_momentum_theory(
            ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            profile_power_W=ac.profile_power_W,
        )

        # Scale power axis: W for small, kW for Joby
        if is_joby:
            P_plot = [p / 1000.0 for p in P]
            P_hover_plot = P_hover / 1000.0
            P_at_Vbest = np.interp(V_best, vs, P) / 1000.0
            ylabel = "Electrical power required  (kW)"
        else:
            P_plot = P
            P_hover_plot = P_hover
            P_at_Vbest = np.interp(V_best, vs, P)
            ylabel = "Electrical power required  (W)"

        ax.plot(vs, P_plot, color=color, linewidth=2.2)
        ax.axhline(P_hover_plot, color=INK_SOFT, linewidth=0.7, linestyle=":")
        ax.axvline(V_best, color=AMBER, linewidth=1.2, linestyle="--")
        ax.scatter([V_best], [P_at_Vbest], color=AMBER, s=55, zorder=5,
                   edgecolor="white", linewidth=1.5)

        ax.set_title(short_name(ac.name), fontsize=12, fontweight="bold")
        ax.set_xlabel("Airspeed  (m/s)")
        ax.set_ylabel(ylabel)
        ax.set_xlim(0, vs[-1])

        t_hover = hover_endurance_min(ac)
        hover_unit = "kW" if is_joby else "W"
        ax.text(0.04, 0.96,
                f"hover P = {P_hover_plot:.0f} {hover_unit}  ({t_hover:.1f} min)",
                transform=ax.transAxes, fontsize=8.5, color=INK_SOFT,
                ha="left", va="top")
        ax.text(0.04, 0.88,
                f"best range:  V = {V_best:.1f} m/s,  R = {range_best:.1f} km",
                transform=ax.transAxes, fontsize=8.5, color=INK,
                ha="left", va="top")

        # Mark stall speed + cruise reference on Joby panel
        if is_joby:
            from endurance import stall_speed
            V_stall = stall_speed(ac.mass_kg, ac.wing_area_m2, ac.CL_max)
            ax.axvspan(0, V_stall, alpha=0.06, color=RUST)
            ax.text(V_stall / 2, ax.get_ylim()[1] * 0.5,
                    "rotor-\nborne", fontsize=9, color=RUST,
                    ha="center", va="center", style="italic")
            ax.text((V_stall + vs[-1]) / 2, ax.get_ylim()[1] * 0.55,
                    "wing-borne\ncruise", fontsize=9, color=GREEN,
                    ha="center", va="center", style="italic")
            # Mark published cruise reference
            ax.scatter([74.0], [161000 / (74.0) / 0 if False else
                                np.interp(74.0, vs, P) / 1000.0],
                       marker="*", s=200, color=GREEN, zorder=6,
                       edgecolor="white", linewidth=1.2)
            ax.text(74.0, np.interp(74.0, vs, P) / 1000.0 + 30,
                    "Joby cruise\n(74 m/s, 161 km)",
                    fontsize=8, color=GREEN, ha="center", va="bottom",
                    fontweight="bold")

    out = os.path.join(DOCS, "power_curves.png")
    fig.savefig(out)
    plt.close(fig)
    return out


# --- Chart 3: composite "calculator overview" (README hero) --------------

def make_overview_chart() -> str:
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(13.5, 9.5))
    gs = GridSpec(3, 3, figure=fig,
                  height_ratios=[0.6, 2.6, 2.8],
                  hspace=0.78, wspace=0.32,
                  top=0.92, bottom=0.085, left=0.06, right=0.96)

    # Title
    ax_t = fig.add_subplot(gs[0, :])
    ax_t.axis("off")
    ax_t.text(0.0, 0.85,
              "Multirotor & eVTOL Battery Endurance Calculator",
              ha="left", va="top", fontsize=22, fontweight="bold", color=INK)
    ax_t.text(0.0, 0.05,
              "rotor momentum theory  ·  Glauert forward flight  ·  "
              "induced + profile-drag  ·  wing-borne cruise (v3)  ·  "
              "validated on Mavic 3 / X10 / Alta X / Joby S4",
              ha="left", va="bottom", fontsize=11, color=INK_SOFT, style="italic")
    ax_t.text(1.0, 0.55,
              "D. Angelou  ·  UMich ME '27",
              ha="right", va="center", fontsize=10, color=INK_SOFT)

    # KPI card (Mavic 3 demo) -- left of second row
    ac_demo = DJI_MAVIC_3
    ax_kpi = fig.add_subplot(gs[1, 0])
    ax_kpi.axis("off")
    P_hover = hover_power_momentum_theory(
        ac_demo.mass_kg, ac_demo.n_rotors, ac_demo.rotor_diameter_m,
        ac_demo.figure_of_merit, ac_demo.drivetrain_efficiency,
        profile_power_W=ac_demo.profile_power_W,
    )
    t_hover = hover_endurance_min(ac_demo)
    V_best, range_best, _ = best_cruise_speed(ac_demo, v_min=1.0, v_max=22.0)

    box = plt.Rectangle((0.02, 0.02), 0.96, 0.96,
                        transform=ax_kpi.transAxes,
                        facecolor=CREAM, edgecolor=AMBER, linewidth=1.5)
    ax_kpi.add_patch(box)
    ax_kpi.text(0.07, 0.90, "DEMO: DJI Mavic 3 Classic",
                transform=ax_kpi.transAxes, fontsize=12, fontweight="bold", color=INK)
    ax_kpi.text(0.07, 0.81,
                f"mass {ac_demo.mass_kg} kg   ·   {ac_demo.nameplate_Wh:.0f} Wh   "
                f"·   9.4 in × 4 rotors",
                transform=ax_kpi.transAxes, fontsize=9.5, color=INK_SOFT)

    kpi_lines = [
        ("HOVER POWER",       f"{P_hover:.0f} W"),
        ("HOVER ENDURANCE",   f"{t_hover:.1f} min"),
        ("BEST CRUISE SPEED", f"{V_best:.1f} m/s"),
        ("RANGE AT V_BEST",   f"{range_best:.2f} km"),
    ]
    for i, (label, val) in enumerate(kpi_lines):
        y = 0.66 - i * 0.13
        ax_kpi.text(0.07, y, label,
                    transform=ax_kpi.transAxes, fontsize=8.5,
                    fontweight="bold", color=INK_SOFT, family="monospace")
        ax_kpi.text(0.93, y, val,
                    transform=ax_kpi.transAxes, fontsize=15,
                    fontweight="bold", color=NAVY, ha="right")

    # Power curve (right of KPI)
    ax_p = fig.add_subplot(gs[1, 1:])
    speeds = np.linspace(0.1, 22.0, 60)
    P = power_curve(ac_demo, speeds.tolist())
    ax_p.plot(speeds, P, color=NAVY, linewidth=2.4, label="Power required")
    ax_p.axhline(P_hover, color=INK_SOFT, linewidth=0.7, linestyle=":")
    ax_p.axvline(V_best, color=AMBER, linewidth=1.2, linestyle="--")
    ax_p.scatter([V_best], [np.interp(V_best, speeds, P)], color=AMBER,
                 s=70, zorder=5, edgecolor="white", linewidth=1.5,
                 label=f"Best range  V = {V_best:.1f} m/s")
    ax_p.text(0.4, P_hover * 1.02, f"hover power = {P_hover:.0f} W",
              fontsize=9, color=INK_SOFT, va="bottom")
    ax_p.set_xlabel("Airspeed  (m/s)")
    ax_p.set_ylabel("Electrical power  (W)")
    ax_p.set_title("Power-required curve  (the classic multirotor U)",
                   loc="left", color=INK)
    ax_p.set_xlim(0, 22)
    ax_p.legend(loc="upper right")

    # Validation bars (full width, bottom)
    ax_v = fig.add_subplot(gs[2, :])
    names    = [short_name(ac.name) for ac in ALL_AIRCRAFT]
    pub      = [PUBLISHED_HOVER_MIN[ac.name] for ac in ALL_AIRCRAFT]
    untuned  = [predict_hover_untuned(ac) for ac in ALL_AIRCRAFT]
    tuned    = [hover_endurance_min(ac)   for ac in ALL_AIRCRAFT]
    err_unt  = [pct_err(u, p) for u, p in zip(untuned, pub)]
    err_tun  = [pct_err(t, p) for t, p in zip(tuned,   pub)]

    x = np.arange(len(names))
    w = 0.26
    bars_pub  = ax_v.bar(x - w, pub,     w, color=NAVY,  label="Published")
    bars_unt  = ax_v.bar(x,     untuned, w, color=RUST,  label="Untuned model")
    bars_tun  = ax_v.bar(x + w, tuned,   w, color=GREEN, label="Tuned model")

    for bars, vals in zip([bars_pub, bars_unt, bars_tun],
                          [pub, untuned, tuned]):
        for b, v in zip(bars, vals):
            ax_v.text(b.get_x() + b.get_width()/2, b.get_height() + 1.0,
                      f"{v:.1f}", ha="center", va="bottom",
                      fontsize=8.5, color=INK, fontweight="bold")

    for xi, eu, et in zip(x, err_unt, err_tun):
        ax_v.text(xi, -5,
                  f"untuned  {eu:+.1f}%\ntuned     {et:+.2f}%",
                  ha="center", va="top",
                  fontsize=8, color=INK_SOFT, family="monospace")

    ax_v.set_xticks(x)
    ax_v.set_xticklabels(names, fontsize=10.5, fontweight="bold")
    ax_v.set_ylabel("Hover endurance  (min)")
    ax_v.set_ylim(-13, max(max(untuned), max(tuned), max(pub)) * 1.18)
    ax_v.axhline(0, color=LINE, linewidth=0.8)
    ax_v.set_title(
        f"Hover validation:  max |error| {max(abs(e) for e in err_unt):.0f}% (untuned) "
        f"→ {max(abs(e) for e in err_tun):.2f}% (tuned)   ·   2400× mass range",
        loc="left", color=INK,
    )
    ax_v.legend(loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.30),
                frameon=False)

    out = os.path.join(DOCS, "calculator_overview.png")
    fig.savefig(out)
    plt.close(fig)
    return out


# --- Chart 4: forward-flight v1 vs v2 comparison (NEW) -------------------

def make_forward_flight_v1_v2() -> str:
    """The killer v2 narrative chart: compare v1 (no profile drag) to v2
    (with profile drag) on the Mavic 3 power curve and predicted range."""
    ac = DJI_MAVIC_3
    speeds = np.linspace(0.1, 22.0, 80)

    # v2: as-tuned (FoM_ind=0.87, eta=0.72, profile=26.8 W)
    P_v2 = power_curve(ac, speeds.tolist())

    # v1 emulation: lumped FoM = 0.55 (so FoM*eta = 0.396), no profile drag
    ac_v1 = replace(ac, figure_of_merit=0.55,
                    drivetrain_efficiency=0.72, profile_power_W=0.0)
    P_v1 = power_curve(ac_v1, speeds.tolist())

    # Predicted range curves: range = V * (E_usable / P) * 3.6
    from endurance import battery_usable_Wh
    E = battery_usable_Wh(ac.battery_capacity_Ah, ac.battery_voltage_V,
                         ac.usable_fraction, ac.discharge_efficiency)
    R_v1 = [v * (E / p) * 3.6 for v, p in zip(speeds, P_v1)]
    R_v2 = [v * (E / p) * 3.6 for v, p in zip(speeds, P_v2)]

    fig, (ax_P, ax_R) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.subplots_adjust(top=0.80, bottom=0.13, left=0.07, right=0.97, wspace=0.28)

    # Left: power curves
    ax_P.plot(speeds, P_v1, color=RUST, linewidth=2.2,
              linestyle="--", label="v1  (lumped FoM, no profile drag)")
    ax_P.plot(speeds, P_v2, color=NAVY, linewidth=2.4,
              label="v2  (induced FoM + profile drag, tuned per-aircraft)")
    # mark hover power for each
    ax_P.scatter([0], [P_v1[0]], color=RUST, s=50, zorder=5)
    ax_P.scatter([0], [P_v2[0]], color=NAVY, s=50, zorder=5)
    # mark DJI's published cruise points (compute back-implied power)
    # 30 km @ 14 m/s -> E_usable * V / R, then back out P
    P_pub_14 = E * 14 / 30 * 3.6   # E[Wh] * V[m/s] / R[km] * 3.6 -> W
    P_pub_9  = E / (46 / 60.0)
    ax_P.scatter([14.0, 9.0], [P_pub_14, P_pub_9],
                 marker="*", s=200, color=GREEN, zorder=6,
                 edgecolor="white", linewidth=1.2,
                 label="DJI published reference")
    ax_P.set_xlabel("Airspeed  (m/s)")
    ax_P.set_ylabel("Electrical power  (W)")
    ax_P.set_title("DJI Mavic 3 power curve:  v1 vs v2", loc="left", color=INK)
    ax_P.legend(loc="upper left", fontsize=9)
    ax_P.set_xlim(0, 22)

    # Right: predicted range curves
    ax_R.plot(speeds, R_v1, color=RUST, linewidth=2.2,
              linestyle="--", label="v1 predicted range")
    ax_R.plot(speeds, R_v2, color=NAVY, linewidth=2.4,
              label="v2 predicted range")
    # DJI's 30 km @ 14 m/s reference
    ax_R.scatter([14.0], [30.0], marker="*", s=220, color=GREEN, zorder=6,
                 edgecolor="white", linewidth=1.2,
                 label="DJI published (30 km @ 14 m/s)")
    ax_R.axhline(30.0, color=GREEN, linewidth=0.5, alpha=0.4)

    # v1 vs v2 endurance @ 14
    R_v1_14 = float(np.interp(14.0, speeds, R_v1))
    R_v2_14 = float(np.interp(14.0, speeds, R_v2))
    err_v1 = (R_v1_14 - 30.0) / 30.0 * 100
    err_v2 = (R_v2_14 - 30.0) / 30.0 * 100

    ax_R.set_xlabel("Airspeed  (m/s)")
    ax_R.set_ylabel("Predicted range  (km)")
    ax_R.set_title("Range vs airspeed:  v1 vs v2", loc="left", color=INK)
    ax_R.legend(loc="lower right", fontsize=9)
    ax_R.set_xlim(0, 22)
    ax_R.set_ylim(0, max(max(R_v1), max(R_v2)) * 1.15)

    # annotation block in right plot
    ax_R.text(0.04, 0.96,
              f"At V = 14 m/s:\n"
              f"  v1:  {R_v1_14:.1f} km   ({err_v1:+.1f} %)\n"
              f"  v2:  {R_v2_14:.1f} km   ({err_v2:+.1f} %)",
              transform=ax_R.transAxes, fontsize=9.5, family="monospace",
              color=INK, ha="left", va="top",
              bbox=dict(boxstyle="round,pad=0.4", facecolor=CREAM, edgecolor=AMBER))

    # Title block
    fig.text(0.07, 0.945,
             "Why v2 matters:  adding a profile-drag term collapses forward-flight error",
             ha="left", fontsize=14, color=INK_SOFT)
    fig.text(0.07, 0.895,
             "Same hover match either way — but only v2 lands the published "
             "cruise range",
             ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.07, 0.02,
             "v1: lumped FoM absorbs profile drag, scales it down with V — wrong physics.   "
             "v2: profile drag stays roughly constant with V, induced power drops.",
             color=INK_SOFT, fontsize=9, style="italic")
    fig.text(0.97, 0.02,
             "D. Angelou  ·  UMich ME '27",
             ha="right", color=INK_SOFT, fontsize=9)

    out = os.path.join(DOCS, "forward_flight_v1_v2.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def make_joby_v2_v3() -> str:
    """The v3 narrative chart: Joby S4 with rotor-only (v2) vs rotor+wing (v3).

    Shows the dramatic difference adding wing-borne cruise makes: the U
    curve gets a wing-borne plateau, range jumps from <80 km to >200 km.
    """
    from dataclasses import replace
    from endurance import stall_speed, battery_usable_Wh

    ac_v3 = next(a for a in ALL_AIRCRAFT if "Joby" in a.name)
    ac_v2 = replace(ac_v3, wing_area_m2=0.0, wing_span_m=0.0)   # disable wing

    speeds = np.linspace(0.1, 100.0, 120)
    P_v2 = np.array(power_curve(ac_v2, speeds.tolist()))
    P_v3 = np.array(power_curve(ac_v3, speeds.tolist()))

    V_stall = stall_speed(ac_v3.mass_kg, ac_v3.wing_area_m2, ac_v3.CL_max)

    # Range curves
    E = battery_usable_Wh(ac_v3.battery_capacity_Ah, ac_v3.battery_voltage_V,
                         ac_v3.usable_fraction, ac_v3.discharge_efficiency)
    R_v2 = speeds * (E / P_v2) * 3.6
    R_v3 = speeds * (E / P_v3) * 3.6

    fig, (ax_P, ax_R) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.subplots_adjust(top=0.80, bottom=0.13, left=0.07, right=0.97, wspace=0.28)

    # Left: power curves
    ax_P.axvspan(0, V_stall, alpha=0.07, color=RUST,
                 label=f"V < V_stall ({V_stall:.0f} m/s)")
    ax_P.plot(speeds, P_v2 / 1000, color=RUST, linewidth=2.2,
              linestyle="--", label="v2  (rotor-borne only)")
    ax_P.plot(speeds, P_v3 / 1000, color=NAVY, linewidth=2.4,
              label="v3  (rotor-borne + wing-borne, min of two)")
    ax_P.scatter([74.0], [np.interp(74.0, speeds, P_v3) / 1000],
                 marker="*", s=200, color=GREEN, zorder=6,
                 edgecolor="white", linewidth=1.2,
                 label="Joby published cruise (74 m/s)")
    ax_P.set_xlabel("Airspeed  (m/s)")
    ax_P.set_ylabel("Electrical power  (kW)")
    ax_P.set_title("Joby S4 power curve:  v2 vs v3", loc="left", color=INK)
    ax_P.legend(loc="upper right", fontsize=9)
    ax_P.set_xlim(0, 100)
    ax_P.set_ylim(0, max(max(P_v2), max(P_v3)) / 1000 * 1.1)

    # Right: range curves
    ax_R.axvspan(0, V_stall, alpha=0.07, color=RUST)
    ax_R.plot(speeds, R_v2, color=RUST, linewidth=2.2,
              linestyle="--", label="v2 predicted range")
    ax_R.plot(speeds, R_v3, color=NAVY, linewidth=2.4,
              label="v3 predicted range")
    ax_R.scatter([74.0], [161.0], marker="*", s=220, color=GREEN, zorder=6,
                 edgecolor="white", linewidth=1.2,
                 label="Joby published (161 km @ 74 m/s)")
    ax_R.axhline(161.0, color=GREEN, linewidth=0.5, alpha=0.4)

    R_v2_74 = float(np.interp(74.0, speeds, R_v2))
    R_v3_74 = float(np.interp(74.0, speeds, R_v3))
    err_v2 = (R_v2_74 - 161.0) / 161.0 * 100
    err_v3 = (R_v3_74 - 161.0) / 161.0 * 100

    ax_R.set_xlabel("Airspeed  (m/s)")
    ax_R.set_ylabel("Predicted range  (km)")
    ax_R.set_title("Range vs airspeed:  v2 vs v3", loc="left", color=INK)
    ax_R.legend(loc="upper right", fontsize=9)
    ax_R.set_xlim(0, 100)
    ax_R.set_ylim(0, max(max(R_v2), max(R_v3)) * 1.1)

    ax_R.text(0.04, 0.96,
              f"At V = 74 m/s:\n"
              f"  v2:  {R_v2_74:.1f} km   ({err_v2:+.1f} %)\n"
              f"  v3:  {R_v3_74:.1f} km   ({err_v3:+.2f} %)",
              transform=ax_R.transAxes, fontsize=9.5, family="monospace",
              color=INK, ha="left", va="top",
              bbox=dict(boxstyle="round,pad=0.4", facecolor=CREAM, edgecolor=AMBER))

    # Title block
    fig.text(0.07, 0.945,
             "Why v3 matters:  the wing-borne cruise model lands the Joby S4 cruise spec",
             ha="left", fontsize=14, color=INK_SOFT)
    fig.text(0.07, 0.895,
             "Same hover, same low-speed flight — but above V_stall a wing is "
             "an order of magnitude more efficient than rotors",
             ha="left", fontsize=11, color=INK, weight="bold")
    fig.text(0.07, 0.02,
             "v2: rotors do all the lifting at every airspeed.   "
             "v3: wing lifts the aircraft above V_stall, rotors become "
             "conventional thrust propellers.",
             color=INK_SOFT, fontsize=9, style="italic")
    fig.text(0.97, 0.02,
             "D. Angelou  ·  UMich ME '27",
             ha="right", color=INK_SOFT, fontsize=9)

    out = os.path.join(DOCS, "joby_v2_v3.png")
    fig.savefig(out)
    plt.close(fig)
    return out


# --- Chart 6 (v4): eVTOL architecture comparison --------------------------

def make_evtol_comparison() -> str:
    """Power curves for the four eVTOLs overlaid, showing how different
    architectures compare. Also annotates V_best and max published range."""
    from aircraft_db import JOBY_S4, ARCHER_MIDNIGHT, BETA_ALIA_250, VERTICAL_VX4

    aircraft = [
        ("Joby S4",          JOBY_S4,          NAVY,   74.0, 161.0, "tilt-rotor (6 tilt)"),
        ("Archer Midnight",  ARCHER_MIDNIGHT,  RUST,   67.0, 161.0, "lift+cruise (12-tilt-6)"),
        ("Beta ALIA-250",    BETA_ALIA_250,    GREEN,  62.0, 463.0, "lift+pusher (4+1)"),
        ("Vertical VX4",     VERTICAL_VX4,     PURPLE, 67.0, 161.0, "tilt+lift (4+4)"),
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.2))
    fig.subplots_adjust(top=0.81, bottom=0.13, left=0.07, right=0.97, wspace=0.25)

    # Left panel: power vs speed
    V = np.linspace(1.0, 110.0, 300)
    for label, ac, color, V_pub, _, arch in aircraft:
        P_kW = np.array([p / 1000.0 for p in power_curve(ac, V.tolist())])
        ax1.plot(V, P_kW, color=color, linewidth=2.2, label=f"{label}  ({arch})")

    ax1.set_xlabel("Cruise speed  (m/s)")
    ax1.set_ylabel("Electrical power required  (kW)")
    ax1.set_xlim(0, 110)
    ax1.set_ylim(0, 1600)
    ax1.legend(loc="upper right", fontsize=9, frameon=False)
    ax1.set_title("Power required vs cruise speed", fontsize=11, pad=6,
                  color=INK, fontweight="bold", loc="left")

    # Right panel: predicted range at V_best vs MTOW
    masses = []
    ranges_best = []
    ranges_pub = []
    colors = []
    labels = []
    for label, ac, color, V_pub, r_pub, _ in aircraft:
        _, r_best, _ = best_cruise_speed(ac, v_min=1.0, v_max=110.0, n_pts=221)
        masses.append(ac.mass_kg)
        ranges_best.append(r_best)
        ranges_pub.append(r_pub)
        colors.append(color)
        labels.append(label)

    x = np.arange(len(labels))
    w = 0.38
    bars1 = ax2.bar(x - w/2, ranges_pub, w, color=[c for c in colors],
                    alpha=0.55, label="Published max range")
    bars2 = ax2.bar(x + w/2, ranges_best, w, color=colors,
                    label="Model: range at V_best")
    for b, v in zip(bars1, ranges_pub):
        ax2.text(b.get_x() + b.get_width()/2, v + 8, f"{v:.0f}",
                 ha="center", va="bottom", fontsize=9, color=INK)
    for b, v in zip(bars2, ranges_best):
        ax2.text(b.get_x() + b.get_width()/2, v + 8, f"{v:.0f}",
                 ha="center", va="bottom", fontsize=9, color=INK, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax2.set_ylabel("Range  (km)")
    ax2.set_ylim(0, 620)
    ax2.legend(loc="upper left", fontsize=9, frameon=False)
    ax2.set_title("Predicted vs published range", fontsize=11, pad=6,
                  color=INK, fontweight="bold", loc="left")

    fig.text(0.07, 0.94,
             "eVTOL Architecture Comparison  ·  4 designs across 1 model",
             fontsize=14, color=INK_SOFT)
    fig.text(0.07, 0.895,
             "One Python model, four eVTOL architectures: each Cd₀ back-solved to "
             "match its manufacturer's published range",
             fontsize=11, color=INK, fontweight="bold")

    fig.text(0.07, 0.025,
             "Wing-borne cruise model (v3 physics) applied to four architectures (v4)",
             color=INK_SOFT, fontsize=9, style="italic")
    fig.text(0.97, 0.025,
             "D. Angelou  ·  UMich ME '27",
             ha="right", color=INK_SOFT, fontsize=9)

    out = os.path.join(DOCS, "evtol_comparison.png")
    fig.savefig(out)
    plt.close(fig)
    return out


# --- Driver ---------------------------------------------------------------

if __name__ == "__main__":
    paths = [
        make_validation_chart(),
        make_power_curves_chart(),
        make_overview_chart(),
        make_forward_flight_v1_v2(),
        make_joby_v2_v3(),
        make_evtol_comparison(),
    ]
    print("Generated:")
    for p in paths:
        print(f"  {p}")
