"""
endurance.py
============
Parametric rotorcraft endurance & range model.
  v1: rotor momentum theory only.
  v2: + rotor profile drag (induced + profile decomposition).
  v3: + wing-borne cruise mode for eVTOLs (induced drag + parasite drag).

Physical basis
--------------
ROTOR-BORNE MODE (multirotors, hover, transition):
Rotor shaft power splits into INDUCED (Glauert) + PROFILE (blade friction):

    P_induced_ideal = T * sqrt(T / (2 * rho * A))
    P_shaft         = P_induced_ideal / FoM_induced + profile_power_W
    P_electrical    = P_shaft / eta_drivetrain

WING-BORNE MODE (eVTOLs in cruise, V > V_stall):
Wing supports the aircraft, rotors act as conventional thrust propellers:

    CL  = W / (0.5 * rho * V^2 * S)
    CD  = Cd0 + CL^2 / (pi * AR * e)             (drag polar)
    D   = 0.5 * rho * V^2 * S * CD
    T   = D                                       (level cruise)
    P_shaft_cruise = T * V / eta_prop
    P_electrical    = P_shaft_cruise / eta_drivetrain

If wing_area_m2 = 0 (multirotor), only the rotor-borne model is used.
If wing_area_m2 > 0 (eVTOL), forward-flight power is min(P_rotor, P_wing),
with a stall guard: if the wing would need CL > CL_max, only the rotor
model is valid at that speed.

The min() blend captures the physical reality that the aircraft uses
whichever mode is more efficient. Below V_stall the wing can't support W,
so the rotor model wins. Above V_stall the wing is dramatically more
efficient, so the wing model wins. The crossover happens naturally.

Author: D. Angelou
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --- Physical constants ---------------------------------------------------
G = 9.80665                  # m/s^2, standard gravity
RHO_SEA_LEVEL = 1.225        # kg/m^3, ISA sea level
T_SEA_LEVEL = 288.15         # K
P_SEA_LEVEL = 101325.0       # Pa
LAPSE_RATE = 0.0065          # K/m, troposphere
R_AIR = 287.05               # J/(kg.K)


# --- Atmosphere -----------------------------------------------------------

def air_density(altitude_m: float = 0.0, temperature_offset_c: float = 0.0) -> float:
    """ISA troposphere density at altitude with optional temperature offset."""
    T = T_SEA_LEVEL - LAPSE_RATE * altitude_m + temperature_offset_c
    p = P_SEA_LEVEL * (T / T_SEA_LEVEL) ** (G / (R_AIR * LAPSE_RATE))
    return p / (R_AIR * T)


# --- Battery model --------------------------------------------------------

def battery_usable_Wh(
    capacity_Ah: float,
    nominal_voltage_V: float,
    usable_fraction: float = 0.90,
    discharge_efficiency: float = 0.96,
) -> float:
    """Usable battery energy after derating for reserve and IR losses."""
    nameplate_Wh = capacity_Ah * nominal_voltage_V
    return nameplate_Wh * usable_fraction * discharge_efficiency


def battery_specific_energy(
    capacity_Ah: float,
    nominal_voltage_V: float,
    pack_mass_kg: float,
) -> float:
    """Pack-level specific energy in Wh/kg."""
    if pack_mass_kg <= 0:
        return float("nan")
    return (capacity_Ah * nominal_voltage_V) / pack_mass_kg


# --- Hover power ----------------------------------------------------------

def hover_power_momentum_theory(
    mass_kg: float,
    n_rotors: int,
    rotor_diameter_m: float,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Electrical hover power: induced (Glauert/FoM) + profile, divided by eta_drive.

    Backward compatible: with profile_power_W=0 this matches v1 exactly, and
    `figure_of_merit` plays the historical lumped-FoM role.

    With profile_power_W > 0, `figure_of_merit` is interpreted as the
    induced-power efficiency only (~0.85-0.95, i.e. 1/kappa).
    """
    rho = air_density(altitude_m, temperature_offset_c)
    thrust_N = mass_kg * G
    disk_area_m2 = n_rotors * math.pi * (rotor_diameter_m / 2.0) ** 2

    p_induced_ideal = thrust_N * math.sqrt(thrust_N / (2.0 * rho * disk_area_m2))
    p_shaft = p_induced_ideal / figure_of_merit + profile_power_W
    p_electrical = p_shaft / drivetrain_efficiency
    return p_electrical


