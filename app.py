"""
app.py
======
Streamlit UI for the multirotor battery endurance calculator.

Run locally:
    streamlit run app.py

Three tabs:
    1. Calculator    -- pick or define an aircraft, see hover/cruise outputs.
    2. Power curve   -- power-required and range vs airspeed.
    3. Validation    -- compare predictions to published Mavic 3 / X10 / Alta X.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

from endurance import (
    Aircraft,
    G,
    air_density,
    battery_usable_Wh,
    hover_power_momentum_theory,
    hover_endurance_min,
    forward_flight_power,
    forward_endurance_and_range,
    power_curve,
    best_cruise_speed,
)
from aircraft_db import ALL_AIRCRAFT, PUBLISHED_HOVER_MIN
from validate import run_validation


# ----------------------------------------------------------------------
# Page config
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Multirotor Endurance Calculator",
    page_icon="🚁",
    layout="wide",
)


# ----------------------------------------------------------------------
# Sidebar -- aircraft selector + environment
# ----------------------------------------------------------------------
st.sidebar.markdown("## Aircraft")
preset_names = ["-- Custom --"] + [ac.name for ac in ALL_AIRCRAFT]
choice = st.sidebar.selectbox("Preset", preset_names, index=1)

if choice == "-- Custom --":
    base = Aircraft(
        name="Custom multirotor",
        mass_kg=1.5,
        n_rotors=4,
        rotor_diameter_m=0.254,
        battery_capacity_Ah=5.0,
        battery_voltage_V=14.8,
    )
else:
    base = next(a for a in ALL_AIRCRAFT if a.name == choice)

with st.sidebar.expander("Airframe", expanded=True):
    mass_kg = st.number_input("Mass [kg]", 0.05, 1500.0, float(base.mass_kg),
                              step=0.05, format="%.3f")
    n_rotors = st.number_input("Number of rotors", 2, 12, int(base.n_rotors), 1)
    rotor_diameter_in = st.number_input(
        "Rotor diameter [in]", 2.0, 80.0,
        float(base.rotor_diameter_m * 39.3701), step=0.1, format="%.2f",
    )
    rotor_diameter_m = rotor_diameter_in / 39.3701

with st.sidebar.expander("Battery", expanded=True):
    cap_Ah = st.number_input("Capacity [Ah]", 0.10, 500.0,
                             float(base.battery_capacity_Ah),
                             step=0.1, format="%.3f")
    cells_S = st.number_input("Cells in series (S-count)", 1, 24,
                              int(round(base.battery_voltage_V / 3.7)), 1)
    chemistry = st.selectbox(
        "Chemistry (sets nominal V/cell)",
        ["LiPo (3.85 V)", "Li-ion 21700 (3.7 V)", "LiHV (3.85 V)", "Custom V"],
        index=0,
    )
    if chemistry.startswith("LiPo"):
        v_per_cell = 3.85
    elif chemistry.startswith("Li-ion"):
        v_per_cell = 3.70
    elif chemistry.startswith("LiHV"):
        v_per_cell = 3.85
    else:
        v_per_cell = st.number_input("V per cell", 2.5, 4.5, 3.7, 0.05)
    voltage_V = cells_S * v_per_cell
    st.caption(f"Pack nominal voltage: **{voltage_V:.2f} V** "
               f"({cap_Ah * voltage_V:.1f} Wh nameplate)")

with st.sidebar.expander("Efficiency assumptions"):
    fom = st.slider("FoM (induced, ~1/kappa)", 0.40, 0.95,
                    float(base.figure_of_merit), 0.01,
                    help="Induced-power efficiency. Textbook 0.87 (kappa=1.15); "
                         "premium designs reach 0.90.")
    eta_drive = st.slider("Drivetrain efficiency (motor+ESC)", 0.55, 0.95,
                          float(base.drivetrain_efficiency), 0.01)
    profile_power = st.number_input(
        "Profile power at hover [W]",
        min_value=0.0, max_value=500_000.0,
        value=float(base.profile_power_W), step=1.0,
        help="Rotor profile drag, expressed as a hover-equivalent power. "
             "Held constant vs airspeed in this model. Typical: 25-37 % of shaft "
             "hover power. Set to 0 for v1-style lumped-FoM model.",
    )
    usable = st.slider("Usable battery fraction", 0.60, 1.00,
                       float(base.usable_fraction), 0.01)
    batt_eff = st.slider("Battery discharge efficiency", 0.85, 1.00,
                         float(base.discharge_efficiency), 0.01)

with st.sidebar.expander("Forward flight drag"):
    Cd = st.slider("Body drag coefficient", 0.3, 2.0,
                   float(base.Cd_body), 0.05)
    A_front = st.number_input("Frontal area [m^2]", 0.005, 1.0,
                              float(base.frontal_area_m2),
                              step=0.005, format="%.3f")

with st.sidebar.expander("Wing-borne cruise (v3, eVTOL)"):
    st.caption(
        "Set wing area > 0 to enable wing-borne cruise mode. The model uses "
        "min(rotor power, wing power) at each airspeed, with a stall guard. "
        "Leave wing area = 0 for pure multirotor."
    )
    wing_area_m2 = st.number_input(
        "Wing area [m²]", 0.0, 200.0, float(base.wing_area_m2),
        step=0.5, format="%.2f",
    )
    wing_span_m = st.number_input(
        "Wingspan [m]", 0.0, 100.0, float(base.wing_span_m),
        step=0.5, format="%.2f",
    )
    Cd0 = st.slider("Parasite drag coefficient Cd₀", 0.010, 0.080,
                    float(base.Cd0), 0.001)
    oswald_e = st.slider("Oswald efficiency e", 0.60, 0.95,
                         float(base.oswald_e), 0.01)
    CL_max = st.slider("Max lift coefficient CL_max", 1.0, 2.5,
                       float(base.CL_max), 0.05)
    prop_efficiency = st.slider("Cruise propeller efficiency η_prop",
                                0.65, 0.95, float(base.prop_efficiency), 0.01)

with st.sidebar.expander("Atmosphere"):
    altitude_m = st.slider("Altitude [m]", 0, 5000, 0, 50)
    temp_offset = st.slider("Temperature offset from ISA [C]",
                            -30, 50, 0, 1)

with st.sidebar.expander("v5 physics (advanced)"):
    st.caption(
        "Runtime parameters for v5 physics extensions. These affect "
        "predictions without changing the aircraft definition."
    )
    altitude_AGL_m = st.slider(
        "Altitude AGL [m] (ground effect)", 0.0, 50.0, 10.0, 0.5,
        help="Height above ground for Cheeseman-Bennett ground effect. "
             "Only affects hover when AGL < 2 × rotor radius.",
    )
    wind_headwind_mps = st.slider(
        "Wind headwind [m/s]", -15.0, 15.0, 0.0, 0.5,
        help="Positive = headwind (reduces ground range). "
             "Negative = tailwind (increases ground range).",
    )

# Build runtime aircraft from sidebar values
ac = Aircraft(
    name=base.name if choice != "-- Custom --" else "Custom multirotor",
    mass_kg=mass_kg,
    n_rotors=int(n_rotors),
    rotor_diameter_m=rotor_diameter_m,
    battery_capacity_Ah=cap_Ah,
    battery_voltage_V=voltage_V,
    Cd_body=Cd,
    frontal_area_m2=A_front,
    figure_of_merit=fom,
    drivetrain_efficiency=eta_drive,
    profile_power_W=profile_power,
    usable_fraction=usable,
    discharge_efficiency=batt_eff,
    wing_area_m2=wing_area_m2,
    wing_span_m=wing_span_m,
    Cd0=Cd0,
    oswald_e=oswald_e,
    CL_max=CL_max,
    prop_efficiency=prop_efficiency,
    notes=base.notes,
    # v5 fields from preset (not editable via sidebar)
    transition_width_mps=base.transition_width_mps,
    profile_K_mu=base.profile_K_mu,
    rotor_tip_speed_mps=base.rotor_tip_speed_mps,
    voltage_sag_at_full_load=base.voltage_sag_at_full_load,
    cooling_power_W=base.cooling_power_W,
)


# ----------------------------------------------------------------------
# Top header
# ----------------------------------------------------------------------
st.markdown("# 🚁 Multirotor & eVTOL Battery Endurance Calculator")
st.markdown(
    "Parametric hover- and cruise-endurance model from rotor momentum theory "
    "+ wing-borne cruise. Validated against published specs for the "
    "DJI Mavic 3, Skydio X10, Freefly Alta X, and Joby S4 eVTOL "
    "(see **Validation** tab)."
)

tab_calc, tab_curves, tab_valid, tab_about = st.tabs(
    ["📊 Calculator", "📈 Power curve", "✓ Validation", "📚 About"]
)


# ----------------------------------------------------------------------
# TAB 1 -- Calculator
# ----------------------------------------------------------------------
with tab_calc:
    rho = air_density(altitude_m, temp_offset)
    P_hover = hover_power_momentum_theory(
        ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
        ac.figure_of_merit, ac.drivetrain_efficiency,
        profile_power_W=ac.profile_power_W,
        altitude_m=altitude_m, temperature_offset_c=temp_offset,
        altitude_AGL_m=altitude_AGL_m,
        cooling_power_W=ac.cooling_power_W,
    )
    t_hover = hover_endurance_min(ac, altitude_m, temp_offset,
                                  altitude_AGL_m=altitude_AGL_m)
    E_usable = battery_usable_Wh(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
    )
    v_max_search = 110.0 if ac.has_wing else 30.0
    V_best, range_best, t_best = best_cruise_speed(
        ac, altitude_m, temp_offset,
        v_min=1.0, v_max=v_max_search, n_pts=221,
        wind_headwind_mps=wind_headwind_mps,
    )

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hover power", f"{P_hover:.0f} W",
              help="Electrical power from the battery, including FoM and drivetrain losses.")
    c2.metric("Hover endurance", f"{t_hover:.1f} min")
    c3.metric("Best-range cruise speed", f"{V_best:.1f} m/s",
              help="Airspeed that minimizes Wh per km (maximum range).")
    c4.metric("Range at best cruise", f"{range_best:.2f} km",
              help=f"Endurance at this speed: {t_best:.1f} min.")

    st.divider()

    # Detail layout
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Aircraft summary")
        st.markdown(
            f"""
