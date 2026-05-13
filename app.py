"""
app.py — Streamlit UI for the Battery Endurance Calculator.
Three tabs: Aircraft Library, Design Your Aircraft, Compare.
"""
from __future__ import annotations
import math, json, datetime, textwrap
from dataclasses import asdict, fields as dc_fields, replace
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from endurance import (
    Aircraft, G, air_density, battery_usable_Wh,
    hover_power_momentum_theory, hover_endurance_min,
    forward_flight_power, forward_endurance_and_range,
    power_curve, best_cruise_speed, stall_speed,
)
from aircraft_db import ALL_AIRCRAFT, PUBLISHED_HOVER_MIN
from validate import run_validation
from endurance_checks import check_aircraft

_FIELD_NAMES = [f.name for f in dc_fields(Aircraft)]
_V5 = 'cooling_power_W' in _FIELD_NAMES

st.set_page_config(page_title="Multirotor Endurance Calculator", page_icon="🚁", layout="wide")

# ── Sidebar (shared) ────────────────────────────────────────────────
st.sidebar.markdown("## 🚁 Endurance Calculator")
st.sidebar.caption("Rotor momentum theory + wing-borne cruise model, validated against 7 aircraft.")
with st.sidebar.expander("📖 Quick reference"):
    st.markdown("""
**How it works:** The model computes hover power from rotor momentum
theory (thrust = weight, induced velocity from actuator disk). Forward
flight adds Glauert's inflow model plus body parasite drag. For winged
eVTOLs, wing-borne cruise uses a classical drag polar (Cd₀ + induced).

**Typical values by aircraft class:**

| Parameter | Consumer drone | Heavy-lift | eVTOL |
|---|---|---|---|
| FoM | 0.60–0.70 | 0.70–0.80 | 0.85–0.90 |
| η_drive | 0.75–0.82 | 0.78–0.85 | 0.85–0.92 |
| Disk loading | 50–150 N/m² | 100–300 N/m² | 400–800 N/m² |
| Cd₀ (wing) | — | — | 0.020–0.035 |

[Physical model details →](https://github.com/angeloudavidj-png/battery-endurance-calculator#readme)
    """)
st.sidebar.markdown("---")
st.sidebar.caption("Built by D. Angelou, UMich ME '27\n\n"
                    "[GitHub repo](https://github.com/angeloudavidj-png/battery-endurance-calculator)")

# ── Helper: compute predictions for an Aircraft ─────────────────────
def _predict(ac, alt_m=0.0, temp_c=0.0, agl=10000.0, wind=0.0):
    kw = {}
    if _V5:
        P_h = hover_power_momentum_theory(
            ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            profile_power_W=ac.profile_power_W,
            altitude_m=alt_m, temperature_offset_c=temp_c,
            altitude_AGL_m=agl, cooling_power_W=getattr(ac,'cooling_power_W',0))
        t_h = hover_endurance_min(ac, alt_m, temp_c, altitude_AGL_m=agl)
    else:
        P_h = hover_power_momentum_theory(
            ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            profile_power_W=ac.profile_power_W,
            altitude_m=alt_m, temperature_offset_c=temp_c)
        t_h = hover_endurance_min(ac, alt_m, temp_c)
    vm = 110.0 if ac.has_wing else 30.0
    if _V5:
        Vb, Rb, Tb = best_cruise_speed(ac, alt_m, temp_c, v_min=1.0, v_max=vm, n_pts=221, wind_headwind_mps=wind)
    else:
        Vb, Rb, Tb = best_cruise_speed(ac, alt_m, temp_c, v_min=1.0, v_max=vm, n_pts=221)
    return P_h, t_h, Vb, Rb, Tb

# ── Tabs ─────────────────────────────────────────────────────────────
tab_lib, tab_design, tab_compare = st.tabs(
    ["📚 Aircraft Library", "🛠️ Design Your Aircraft", "⚖️ Compare"])