def hover_power_disk_loading(
    mass_kg: float,
    disk_loading_Nm2: float,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Hover power using disk loading. Same model as the geometry version."""
    rho = air_density(altitude_m, temperature_offset_c)
    thrust_N = mass_kg * G
    p_induced_ideal = thrust_N * math.sqrt(disk_loading_Nm2 / (2.0 * rho))
    p_shaft = p_induced_ideal / figure_of_merit + profile_power_W
    p_electrical = p_shaft / drivetrain_efficiency
    return p_electrical


# --- Forward flight power -------------------------------------------------

def _glauert_induced_velocity(
    thrust_N: float,
    airspeed_mps: float,
    alpha_rad: float,
    rho: float,
    disk_area_m2: float,
    tol: float = 1e-4,
    max_iter: int = 200,
) -> float:
    """Solve Glauert's induced-velocity equation by fixed-point iteration."""
    vi_hover = math.sqrt(thrust_N / (2.0 * rho * disk_area_m2))
    vi = vi_hover
    omega = 0.5
    Vh = airspeed_mps * math.cos(alpha_rad)
    Vv = airspeed_mps * math.sin(alpha_rad)
    for _ in range(max_iter):
        denom = 2.0 * rho * disk_area_m2 * math.sqrt(Vh * Vh + (Vv + vi) ** 2)
        if denom <= 0:
            break
        vi_new = thrust_N / denom
        if abs(vi_new - vi) < tol:
            return vi_new
        vi = (1 - omega) * vi + omega * vi_new
    return vi


def forward_flight_power(
    mass_kg: float,
    airspeed_mps: float,
    n_rotors: int,
    rotor_diameter_m: float,
    Cd_body: float = 1.0,
    frontal_area_m2: float = 0.04,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    # v3: optional wing parameters. wing_area_m2 = 0 -> rotor-only (v2 behavior).
    wing_area_m2: float = 0.0,
    wing_span_m: float = 0.0,
    Cd0: float = 0.030,
    oswald_e: float = 0.80,
    CL_max: float = 1.3,
    prop_efficiency: float = 0.85,
) -> float:
    """Electrical forward-flight power at trimmed level flight.

    If wing_area_m2 = 0, returns pure rotor-borne forward flight power
    (Glauert + parasite drag from body, with profile drag from rotor blades).

    If wing_area_m2 > 0, also computes wing-borne cruise power
    (lift from wing, drag = parasite + induced; rotors are thrust propellers)
    and returns the minimum of the two. Below stall, only the rotor model
    is used because the wing physically cannot generate enough lift.
    """
    p_rotor = rotor_borne_forward_power(
        mass_kg, airspeed_mps, n_rotors, rotor_diameter_m,
        Cd_body, frontal_area_m2,
        figure_of_merit, drivetrain_efficiency, profile_power_W,
        altitude_m, temperature_offset_c,
    )
    if wing_area_m2 <= 0 or wing_span_m <= 0 or airspeed_mps <= 0:
        return p_rotor

    p_wing = wing_borne_cruise_power(
        mass_kg, airspeed_mps,
        wing_area_m2, wing_span_m,
        Cd0, oswald_e, CL_max, prop_efficiency,
        drivetrain_efficiency,
        altitude_m, temperature_offset_c,
    )
    return min(p_rotor, p_wing)


def rotor_borne_forward_power(
    mass_kg: float,
    airspeed_mps: float,
    n_rotors: int,
    rotor_diameter_m: float,
    Cd_body: float = 1.0,
    frontal_area_m2: float = 0.04,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Pure rotor-borne forward flight (v2 model, no wing)."""
    rho = air_density(altitude_m, temperature_offset_c)
    W = mass_kg * G
    A = n_rotors * math.pi * (rotor_diameter_m / 2.0) ** 2

    D = 0.5 * rho * airspeed_mps ** 2 * Cd_body * frontal_area_m2
    T = math.sqrt(W * W + D * D)
    alpha = math.atan2(D, W)

    vi = _glauert_induced_velocity(T, airspeed_mps, alpha, rho, A)
    p_induced_ideal = T * (airspeed_mps * math.sin(alpha) + vi)
    p_shaft = p_induced_ideal / figure_of_merit + profile_power_W
    p_electrical = p_shaft / drivetrain_efficiency
    return p_electrical


def wing_borne_cruise_power(
    mass_kg: float,
    airspeed_mps: float,
    wing_area_m2: float,
    wing_span_m: float,
    Cd0: float,
    oswald_e: float,
    CL_max: float,
    prop_efficiency: float,
    drivetrain_efficiency: float,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Wing-borne cruise power for an eVTOL or fixed-wing aircraft.

    Computes:
        CL = W / (0.5 * rho * V^2 * S)        (required lift coefficient)
        CD = Cd0 + CL^2 / (pi * AR * e)       (drag polar)
        D  = 0.5 * rho * V^2 * S * CD         (total drag)
        T  = D                                 (level cruise: thrust = drag)
        P_shaft_thrust = T * V / eta_prop     (propeller thrust power)
        P_electrical   = P_shaft / eta_drive

    If the wing would need CL > CL_max, returns +inf (stalled, wing cannot
    support the aircraft -- caller must use rotor-borne model instead).
    """
    rho = air_density(altitude_m, temperature_offset_c)
    W = mass_kg * G
    AR = wing_span_m ** 2 / wing_area_m2
    q = 0.5 * rho * airspeed_mps ** 2

    CL = W / (q * wing_area_m2)
    if CL > CL_max:
        return float("inf")  # stall: wing cannot generate enough lift

    CD = Cd0 + CL ** 2 / (math.pi * AR * oswald_e)
    D = q * wing_area_m2 * CD
    T = D  # level flight

    p_shaft = T * airspeed_mps / prop_efficiency
    p_electrical = p_shaft / drivetrain_efficiency
    return p_electrical


def stall_speed(
    mass_kg: float,
    wing_area_m2: float,
    CL_max: float = 1.3,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Wing-only stall speed (level 1-g flight). Returns inf if no wing."""
    if wing_area_m2 <= 0:
        return float("inf")
    rho = air_density(altitude_m, temperature_offset_c)
    return math.sqrt(2 * mass_kg * G / (rho * wing_area_m2 * CL_max))


# --- Aircraft container ---------------------------------------------------

@dataclass
class Aircraft:
    """All parameters needed to evaluate endurance."""
    name: str
    mass_kg: float
    n_rotors: int
    rotor_diameter_m: float
    battery_capacity_Ah: float
    battery_voltage_V: float
    Cd_body: float = 1.0
    frontal_area_m2: float = 0.04
    figure_of_merit: float = 0.65         # induced-power efficiency (with profile_power_W > 0)
    drivetrain_efficiency: float = 0.78
    profile_power_W: float = 0.0          # rotor profile power at hover (v2)
    usable_fraction: float = 0.90
    discharge_efficiency: float = 0.96
    # v3: wing-borne cruise parameters. wing_area_m2 = 0 -> pure multirotor.
    wing_area_m2: float = 0.0
    wing_span_m: float = 0.0
    Cd0: float = 0.030
    oswald_e: float = 0.80
    CL_max: float = 1.3
    prop_efficiency: float = 0.85
    notes: str = ""

    @property
    def nameplate_Wh(self) -> float:
        return self.battery_capacity_Ah * self.battery_voltage_V

    @property
    def disk_area_m2(self) -> float:
        return self.n_rotors * math.pi * (self.rotor_diameter_m / 2.0) ** 2

    @property
    def disk_loading_Nm2(self) -> float:
        return (self.mass_kg * G) / self.disk_area_m2

    @property
    def has_wing(self) -> bool:
        return self.wing_area_m2 > 0 and self.wing_span_m > 0

    @property
    def aspect_ratio(self) -> float:
        if not self.has_wing:
            return float("nan")
        return self.wing_span_m ** 2 / self.wing_area_m2

    @property
    def wing_loading_Nm2(self) -> float:
        if not self.has_wing:
            return float("nan")
        return (self.mass_kg * G) / self.wing_area_m2


# --- High-level endurance & range -----------------------------------------

def hover_endurance_min(
    ac: Aircraft,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Predicted hover endurance in minutes."""
    P = hover_power_momentum_theory(
        mass_kg=ac.mass_kg,
        n_rotors=ac.n_rotors,
        rotor_diameter_m=ac.rotor_diameter_m,
        figure_of_merit=ac.figure_of_merit,
        drivetrain_efficiency=ac.drivetrain_efficiency,
        profile_power_W=ac.profile_power_W,
        altitude_m=altitude_m,
        temperature_offset_c=temperature_offset_c,
    )
    E = battery_usable_Wh(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
    )
    return (E / P) * 60.0


def forward_endurance_and_range(
    ac: Aircraft,
    airspeed_mps: float,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> tuple[float, float]:
    """Predicted endurance (min) and range (km) at a given cruise speed."""
    P = forward_flight_power(
        mass_kg=ac.mass_kg,
        airspeed_mps=airspeed_mps,
        n_rotors=ac.n_rotors,
        rotor_diameter_m=ac.rotor_diameter_m,
        Cd_body=ac.Cd_body,
        frontal_area_m2=ac.frontal_area_m2,
        figure_of_merit=ac.figure_of_merit,
        drivetrain_efficiency=ac.drivetrain_efficiency,
        profile_power_W=ac.profile_power_W,
        altitude_m=altitude_m,
        temperature_offset_c=temperature_offset_c,
        wing_area_m2=ac.wing_area_m2,
        wing_span_m=ac.wing_span_m,
        Cd0=ac.Cd0,
        oswald_e=ac.oswald_e,
        CL_max=ac.CL_max,
        prop_efficiency=ac.prop_efficiency,
    )
    E = battery_usable_Wh(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
    )
    t_min = (E / P) * 60.0
    range_km = (airspeed_mps * (t_min / 60.0)) * 3.6
    return t_min, range_km


def power_curve(
    ac: Aircraft,
    speeds_mps: list[float],
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> list[float]:
    """Power-required curve over a range of airspeeds (W)."""
    out = []
    for V in speeds_mps:
        if V <= 0.1:
            out.append(hover_power_momentum_theory(
                mass_kg=ac.mass_kg,
                n_rotors=ac.n_rotors,
                rotor_diameter_m=ac.rotor_diameter_m,
                figure_of_merit=ac.figure_of_merit,
                drivetrain_efficiency=ac.drivetrain_efficiency,
                profile_power_W=ac.profile_power_W,
                altitude_m=altitude_m,
                temperature_offset_c=temperature_offset_c,
            ))
        else:
            out.append(forward_flight_power(
                mass_kg=ac.mass_kg,
                airspeed_mps=V,
                n_rotors=ac.n_rotors,
                rotor_diameter_m=ac.rotor_diameter_m,
                Cd_body=ac.Cd_body,
                frontal_area_m2=ac.frontal_area_m2,
                figure_of_merit=ac.figure_of_merit,
                drivetrain_efficiency=ac.drivetrain_efficiency,
                profile_power_W=ac.profile_power_W,
                altitude_m=altitude_m,
                temperature_offset_c=temperature_offset_c,
                wing_area_m2=ac.wing_area_m2,
                wing_span_m=ac.wing_span_m,
                Cd0=ac.Cd0,
                oswald_e=ac.oswald_e,
                CL_max=ac.CL_max,
                prop_efficiency=ac.prop_efficiency,
            ))
    return out


def best_cruise_speed(
    ac: Aircraft,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    v_min: float = 1.0,
    v_max: float = 30.0,
    n_pts: int = 201,
) -> tuple[float, float, float]:
    """Find the airspeed that maximizes range (min energy per km).

    For wing-borne aircraft, pass a higher v_max (e.g. 100 m/s) to capture
    the wing-borne cruise regime.
    """
    best_V = v_min
    best_range = -1.0
    best_t = 0.0
    step = (v_max - v_min) / max(n_pts - 1, 1)
    for i in range(n_pts):
        V = v_min + i * step
        t_min, rng_km = forward_endurance_and_range(
            ac, V, altitude_m, temperature_offset_c
        )
        if rng_km > best_range:
            best_range = rng_km
            best_V = V
            best_t = t_min
    return best_V, best_range, best_t


# --- Self-test ------------------------------------------------------------

if __name__ == "__main__":
    test = Aircraft(
        name="Test 1 kg quad",
        mass_kg=1.0,
        n_rotors=4,
        rotor_diameter_m=0.254,
        battery_capacity_Ah=5.0,
        battery_voltage_V=14.8,
        figure_of_merit=0.87,
        drivetrain_efficiency=0.78,
        profile_power_W=30.0,
    )
    P = hover_power_momentum_theory(
        test.mass_kg, test.n_rotors, test.rotor_diameter_m,
        test.figure_of_merit, test.drivetrain_efficiency, test.profile_power_W,
    )
    t = hover_endurance_min(test)
    Vbest, rng, tcruise = best_cruise_speed(test)
    print(f"{test.name}")
    print(f"  Disk loading       : {test.disk_loading_Nm2:6.1f} N/m^2")
    print(f"  Hover power        : {P:6.1f} W")
    print(f"  Hover endurance    : {t:6.1f} min")
    print(f"  Best cruise speed  : {Vbest:6.1f} m/s")
    print(f"  Range at best V    : {rng:6.2f} km")
    print(f"  Endurance at best V: {tcruise:6.1f} min")