| Quantity | Value |
|---|---|
| Vehicle | **{ac.name}** |
| Mass (flying) | {ac.mass_kg:.3f} kg ({ac.mass_kg * 2.205:.2f} lb) |
| Rotors | {ac.n_rotors} × {ac.rotor_diameter_m * 39.37:.2f} in |
| Disk area | {ac.disk_area_m2:.3f} m² |
| Disk loading | **{ac.disk_loading_Nm2:.1f} N/m²** |
| Battery | {ac.battery_capacity_Ah:.2f} Ah × {ac.battery_voltage_V:.2f} V |
| Battery nameplate | {ac.nameplate_Wh:.1f} Wh |
| Battery usable | {E_usable:.1f} Wh ({100 * E_usable / ac.nameplate_Wh:.0f} %) |
            """,
        )
        if ac.notes:
            st.caption(f"_{ac.notes}_")

    with right:
        st.subheader("Operating conditions")
        st.markdown(
            f"""
| Quantity | Value |
|---|---|
| Altitude | {altitude_m} m |
| Temp offset (ISA) | {temp_offset:+d} °C |
| Air density | **{rho:.4f} kg/m³** ({100 * rho / 1.225:.1f} % of sea level) |
| FoM (induced) | {ac.figure_of_merit:.2f} |
| Drivetrain efficiency | {ac.drivetrain_efficiency:.2f} |
| Profile power at hover | **{ac.profile_power_W:.1f} W** |
            """,
        )
        # v5 fields
        v5_lines = []
        if ac.transition_width_mps > 0:
            v5_lines.append(f"| Transition width | {ac.transition_width_mps:.1f} m/s |")
        if ac.profile_K_mu > 0:
            v5_lines.append(f"| Profile K_μ | {ac.profile_K_mu:.2f} |")
        if ac.cooling_power_W > 0:
            v5_lines.append(f"| Cooling power | {ac.cooling_power_W:.0f} W |")
        if ac.voltage_sag_at_full_load > 0:
            v5_lines.append(f"| Voltage sag | {ac.voltage_sag_at_full_load:.2f} |")
        if altitude_AGL_m < 10.0:
            v5_lines.append(f"| Altitude AGL | {altitude_AGL_m:.1f} m |")
        if wind_headwind_mps != 0:
            v5_lines.append(f"| Wind headwind | {wind_headwind_mps:+.1f} m/s |")
        if v5_lines:
            st.markdown("**v5 physics active:**")
            st.markdown("| Parameter | Value |\n|---|---|\n" + "\n".join(v5_lines))

    st.divider()

    # User-specified cruise speed
    st.subheader("Endurance at a specified cruise speed")
    V_user = st.slider("Cruise airspeed [m/s]", 0.0, 30.0, float(V_best), 0.5)
    if V_user < 0.1:
        t_min, rng_km = t_hover, 0.0
        P_user = P_hover
    else:
        t_min, rng_km = forward_endurance_and_range(
            ac, V_user, altitude_m, temp_offset,
            wind_headwind_mps=wind_headwind_mps,
        )
        P_user = forward_flight_power(
            ac.mass_kg, V_user, ac.n_rotors, ac.rotor_diameter_m,
            ac.Cd_body, ac.frontal_area_m2,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            profile_power_W=ac.profile_power_W,
            altitude_m=altitude_m, temperature_offset_c=temp_offset,
        )
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Power required", f"{P_user:.0f} W")
    cc2.metric("Endurance", f"{t_min:.1f} min")
    cc3.metric("Range", f"{rng_km:.2f} km")


# ----------------------------------------------------------------------
# TAB 2 -- Power / endurance / range curves
# ----------------------------------------------------------------------
with tab_curves:
    v_curve_max = 110.0 if ac.has_wing else 30.0
    speeds = np.linspace(0.1, v_curve_max, 120)
    P_arr = power_curve(ac, list(speeds), altitude_m, temp_offset)
    E_usable = battery_usable_Wh(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
    )
    t_arr = [60.0 * E_usable / P for P in P_arr]
    rng_arr = [(V * (t / 60.0)) * 3.6 for V, t in zip(speeds, t_arr)]

    df = pd.DataFrame({
        "Airspeed (m/s)": speeds,
        "Power (W)": P_arr,
        "Endurance (min)": t_arr,
        "Range (km)": rng_arr,
    })

    V_best, range_best, t_best = best_cruise_speed(
        ac, altitude_m, temp_offset,
        v_min=1.0, v_max=v_curve_max, n_pts=221,
    )

    st.subheader("Power required vs airspeed")
    base_chart = alt.Chart(df).encode(x=alt.X("Airspeed (m/s)"))
    p_line = base_chart.mark_line(strokeWidth=2.5).encode(
        y=alt.Y("Power (W)", scale=alt.Scale(zero=False)),
        tooltip=["Airspeed (m/s)", "Power (W)"],
    )
    rule = alt.Chart(pd.DataFrame({"x": [V_best]})).mark_rule(
        color="#e8a93e", strokeDash=[4, 3]
    ).encode(x="x")
    st.altair_chart(p_line + rule, use_container_width=True)
    st.caption(
        f"Dashed line marks the best-range cruise speed (V = {V_best:.1f} m/s). "
        "The classic multirotor power curve: induced power drops as forward speed "
        "reduces the rotor disk's induced-velocity requirement, then parasite "
        "drag takes over and total power climbs."
    )

    st.subheader("Endurance and range vs airspeed")
    df_long = df.melt(
        id_vars=["Airspeed (m/s)"],
        value_vars=["Endurance (min)", "Range (km)"],
        var_name="Metric", value_name="Value",
    )
    ec = alt.Chart(df_long).mark_line(strokeWidth=2.5).encode(
        x="Airspeed (m/s)",
        y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
        color=alt.Color("Metric:N", scale=alt.Scale(range=["#1f77b4", "#d62728"])),
        tooltip=["Airspeed (m/s)", "Metric", "Value"],
    ).properties(height=320)
    st.altair_chart(ec + rule, use_container_width=True)

    st.subheader("Raw data")
    st.dataframe(df.style.format({
        "Airspeed (m/s)": "{:.2f}",
        "Power (W)": "{:.1f}",
        "Endurance (min)": "{:.1f}",
        "Range (km)": "{:.2f}",
    }), height=260, use_container_width=True)


# ----------------------------------------------------------------------
# TAB 3 -- Validation against published specs
# ----------------------------------------------------------------------
with tab_valid:
    st.subheader("Predicted vs published hover endurance")
    st.markdown(
        "Each aircraft is evaluated twice:\n"
        "- **Untuned**: universal defaults FoM = 0.65, η<sub>drive</sub> = 0.78.\n"
        "- **Tuned**: per-aircraft FoM and η<sub>drive</sub> (see `aircraft_db.py`).\n\n"
        "The gap between columns is the headline result: it tells you how much "
        "per-aircraft calibration is worth.",
        unsafe_allow_html=True,
    )

    rows = run_validation(verbose=False)
    valid_df = pd.DataFrame(rows)
    show = valid_df[[
        "aircraft", "mass_kg", "battery_Wh_nameplate", "disk_loading_Nm2",
        "published_hover_min", "predicted_untuned", "err_untuned_pct",
        "predicted_tuned", "err_tuned_pct",
    ]].rename(columns={
        "aircraft":             "Aircraft",
        "mass_kg":              "Mass (kg)",
        "battery_Wh_nameplate": "Battery (Wh)",
        "disk_loading_Nm2":     "Disk load (N/m²)",
        "published_hover_min":  "Published (min)",
        "predicted_untuned":    "Untuned (min)",
        "err_untuned_pct":      "Err untuned (%)",
        "predicted_tuned":      "Tuned (min)",
        "err_tuned_pct":        "Err tuned (%)",
    })
    st.dataframe(show, use_container_width=True, hide_index=True)

    max_untuned = max(abs(r["err_untuned_pct"]) for r in rows)
    max_tuned   = max(abs(r["err_tuned_pct"])   for r in rows)
    cc1, cc2 = st.columns(2)
    cc1.metric("Max |error| -- universal defaults", f"{max_untuned:.1f} %")
    cc2.metric("Max |error| -- per-aircraft tune", f"{max_tuned:.2f} %")

    st.divider()
    st.subheader("Bar chart: published vs predicted")
    chart_df = pd.DataFrame({
        "Aircraft":  [r["aircraft"] for r in rows] * 3,
        "Source":    (["Published"] * len(rows)
                      + ["Untuned"]  * len(rows)
                      + ["Tuned"]    * len(rows)),
        "Minutes":   ([r["published_hover_min"] for r in rows]
                      + [r["predicted_untuned"]  for r in rows]
                      + [r["predicted_tuned"]    for r in rows]),
    })
    bars = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X("Source:N", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Minutes:Q"),
        color=alt.Color("Source:N", scale=alt.Scale(
            domain=["Published", "Untuned", "Tuned"],
            range=["#1f4d7a", "#c96a3a", "#2e7d5b"],
        )),
        column=alt.Column("Aircraft:N", header=alt.Header(labelOrient="bottom")),
        tooltip=["Aircraft", "Source", "Minutes"],
    ).properties(width=140)
    st.altair_chart(bars, use_container_width=False)


# ----------------------------------------------------------------------
# TAB 4 -- About
# ----------------------------------------------------------------------
with tab_about:
    st.subheader("Model (v3)")
    st.markdown(r"""