# ══════════════════════════════════════════════════════════════════════
# TAB 1 — Aircraft Library
# ══════════════════════════════════════════════════════════════════════
with tab_lib:
    st.markdown("# 📚 Aircraft Library")
    st.info("💡 Want to design your own aircraft? Use the **🛠️ Design Your Aircraft** tab.")
    preset_names = [ac.name for ac in ALL_AIRCRAFT]
    lib_choice = st.selectbox("Select a reference aircraft", preset_names, index=0, key="lib_preset")
    lib_base = next(a for a in ALL_AIRCRAFT if a.name == lib_choice)

    with st.expander("Airframe", expanded=True):
        lib_mass = st.number_input("Mass [kg]", 0.05, 5000.0, float(lib_base.mass_kg), step=0.05, format="%.3f", key="lib_mass")
        lib_nrot = st.number_input("Number of rotors", 1, 20, int(lib_base.n_rotors), 1, key="lib_nrot")
        lib_rdiam_in = st.number_input("Rotor diameter [in]", 2.0, 200.0, float(lib_base.rotor_diameter_m*39.3701), step=0.1, format="%.2f", key="lib_rdiam")
        lib_rdiam = lib_rdiam_in / 39.3701

    with st.expander("Battery", expanded=True):
        lib_cap = st.number_input("Capacity [Ah]", 0.1, 5000.0, float(lib_base.battery_capacity_Ah), step=0.1, format="%.3f", key="lib_cap")
        lib_cells = st.number_input("Cells in series", 1, 300, int(round(lib_base.battery_voltage_V/3.7)), 1, key="lib_cells")
        lib_chem = st.selectbox("Chemistry", ["LiPo (3.85 V)", "Li-ion (3.7 V)", "Custom V"], key="lib_chem")
        if lib_chem.startswith("LiPo"): lib_vpc = 3.85
        elif lib_chem.startswith("Li-ion"): lib_vpc = 3.70
        else: lib_vpc = st.number_input("V per cell", 2.5, 4.5, 3.7, 0.05, key="lib_vpc")
        lib_volt = lib_cells * lib_vpc
        st.caption(f"Pack voltage: **{lib_volt:.2f} V** ({lib_cap*lib_volt:.1f} Wh)")

    with st.expander("Efficiency"):
        lib_fom = st.slider("FoM", 0.40, 0.95, float(lib_base.figure_of_merit), 0.01, key="lib_fom")
        lib_eta = st.slider("Drivetrain efficiency", 0.55, 0.95, float(lib_base.drivetrain_efficiency), 0.01, key="lib_eta")
        lib_prof = st.number_input("Profile power [W]", 0.0, 500000.0, float(lib_base.profile_power_W), step=1.0, key="lib_prof")
        lib_usable = st.slider("Usable battery fraction", 0.60, 1.00, float(lib_base.usable_fraction), 0.01, key="lib_usable")
        lib_batteff = st.slider("Discharge efficiency", 0.85, 1.00, float(lib_base.discharge_efficiency), 0.01, key="lib_batteff")

    with st.expander("Forward flight drag"):
        lib_cd = st.slider("Body Cd", 0.3, 2.0, float(lib_base.Cd_body), 0.05, key="lib_cd")
        lib_af = st.number_input("Frontal area [m²]", 0.005, 10.0, float(lib_base.frontal_area_m2), step=0.005, format="%.3f", key="lib_af")

    with st.expander("Wing-borne cruise (eVTOL)"):
        lib_wa = st.number_input("Wing area [m²]", 0.0, 200.0, float(lib_base.wing_area_m2), step=0.5, key="lib_wa")
        lib_ws = st.number_input("Wingspan [m]", 0.0, 100.0, float(lib_base.wing_span_m), step=0.5, key="lib_ws")
        lib_cd0 = st.slider("Cd₀", 0.010, 0.080, float(lib_base.Cd0), 0.001, key="lib_cd0")
        lib_oe = st.slider("Oswald e", 0.60, 0.95, float(lib_base.oswald_e), 0.01, key="lib_oe")
        lib_clm = st.slider("CL_max", 1.0, 2.5, float(lib_base.CL_max), 0.05, key="lib_clm")
        lib_pe = st.slider("Prop efficiency", 0.65, 0.95, float(lib_base.prop_efficiency), 0.01, key="lib_pe")

    with st.expander("Atmosphere"):
        lib_alt = st.slider("Altitude [m]", 0, 5000, 0, 50, key="lib_alt")
        lib_temp = st.slider("Temp offset (ISA) [°C]", -30, 50, 0, 1, key="lib_temp")

    if _V5:
        with st.expander("v5 physics (advanced)"):
            lib_agl = st.slider("Altitude AGL [m]", 0.0, 50.0, 10.0, 0.5, key="lib_agl")
            lib_wind = st.slider("Wind headwind [m/s]", -15.0, 15.0, 0.0, 0.5, key="lib_wind")
    else:
        lib_agl, lib_wind = 10000.0, 0.0

    # Build library Aircraft
    _lkw = dict(name=lib_base.name, mass_kg=lib_mass, n_rotors=int(lib_nrot),
                rotor_diameter_m=lib_rdiam, battery_capacity_Ah=lib_cap,
                battery_voltage_V=lib_volt, Cd_body=lib_cd, frontal_area_m2=lib_af,
                figure_of_merit=lib_fom, drivetrain_efficiency=lib_eta,
                profile_power_W=lib_prof, usable_fraction=lib_usable,
                discharge_efficiency=lib_batteff, wing_area_m2=lib_wa,
                wing_span_m=lib_ws, Cd0=lib_cd0, oswald_e=lib_oe,
                CL_max=lib_clm, prop_efficiency=lib_pe, notes=lib_base.notes)
    if _V5:
        _lkw.update(transition_width_mps=getattr(lib_base,'transition_width_mps',0.0),
                     profile_K_mu=getattr(lib_base,'profile_K_mu',0.0),
                     rotor_tip_speed_mps=getattr(lib_base,'rotor_tip_speed_mps',200.0),
                     voltage_sag_at_full_load=getattr(lib_base,'voltage_sag_at_full_load',0.0),
                     cooling_power_W=getattr(lib_base,'cooling_power_W',0.0))
    lib_ac = Aircraft(**_lkw)

    P_h, t_h, Vb, Rb, Tb = _predict(lib_ac, lib_alt, lib_temp, lib_agl, lib_wind)
    E_us = battery_usable_Wh(lib_ac.battery_capacity_Ah, lib_ac.battery_voltage_V,
                              lib_ac.usable_fraction, lib_ac.discharge_efficiency)
    rho = air_density(lib_alt, lib_temp)

    st.divider()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Hover power", f"{P_h:.0f} W")
    c2.metric("Hover endurance", f"{t_h:.1f} min")
    c3.metric("Best-range speed", f"{Vb:.1f} m/s")
    c4.metric("Range at best cruise", f"{Rb:.2f} km", help=f"Endurance: {Tb:.1f} min")

    left, right = st.columns(2)
    with left:
        st.subheader("Aircraft summary")
        st.markdown(f"""
| Quantity | Value |
|---|---|
| Vehicle | **{lib_ac.name}** |
| Mass | {lib_ac.mass_kg:.3f} kg ({lib_ac.mass_kg*2.205:.2f} lb) |
| Rotors | {lib_ac.n_rotors} × {lib_ac.rotor_diameter_m*39.37:.2f} in |
| Disk area | {lib_ac.disk_area_m2:.3f} m² |
| Disk loading | **{lib_ac.disk_loading_Nm2:.1f} N/m²** |
| Battery | {lib_ac.battery_capacity_Ah:.2f} Ah × {lib_ac.battery_voltage_V:.2f} V |
| Nameplate | {lib_ac.nameplate_Wh:.1f} Wh |
| Usable | {E_us:.1f} Wh ({100*E_us/lib_ac.nameplate_Wh:.0f}%) |""")
        if lib_ac.notes:
            st.caption(f"_{lib_ac.notes}_")
    with right:
        st.subheader("Operating conditions")
        st.markdown(f"""
| Quantity | Value |
|---|---|
| Altitude | {lib_alt} m |
| Temp offset | {lib_temp:+d} °C |
| Air density | **{rho:.4f} kg/m³** ({100*rho/1.225:.1f}%) |
| FoM | {lib_ac.figure_of_merit:.2f} |
| η_drive | {lib_ac.drivetrain_efficiency:.2f} |
| Profile power | {lib_ac.profile_power_W:.1f} W |""")

    # Cruise speed slider
    st.divider()
    st.subheader("Endurance at a specified cruise speed")
    _vmax_sl = 110.0 if lib_ac.has_wing else 30.0
    V_user = st.slider("Cruise airspeed [m/s]", 0.0, _vmax_sl, float(Vb), 0.5, key="lib_vuser")
    if V_user < 0.1:
        t_u, r_u, P_u = t_h, 0.0, P_h
    else:
        if _V5:
            t_u, r_u = forward_endurance_and_range(lib_ac, V_user, lib_alt, lib_temp, wind_headwind_mps=lib_wind)
        else:
            t_u, r_u = forward_endurance_and_range(lib_ac, V_user, lib_alt, lib_temp)
        P_u = forward_flight_power(lib_ac.mass_kg, V_user, lib_ac.n_rotors, lib_ac.rotor_diameter_m,
                                    lib_ac.Cd_body, lib_ac.frontal_area_m2, lib_ac.figure_of_merit,
                                    lib_ac.drivetrain_efficiency, profile_power_W=lib_ac.profile_power_W,
                                    altitude_m=lib_alt, temperature_offset_c=lib_temp)
    cc1,cc2,cc3 = st.columns(3)
    cc1.metric("Power", f"{P_u:.0f} W"); cc2.metric("Endurance", f"{t_u:.1f} min"); cc3.metric("Range", f"{r_u:.2f} km")

    # Power curve section
    with st.expander("📈 Power curve", expanded=False):
        vc_max = 110.0 if lib_ac.has_wing else 30.0
        speeds = np.linspace(0.1, vc_max, 120)
        P_arr = power_curve(lib_ac, list(speeds), lib_alt, lib_temp)
        E_cv = battery_usable_Wh(lib_ac.battery_capacity_Ah, lib_ac.battery_voltage_V, lib_ac.usable_fraction, lib_ac.discharge_efficiency)
        t_arr = [60.0*E_cv/P for P in P_arr]
        rng_arr = [(V*(t/60.0))*3.6 for V,t in zip(speeds, t_arr)]
        df = pd.DataFrame({"Airspeed (m/s)": speeds, "Power (W)": P_arr, "Endurance (min)": t_arr, "Range (km)": rng_arr})
        bc = alt.Chart(df).encode(x="Airspeed (m/s)")
        pl = bc.mark_line(strokeWidth=2.5).encode(y=alt.Y("Power (W)", scale=alt.Scale(zero=False)), tooltip=["Airspeed (m/s)", "Power (W)"])
        rl = alt.Chart(pd.DataFrame({"x":[Vb]})).mark_rule(color="#e8a93e", strokeDash=[4,3]).encode(x="x")
        st.altair_chart(pl+rl, use_container_width=True)
        st.caption(f"Dashed line: best-range speed ({Vb:.1f} m/s)")

    # Validation section
    with st.expander("✓ Validation", expanded=False):
        st.subheader("Predicted vs published hover endurance")
        rows = run_validation(verbose=False)
        valid_df = pd.DataFrame(rows)
        show = valid_df[["aircraft","mass_kg","battery_Wh_nameplate","disk_loading_Nm2",
                          "published_hover_min","predicted_untuned","err_untuned_pct",
                          "predicted_tuned","err_tuned_pct"]].rename(columns={
            "aircraft":"Aircraft","mass_kg":"Mass (kg)","battery_Wh_nameplate":"Battery (Wh)",
            "disk_loading_Nm2":"DL (N/m²)","published_hover_min":"Published (min)",
            "predicted_untuned":"Untuned","err_untuned_pct":"Err %","predicted_tuned":"Tuned","err_tuned_pct":"Err %  "})
        st.dataframe(show, use_container_width=True, hide_index=True)
        mu = max(abs(r["err_untuned_pct"]) for r in rows)
        mt = max(abs(r["err_tuned_pct"]) for r in rows)
        e1,e2 = st.columns(2)
        e1.metric("Max |err| untuned", f"{mu:.1f}%"); e2.metric("Max |err| tuned", f"{mt:.2f}%")

    # About section
    with st.expander("📚 About the model", expanded=False):
        st.markdown(r"""
**v1 — Hover**: $P_{\text{induced}} = T\sqrt{T/(2\rho A)}$, divided by FoM and η_drive.

**v2 — Profile drag**: adds constant rotor profile term.

**v3 — Wing-borne cruise**: wing drag polar $C_D = C_{d_0} + C_L^2/(\pi\cdot AR\cdot e)$.

**v5 — Physics extensions**: smooth sigmoid transition, μ-scaling, voltage sag,
ground effect, cooling, wind, VRS boundary — all opt-in with backward-compatible defaults.
        """)
        st.caption("Built by D. Angelou, UMich ME '27.")


