"""
endurance_checks.py
====================
Sanity-check module for the Battery Endurance Calculator.

Provides `check_aircraft(ac)` which returns a list of findings
(info / warn / error) for a given Aircraft instance. Used by the
Streamlit "Design Your Aircraft" tab to flag unphysical parameter
combinations before the user commits to a design.
"""

from __future__ import annotations

import math
from dataclasses import fields as dc_fields

from endurance import (
    Aircraft,
    G,
    air_density,
    hover_power_momentum_theory,
    battery_usable_Wh,
    stall_speed,
)


def check_aircraft(ac: Aircraft) -> list[dict]:
    """Run sanity checks on an Aircraft and return a list of findings.

    Each finding is a dict with keys:
        severity: "info" | "warn" | "error"
        message:  human-readable description

    Checks are wrapped in try/except so a failure in one check
    does not prevent the others from running.
    """
    findings: list[dict] = []

    def _warn(msg: str) -> None:
        findings.append({"severity": "warn", "message": msg})

    def _info(msg: str) -> None:
        findings.append({"severity": "info", "message": msg})

    def _error(msg: str) -> None:
        findings.append({"severity": "error", "message": msg})

    # 1. Disk loading
    try:
        dl = ac.disk_loading_Nm2
        if dl < 30:
            _warn(
                f"Disk loading is very low ({dl:.0f} N/m²). "
                "Typical multirotors: 50–200 N/m²; eVTOLs: 400–800 N/m²."
            )
        elif dl > 2500:
            _warn(
                f"Disk loading is extremely high ({dl:.0f} N/m²). "
                "Even the heaviest eVTOLs stay below ~1000 N/m²."
            )
    except Exception:
        pass

    # 2. Mass
    try:
        if ac.mass_kg > 3500:
            _warn(
                f"Mass ({ac.mass_kg:.0f} kg) exceeds the heaviest production "
                "eVTOL in the database (Archer Midnight at 2,948 kg)."
            )
    except Exception:
        pass

    # 3–5. Wing checks (only if wing is present)
    try:
        if ac.has_wing:
            wl = ac.wing_loading_Nm2
            if wl > 2500:
                _warn(
                    f"Wing loading is very high ({wl:.0f} N/m²). "
                    "Typical eVTOL: 500–1500 N/m²."
                )
            elif wl < 150:
                _warn(
                    f"Wing loading is very low ({wl:.0f} N/m²). "
                    "The wing may be oversized for this mass."
                )
    except Exception:
        pass

    try:
        if ac.has_wing and ac.Cd0 < 0.018:
            _warn(
                f"Cd₀ = {ac.Cd0:.3f} is cleaner than most production wings. "
                "Typical range: 0.020–0.035."
            )
    except Exception:
        pass

    try:
        if ac.has_wing:
            vs = stall_speed(ac.mass_kg, ac.wing_area_m2, ac.CL_max)
            if not math.isinf(vs) and vs > 50:
                _info(
                    f"Stall speed is {vs:.0f} m/s — very high for an eVTOL. "
                    "Consider increasing wing area or CL_max."
                )
    except Exception:
        pass

    # 6. FoM
    try:
        if ac.figure_of_merit > 0.90:
            _warn(
                f"FoM = {ac.figure_of_merit:.2f} exceeds 0.90 — borderline "
                "unphysical. Best production rotors: 0.85–0.90."
            )
    except Exception:
        pass

    # 7. Drivetrain efficiency
    try:
        if ac.drivetrain_efficiency > 0.95:
            _warn(
                f"Drivetrain efficiency {ac.drivetrain_efficiency:.2f} exceeds 0.95 — "
                "very optimistic. Best BLDC + ESC: 0.88–0.93."
            )
    except Exception:
        pass

    # 8. Profile power vs induced hover power
    try:
        if ac.profile_power_W > 0:
            rho = air_density(0.0, 0.0)
            thrust = ac.mass_kg * G
            disk_area = ac.disk_area_m2
            p_induced = thrust * math.sqrt(thrust / (2.0 * rho * disk_area))
            p_ind_shaft = p_induced / ac.figure_of_merit
            if ac.profile_power_W > 0.5 * p_ind_shaft:
                _warn(
                    f"Profile power ({ac.profile_power_W:.0f} W) is more than "
                    f"50% of induced shaft power ({p_ind_shaft:.0f} W). "
                    "Profile typically accounts for 10–25% of total hover power."
                )
    except Exception:
        pass

    # 9. Battery C-rate at hover
    try:
        P_hover = hover_power_momentum_theory(
            ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            profile_power_W=ac.profile_power_W,
        )
        nameplate_Wh = ac.battery_capacity_Ah * ac.battery_voltage_V
        if nameplate_Wh > 0:
            c_rate = P_hover / nameplate_Wh
            if c_rate > 8.0:
                _info(
                    f"Battery C-rate at hover is {c_rate:.1f}C — verify your "
                    "pack chemistry and cooling can sustain this discharge rate."
                )
    except Exception:
        pass

    return findings