The model evolved in three iterations. v3 ships with all three layers
active:

**v1 / Hover** — rotor momentum theory:

$$
P_{\text{induced ideal}} = T \sqrt{\dfrac{T}{2\,\rho\,A}}
$$

**v2 / Profile drag** — adds a constant rotor profile term, splitting
"figure of merit" into a physically meaningful induced piece (≈ 1/κ)
plus a per-aircraft profile-power constant:

$$
P_{\text{shaft}} = \frac{P_{\text{induced ideal}}}{\text{FoM}_\text{ind}} + P_\text{profile}
$$

**v3 / Wing-borne cruise** — for eVTOLs in cruise, the wing makes lift
and rotors become thrust propellers:

$$
C_L = \frac{W}{\tfrac{1}{2}\rho V^2 S}, \qquad
C_D = C_{d_0} + \frac{C_L^2}{\pi\,\text{AR}\,e}
$$

$$
P_{\text{shaft, cruise}} = \frac{T_{\text{thrust}} \cdot V}{\eta_\text{prop}}
\quad\text{where}\quad T_{\text{thrust}} = \tfrac{1}{2}\rho V^2 S\,C_D
$$

**Mode selection**: at each V we compute both rotor-borne (Glauert) and
wing-borne (drag polar) power; the model uses `min()`. Below stall
(CL > CL_max) the wing model returns ∞, forcing rotor mode. Multirotors
just leave `wing_area_m2 = 0`.
    """)

    st.subheader("Defaults & where they come from")
    st.markdown("""