# ══════════════════════════════════════════════════════════════════════
# TAB 2 — Design Your Aircraft
# ══════════════════════════════════════════════════════════════════════
_TEMPLATES = {
    "Consumer multirotor (~1 kg)": dict(mass_kg=1.0, n_rotors=4, rotor_diameter_m=0.25,
        battery_capacity_Ah=5.0, battery_voltage_V=14.8, Cd_body=1.0, frontal_area_m2=0.03,
        figure_of_merit=0.65, drivetrain_efficiency=0.78, profile_power_W=0.0,
        usable_fraction=0.90, discharge_efficiency=0.96,
        wing_area_m2=0.0, wing_span_m=0.0, Cd0=0.030, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
    "Heavy-lift multirotor (~15 kg)": dict(mass_kg=15.0, n_rotors=8, rotor_diameter_m=0.71,
        battery_capacity_Ah=32.0, battery_voltage_V=44.4, Cd_body=1.0, frontal_area_m2=0.12,
        figure_of_merit=0.87, drivetrain_efficiency=0.85, profile_power_W=120.0,
        usable_fraction=0.90, discharge_efficiency=0.96,
        wing_area_m2=0.0, wing_span_m=0.0, Cd0=0.030, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
    "eVTOL tilt-rotor (à la Joby S4)": dict(mass_kg=2200.0, n_rotors=6, rotor_diameter_m=2.9,
        battery_capacity_Ah=1650.0, battery_voltage_V=100.0, Cd_body=0.4, frontal_area_m2=2.0,
        figure_of_merit=0.87, drivetrain_efficiency=0.90, profile_power_W=8000.0,
        usable_fraction=0.85, discharge_efficiency=0.96,
        wing_area_m2=20.0, wing_span_m=12.0, Cd0=0.028, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
    "eVTOL lift+cruise (à la Archer)": dict(mass_kg=2900.0, n_rotors=12, rotor_diameter_m=1.5,
        battery_capacity_Ah=1400.0, battery_voltage_V=100.0, Cd_body=0.4, frontal_area_m2=2.5,
        figure_of_merit=0.87, drivetrain_efficiency=0.88, profile_power_W=12000.0,
        usable_fraction=0.85, discharge_efficiency=0.96,
        wing_area_m2=18.0, wing_span_m=12.0, Cd0=0.024, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
    "eVTOL lift+pusher (à la Beta)": dict(mass_kg=2700.0, n_rotors=5, rotor_diameter_m=2.4,
        battery_capacity_Ah=3500.0, battery_voltage_V=100.0, Cd_body=0.4, frontal_area_m2=2.0,
        figure_of_merit=0.87, drivetrain_efficiency=0.90, profile_power_W=6000.0,
        usable_fraction=0.85, discharge_efficiency=0.96,
        wing_area_m2=19.0, wing_span_m=15.0, Cd0=0.027, oswald_e=0.85, CL_max=1.4, prop_efficiency=0.88),
    "eVTOL tilt+lift (à la VX4)": dict(mass_kg=2500.0, n_rotors=8, rotor_diameter_m=2.2,
        battery_capacity_Ah=1440.0, battery_voltage_V=100.0, Cd_body=0.4, frontal_area_m2=2.0,
        figure_of_merit=0.87, drivetrain_efficiency=0.88, profile_power_W=10000.0,
        usable_fraction=0.85, discharge_efficiency=0.96,
        wing_area_m2=17.0, wing_span_m=12.0, Cd0=0.030, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
    "Custom (blank)": dict(mass_kg=1.0, n_rotors=4, rotor_diameter_m=0.25,
        battery_capacity_Ah=5.0, battery_voltage_V=14.8, Cd_body=1.0, frontal_area_m2=0.04,
        figure_of_merit=0.75, drivetrain_efficiency=0.85, profile_power_W=0.0,
        usable_fraction=0.85, discharge_efficiency=0.96,
        wing_area_m2=0.0, wing_span_m=0.0, Cd0=0.030, oswald_e=0.80, CL_max=1.3, prop_efficiency=0.85),
}

with tab_design:
    st.markdown("# 🛠️ Design Your Aircraft")
    st.markdown("Input your own specs and get predictions backed by the same physics that validates against 7 real aircraft.")

    # Template selector with session_state pattern
    tpl_names = list(_TEMPLATES.keys())
    if "d_last_tpl" not in st.session_state:
        st.session_state["d_last_tpl"] = tpl_names[0]
    tpl_choice = st.selectbox("Start from a template:", tpl_names, key="d_tpl_sel")
    if tpl_choice != st.session_state["d_last_tpl"]:
        t = _TEMPLATES[tpl_choice]
        for k, v in t.items():
            st.session_state[f"d_{k}"] = v
        st.session_state["d_has_wing"] = t["wing_area_m2"] > 0
        st.session_state["d_last_tpl"] = tpl_choice
        st.rerun()

    # Defaults for first load
    _t = _TEMPLATES[tpl_choice]
    def _dv(k): return st.session_state.get(f"d_{k}", _t.get(k, 0))

    # ── Input groups ──
    with st.expander("✈️ Mission & Mass", expanded=True):
        d_mass = st.number_input("Mass [kg]", 0.1, 3500.0, float(_dv("mass_kg")), step=0.1, key="d_mass_kg",
                                  help="Total flying mass including airframe, battery, and payload.")
        d_mission = st.radio("Mission profile", ["Hover-dominated", "Mixed", "Cruise-dominated"],
                              index=1, key="d_mission", horizontal=True,
                              help="Used for output color-coding only — not a model parameter.")

    with st.expander("🌀 Rotors"):
        d_nrot = st.number_input("Number of rotors", 1, 20, int(_dv("n_rotors")), 1, key="d_n_rotors")
        d_rdiam = st.number_input("Rotor diameter [m]", 0.05, 5.0, float(_dv("rotor_diameter_m")),
                                   step=0.01, format="%.3f", key="d_rotor_diameter_m",
                                   help="Tip-to-tip diameter of a single rotor.")
        if _V5 and 'rotor_tip_speed_mps' in _FIELD_NAMES:
            d_tip = st.number_input("Tip speed [m/s]", 50.0, 300.0, 200.0, 5.0, key="d_rotor_tip_speed_mps")
        else:
            d_tip = 200.0
        _da = d_nrot * math.pi * (d_rdiam/2)**2
        _dl = (d_mass*G) / _da if _da > 0 else 0
        m1,m2 = st.columns(2)
        m1.metric("Disk area", f"{_da:.3f} m²"); m2.metric("Disk loading", f"{_dl:.1f} N/m²")

    with st.expander("🔋 Battery"):
        d_cap = st.number_input("Capacity [Ah]", 0.1, 5000.0, float(_dv("battery_capacity_Ah")),
                                 step=0.1, format="%.2f", key="d_battery_capacity_Ah")
        d_volt = st.number_input("Voltage [V]", 3.0, 1000.0, float(_dv("battery_voltage_V")),
                                  step=0.1, format="%.1f", key="d_battery_voltage_V")
        st.metric("Nameplate energy", f"{d_cap*d_volt:.1f} Wh")
        d_usable = st.slider("Usable fraction", 0.50, 1.00, float(_dv("usable_fraction")), 0.01, key="d_usable_fraction",
                              help="How much of the battery you actually use. 0.85 for FAA eVTOL reserves, 0.90 typical consumer.")
        d_batteff = st.slider("Discharge efficiency", 0.85, 0.99, float(_dv("discharge_efficiency")), 0.01, key="d_discharge_efficiency")
        if _V5 and 'voltage_sag_at_full_load' in _FIELD_NAMES:
            d_sag = st.slider("Voltage sag at full load", 0.0, 0.20, 0.0, 0.01, key="d_voltage_sag_at_full_load",
                               help="Fractional voltage drop under max load. Typical 0.05–0.15.")
        else:
            d_sag = 0.0

    with st.expander("🪶 Body & Aerodynamics"):
        d_cd = st.slider("Body drag Cd", 0.2, 2.0, float(_dv("Cd_body")), 0.05, key="d_Cd_body",
                          help="Fuselage form drag coefficient. Matters most in rotor-borne forward flight.")
        d_af = st.number_input("Frontal area [m²]", 0.005, 10.0, float(_dv("frontal_area_m2")),
                                step=0.005, format="%.3f", key="d_frontal_area_m2")
        d_has_wing = st.checkbox("Does this aircraft have a wing?",
                                  value=st.session_state.get("d_has_wing", _dv("wing_area_m2") > 0),
                                  key="d_has_wing")
        if d_has_wing:
            d_wa = st.number_input("Wing area [m²]", 0.1, 200.0, max(0.1, float(_dv("wing_area_m2"))),
                                    step=0.5, key="d_wing_area_m2")
            d_ws = st.number_input("Wingspan [m]", 0.1, 100.0, max(0.1, float(_dv("wing_span_m"))),
                                    step=0.5, key="d_wing_span_m")
            _ar = d_ws**2 / d_wa if d_wa > 0 else 0
            st.metric("Aspect ratio", f"{_ar:.1f}")
            d_cd0 = st.slider("Cd₀", 0.018, 0.060, float(_dv("Cd0")), 0.001, key="d_Cd0")
            d_oe = st.slider("Oswald e", 0.60, 0.95, float(_dv("oswald_e")), 0.01, key="d_oswald_e")
            d_clm = st.slider("CL_max", 0.8, 1.8, float(_dv("CL_max")), 0.05, key="d_CL_max")
            d_pe = st.slider("Prop efficiency η_prop", 0.70, 0.92, float(_dv("prop_efficiency")), 0.01, key="d_prop_efficiency")
            _wl = (d_mass*G)/d_wa if d_wa > 0 else 0
            _vs = stall_speed(d_mass, d_wa, d_clm) if d_wa > 0 else float("inf")
            w1,w2 = st.columns(2)
            w1.metric("Wing loading", f"{_wl:.0f} N/m²")
            w2.metric("V_stall", f"{_vs:.1f} m/s" if not math.isinf(_vs) else "N/A")
        else:
            d_wa, d_ws, d_cd0, d_oe, d_clm, d_pe = 0.0, 0.0, 0.030, 0.80, 1.3, 0.85

    with st.expander("⚙️ Efficiency & Losses"):
        d_fom = st.slider("Figure of merit", 0.55, 0.92, float(_dv("figure_of_merit")), 0.01, key="d_figure_of_merit",
                            help="Induced-power efficiency. Consumer: 0.60–0.70. Premium: 0.75–0.85. Best eVTOL: 0.85–0.90. Above 0.90 is borderline unphysical.")
        d_eta = st.slider("Drivetrain efficiency", 0.65, 0.95, float(_dv("drivetrain_efficiency")), 0.01, key="d_drivetrain_efficiency")
        d_prof = st.number_input("Profile power [W]", 0.0, 500000.0, float(_dv("profile_power_W")), step=1.0, key="d_profile_power_W",
                                  help="Rotor blade drag in hover. Roughly 10–25% of total hover power. Set to 0 for pure momentum theory.")
        if _V5 and 'profile_K_mu' in _FIELD_NAMES:
            d_kmu = st.slider("Profile K_μ", 0.0, 8.0, 0.0, 0.1, key="d_profile_K_mu",
                               help="Advance-ratio profile scaling. 4.65 typical for eVTOLs. 0 = constant profile.")
        else:
            d_kmu = 0.0
        if _V5 and 'cooling_power_W' in _FIELD_NAMES:
            d_cool = st.number_input("Cooling power [W]", 0.0, 50000.0, 0.0, step=100.0, key="d_cooling_power_W",
                                      help="Constant electrical draw from cooling systems (liquid cooling on eVTOLs).")
        else:
            d_cool = 0.0

    with st.expander("🌍 Environment"):
        d_alt = st.slider("Altitude [m]", 0, 5000, 0, 50, key="d_alt")
        d_temp = st.slider("Temperature offset (ISA) [°C]", -20, 50, 0, 1, key="d_temp")
        if _V5:
            d_wind = st.slider("Wind headwind [m/s]", -15.0, 15.0, 0.0, 0.5, key="d_wind",
                                help="Positive = headwind. Negative = tailwind.")
            d_agl = st.slider("Altitude AGL [m]", 0.0, 50.0, 30.0, 0.5, key="d_agl",
                               help="For Cheeseman-Bennett ground effect on hover.")
        else:
            d_wind, d_agl = 0.0, 10000.0

    # Build the design Aircraft
    _dkw = dict(name="My Design", mass_kg=d_mass, n_rotors=int(d_nrot),
                rotor_diameter_m=d_rdiam, battery_capacity_Ah=d_cap,
                battery_voltage_V=d_volt, Cd_body=d_cd, frontal_area_m2=d_af,
                figure_of_merit=d_fom, drivetrain_efficiency=d_eta,
                profile_power_W=d_prof, usable_fraction=d_usable,
                discharge_efficiency=d_batteff, wing_area_m2=d_wa,
                wing_span_m=d_ws, Cd0=d_cd0, oswald_e=d_oe,
                CL_max=d_clm, prop_efficiency=d_pe, notes="Custom design")
    if _V5:
        _dkw.update(transition_width_mps=5.0 if d_has_wing else 0.0,
                     profile_K_mu=d_kmu, rotor_tip_speed_mps=d_tip,
                     voltage_sag_at_full_load=d_sag, cooling_power_W=d_cool)
    des_ac = Aircraft(**_dkw)

    # ── Sanity checks ──
    findings = check_aircraft(des_ac)
    if findings:
        with st.expander(f"🔍 Sanity checks ({len(findings)} findings)", expanded=True):
            for f in findings:
                if f["severity"] == "error": st.error(f["message"])
                elif f["severity"] == "warn": st.warning(f["message"])
                else: st.info(f["message"])
    else:
        with st.expander("🔍 Sanity checks (0 findings)", expanded=False):
            st.success("All parameters look physically reasonable.")

    # ── Predictions ──
    st.divider()
    st.subheader("📊 Predictions")
    dP, dt, dV, dR, dT = _predict(des_ac, d_alt, d_temp, d_agl, d_wind)
    k1,k2,k3 = st.columns(3)
    k1.metric("Hover endurance", f"{dt:.1f} min")
    k2.metric("Best-range cruise", f"{dR:.1f} km @ {dV:.1f} m/s" if dR > 0 else "N/A")
    k3.metric("Cruise endurance", f"{dT:.1f} min @ {dV:.1f} m/s" if dT > 0 else "N/A")

    # Power curve
    st.subheader("Power vs speed")
    d_target_v = st.number_input("Target cruise speed [m/s]", 0.0, 150.0, float(dV), 0.5, key="d_target_v")
    _dvm = 110.0 if des_ac.has_wing else 35.0
    d_speeds = np.linspace(0.1, _dvm, 150)
    d_P = power_curve(des_ac, list(d_speeds), d_alt, d_temp)
    d_df = pd.DataFrame({"Airspeed (m/s)": d_speeds, "Power (W)": d_P})
    d_ch = alt.Chart(d_df).mark_line(strokeWidth=2.5, color="#1f4d7a").encode(
        x="Airspeed (m/s)", y=alt.Y("Power (W)", scale=alt.Scale(zero=False)),
        tooltip=["Airspeed (m/s)", "Power (W)"])
    d_rl = alt.Chart(pd.DataFrame({"x":[d_target_v]})).mark_rule(color="#e8a93e", strokeDash=[4,3]).encode(x="x")
    st.altair_chart(d_ch + d_rl, use_container_width=True)

    # Comparison bar chart
    st.subheader("How does your design compare?")
    if des_ac.has_wing:
        _cmp = [a for a in ALL_AIRCRAFT if a.has_wing]
    else:
        _cmp = [a for a in ALL_AIRCRAFT if not a.has_wing]
    _cmp_data = []
    for ca in _cmp:
        _,_,_cv,_cr,_ = _predict(ca)
        _cmp_data.append({"Aircraft": ca.name, "Range (km)": _cr})
    _cmp_data.append({"Aircraft": "✨ Your Design", "Range (km)": dR})
    _cmp_data.sort(key=lambda x: x["Range (km)"])
    cmp_df = pd.DataFrame(_cmp_data)
    cmp_ch = alt.Chart(cmp_df).mark_bar().encode(
        x=alt.X("Range (km):Q"), y=alt.Y("Aircraft:N", sort="-x"),
        color=alt.condition(alt.datum.Aircraft == "✨ Your Design",
                            alt.value("#e8a93e"), alt.value("#1f4d7a")),
        tooltip=["Aircraft", "Range (km)"])
    st.altair_chart(cmp_ch, use_container_width=True)

    # Sensitivity analysis
    st.subheader("Sensitivity analysis (±10% impact on hover endurance)")
    _sens_params = [("mass_kg", "Mass"), ("battery_capacity_Ah", "Battery Ah"),
                     ("figure_of_merit", "FoM"), ("drivetrain_efficiency", "η_drive")]
    if des_ac.has_wing: _sens_params.append(("Cd0", "Cd₀"))
    else: _sens_params.append(("Cd_body", "Body Cd"))
    _base_t = hover_endurance_min(des_ac, d_alt, d_temp)
    _sens_rows = []
    for field, label in _sens_params:
        val = getattr(des_ac, field)
        if val == 0: continue
        ac_lo = replace(des_ac, **{field: val * 0.9})
        ac_hi = replace(des_ac, **{field: val * 1.1})
        t_lo = hover_endurance_min(ac_lo, d_alt, d_temp)
        t_hi = hover_endurance_min(ac_hi, d_alt, d_temp)
        _sens_rows.append({"Parameter": label, "+10%": t_hi - _base_t, "-10%": t_lo - _base_t})
    _sens_rows.sort(key=lambda x: abs(x["+10%"]) + abs(x["-10%"]), reverse=True)
    if _sens_rows:
        s_df = pd.DataFrame(_sens_rows)
        s_melt = s_df.melt(id_vars="Parameter", var_name="Direction", value_name="Δ endurance (min)")
        s_ch = alt.Chart(s_melt).mark_bar().encode(
            x="Δ endurance (min):Q", y=alt.Y("Parameter:N", sort=None),
            color=alt.Color("Direction:N", scale=alt.Scale(range=["#c96a3a","#2e7d5b"])),
            tooltip=["Parameter","Direction","Δ endurance (min)"])
        st.altair_chart(s_ch, use_container_width=True)

    # Export
    st.divider()
    st.subheader("💾 Export your design")
    _d = asdict(des_ac)
    e1,e2,e3 = st.columns(3)
    # Python export
    _py_lines = ["from endurance import Aircraft\n\n", "my_aircraft = Aircraft(\n"]
    for f in dc_fields(Aircraft):
        v = _d[f.name]
        _py_lines.append(f"    {f.name}={v!r},\n")
    _py_lines.append(")\n")
    e1.download_button("Download .py", "".join(_py_lines), "my_aircraft.py", "text/plain")
    # JSON export
    e2.download_button("Download .json", json.dumps(_d, indent=2), "my_aircraft.json", "application/json")
    # Markdown export
    _md = [f"# Aircraft Design: {des_ac.name}\n", f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n",
           "## Parameters\n", "| Parameter | Value |\n|---|---|\n"]
    for f in dc_fields(Aircraft):
        _md.append(f"| {f.name} | {_d[f.name]} |\n")
    _md.extend([f"\n## Predictions\n", f"- Hover endurance: {dt:.1f} min\n",
                f"- Best-range cruise: {dR:.1f} km @ {dV:.1f} m/s\n",
                f"- Hover power: {dP:.0f} W\n",
                f"\n---\n*Generated by [Battery Endurance Calculator](https://david-angelou-bec.streamlit.app)*\n"])
    e3.download_button("Download .md", "".join(_md), "my_aircraft.md", "text/markdown")

    # Save for Compare
    st.divider()
    if "saved_designs" not in st.session_state:
        st.session_state["saved_designs"] = []
    _save_name = st.text_input("Design name", "My design v1", key="d_save_name")
    if st.button("💾 Save this design for the Compare tab", key="d_save_btn"):
        if len(st.session_state["saved_designs"]) >= 10:
            st.warning("Max 10 saved designs. Remove one first.")
        else:
            st.session_state["saved_designs"].append({"name": _save_name, "ac": des_ac})
            st.success(f"Saved '{_save_name}'!")


# ══════════════════════════════════════════════════════════════════════
# TAB 3 — Compare
# ══════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("# ⚖️ Compare Aircraft")
    saved = st.session_state.get("saved_designs", [])
    _opts = ["(none)"] + [a.name for a in ALL_AIRCRAFT] + [d["name"] for d in saved]

    def _get_ac(name):
        if name == "(none)": return None
        for a in ALL_AIRCRAFT:
            if a.name == name: return a
        for d in saved:
            if d["name"] == name: return d["ac"]
        return None

    s1, s2, s3 = st.columns(3)
    n1 = s1.selectbox("Slot 1", _opts, 0, key="cmp1")
    n2 = s2.selectbox("Slot 2", _opts, 0, key="cmp2")
    n3 = s3.selectbox("Slot 3", _opts, 0, key="cmp3")

    _sel = [(n, _get_ac(n)) for n in [n1, n2, n3] if _get_ac(n) is not None]

    if not _sel:
        if not saved:
            st.info("No custom designs yet. Build one in the 🛠️ **Design Your Aircraft** tab and click **Save**.")
        else:
            st.info("Select at least one aircraft above to compare.")
    else:
        # Power curves overlay
        st.subheader("Power curves")
        _colors = ["#1f4d7a", "#c96a3a", "#2e7d5b"]
        _all_dfs = []
        _markers = []
        for i, (nm, ac) in enumerate(_sel):
            vm = 110.0 if ac.has_wing else 35.0
            sp = np.linspace(0.1, vm, 120)
            pw = power_curve(ac, list(sp))
            _,_,vb,rb,_ = _predict(ac)
            _all_dfs.append(pd.DataFrame({"Airspeed (m/s)": sp, "Power (W)": pw, "Aircraft": nm}))
            _markers.append({"Airspeed (m/s)": vb, "Power (W)": float(np.interp(vb, sp, pw)), "Aircraft": nm})
        cdf = pd.concat(_all_dfs)
        c_lines = alt.Chart(cdf).mark_line(strokeWidth=2.2).encode(
            x="Airspeed (m/s)", y=alt.Y("Power (W)", scale=alt.Scale(zero=False)),
            color=alt.Color("Aircraft:N", scale=alt.Scale(range=_colors[:len(_sel)])),
            tooltip=["Aircraft", "Airspeed (m/s)", "Power (W)"])
        mdf = pd.DataFrame(_markers)
        c_pts = alt.Chart(mdf).mark_point(size=120, filled=True).encode(
            x="Airspeed (m/s)", y="Power (W)",
            color=alt.Color("Aircraft:N", scale=alt.Scale(range=_colors[:len(_sel)])),
            tooltip=["Aircraft", "Airspeed (m/s)", "Power (W)"])
        st.altair_chart(c_lines + c_pts, use_container_width=True)
        st.caption("Dots mark best-range cruise speed for each aircraft.")

        # Bar comparison
        st.subheader("Headline numbers")
        bar_data = []
        for nm, ac in _sel:
            ph, th, vb, rb, tb = _predict(ac)
            bar_data.append({"Aircraft": nm, "Hover (min)": th, "Range (km)": rb,
                              "Best speed (m/s)": vb, "Hover power (W)": ph})
        bdf = pd.DataFrame(bar_data)
        b1, b2 = st.columns(2)
        with b1:
            ch1 = alt.Chart(bdf).mark_bar().encode(
                x="Hover (min):Q", y=alt.Y("Aircraft:N", sort="-x"),
                color=alt.Color("Aircraft:N", legend=None, scale=alt.Scale(range=_colors[:len(_sel)])),
                tooltip=["Aircraft", "Hover (min)"])
            st.altair_chart(ch1, use_container_width=True)
        with b2:
            ch2 = alt.Chart(bdf).mark_bar().encode(
                x="Range (km):Q", y=alt.Y("Aircraft:N", sort="-x"),
                color=alt.Color("Aircraft:N", legend=None, scale=alt.Scale(range=_colors[:len(_sel)])),
                tooltip=["Aircraft", "Range (km)"])
            st.altair_chart(ch2, use_container_width=True)
        st.dataframe(bdf, use_container_width=True, hide_index=True)