| Parameter | Default | Where it lives |
|---|---|---|
| FoM (induced) | 0.87 | κ=1.15 textbook; premium designs reach 0.90 |
| Drivetrain efficiency | 0.78 | motor + ESC; tune per aircraft |
| Profile power at hover | per-aircraft tuned | rotor blade friction drag |
| Wing Cd₀ | 0.030 | clean modern aerodynamic shape |
| Oswald e | 0.80 | clean wing |
| CL_max | 1.3 | clean wing, no flaps |
| Prop efficiency (cruise) | 0.85 | cruise-pitched propeller |
| Usable battery fraction | 0.90 | reserve policy; 0.85 for FAA eVTOL reserves |
| Discharge efficiency | 0.96 | IR loss at typical multirotor C-rate |
| Body drag coefficient | 1.0 | bluff-body approximation |
| Frontal area | 0.04 m² | depends on airframe |
    """)

    st.subheader("What the model does NOT capture")
    st.markdown("""
- **Smooth mode transition**: real eVTOLs blend rotor and wing lift
  gradually as nacelles tilt. The min() blend creates a small step at
  V_stall — visible on the Joby curve. The step is small in *energy*
  terms (range numbers are essentially correct).
- **Profile power vs airspeed**: held constant.
- **Battery voltage sag**: absorbed on average into discharge efficiency.
- **Low-speed rotor physics**: vortex-ring state, ground effect.
- **BLDC iron losses, ESC switching losses**: lumped into η_drive.
- **Wind and gusts**.
- **Cooling parasitic loads** on premium eVTOLs.
    """)

    st.subheader("Validation methodology")
    st.markdown("""
v3 tuned predictions match published hover specs across **all four
reference aircraft** within **±0.2 %**, spanning a **2400× mass range**
(0.9 kg → 2,177 kg). Mavic 3 forward-flight predictions match within
**±5 %** thanks to v2's profile-drag term. Joby S4 cruise range matches
the published 100 mi (161 km) claim within **0.04 %** thanks to v3's
wing-borne cruise model.

For Joby S4, the hover endurance is *derived* from Stoll (NASA 2015)
shaft power scaled to MTOW + a 165 kWh battery assumption, not a
Joby-published spec. Wing parameters (Cd₀, e, prop efficiency) are
back-solved to match the published cruise range claim.
    """)

    st.subheader("References")
    st.markdown("""
- Leishman, J.G. *Principles of Helicopter Aerodynamics*, 2nd ed. Cambridge, 2006.
- Anderson, J.D. *Aircraft Performance and Design*. McGraw-Hill, 1999.
  (Wing drag polar reference.)
- Stoll, A. *Analysis and Full Scale Testing of the Joby S4 Propulsion System.*
  NASA Ames TVFW Aug 2015. (Used as Joby S4 calibration anchor.)
- Bershadsky, D., Haviland, S., & Johnson, E.N.
  *Electric Multirotor Propulsion System Sizing for Performance Prediction
  and Design Optimization.* AIAA SciTech 2016.
- Bacchini, A., & Cestino, E.
  *Electric VTOL Configurations Comparison.* Aerospace 6.3, 2019.

**Aircraft specifications retrieved May 12, 2026:**
- DJI Mavic 3: dji.com/mavic-3-classic/specs
- Skydio X10: skydio.com/x10/faqs
- Freefly Alta X: freeflysystems.com/alta-x; advexure.com
- Joby S4: FAA airworthiness criteria JAS4-1; aopa.org; Stoll NASA 2015
    """)

    st.caption("Built by D. Angelou, UMich ME '27. Open source — fork it.")
